"""Official shareholding pattern (promoter, foreign and domestic institutions, public, pledges) from NSE XBRL files.

Sources, all public and free:
  - a file you saved from NSE (Corporate Filings > Shareholding Pattern > XBRL), passed with --shareholding;
  - NSE's public RSS feed (nsearchives.nseindia.com/content/RSS/Shareholding_Pattern.xml), which lists the newest filings
    with a link to each XBRL file. The feed is short, so it only helps right after a company files.
Every snapshot a run sees is kept in a small local store, so quarter-on-quarter change builds up over time.
No cookies, no browser imitation. Education only; not financial advice.
"""
from __future__ import annotations

import csv
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from indiafacts.models import AvailabilityKind, Fact, PeriodType, Status

SOURCE = "nse_shp"
FEED_URL = "https://nsearchives.nseindia.com/content/RSS/Shareholding_Pattern.xml"
USER_AGENT = "NexTrade-research/0.1 (education; reads the exchange's public RSS and filings)"
MAX_BYTES = 6_000_000
XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"

# CategoryOfShareholdersAxis member -> our key
CATEGORIES = {
    "ShareholdingOfPromoterAndPromoterGroupMember": "promoter",
    "InstitutionsForeignMember": "foreign_inst",
    "InstitutionsDomesticMember": "domestic_inst",
    "MutualFundsOrUTIMember": "mutual_funds",
    "MutualFundsMember": "mutual_funds",
    "InsuranceCompaniesMember": "insurance",
    "PublicShareholdingMember": "public",
    "ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakhMember": "retail",
    "NonResidentIndiansMember": "nri",
    "BodiesCorporateMember": "bodies_corporate",
    "CentralGovernmentOrPresidentOfIndiaMember": "government",
    "ShareholdingPatternMember": "total",
}
STORE_FIELDS = ["symbol", "isin", "as_on", "promoter", "pledged_of_promoter", "foreign_inst", "domestic_inst", "mutual_funds",
                "insurance", "public", "retail", "shareholders", "total_shares", "source", "fetched_on"]


@dataclass
class Shareholding:
    symbol: str
    isin: str = ""
    name: str = ""
    as_on: date | None = None
    pct: dict[str, float] = field(default_factory=dict)          # fraction of all shares, 0..1
    pledged_of_promoter: float | None = None                     # fraction of the promoters' shares that are pledged
    shareholders: int | None = None
    total_shares: float | None = None                            # total equity shares in issue, from the "total" row's share count
    source: str = ""                                             # file name or URL it came from


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_shp(data: bytes | str | Path, source: str = "") -> Shareholding:
    """Parse an NSE shareholding-pattern XBRL instance. Raises ValueError when it is not one."""
    raw = Path(data).read_bytes() if isinstance(data, Path) else (data.encode() if isinstance(data, str) else data)
    if len(raw) > MAX_BYTES:
        raise ValueError("shareholding file larger than the size cap")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"not a readable XML file ({exc})") from None
    if "in-bse-shp" not in raw[:4000].decode("utf-8", "ignore"):
        raise ValueError("not an NSE shareholding-pattern XBRL file")
    cat_of: dict[str, str] = {}
    instants: dict[str, str] = {}
    for c in root.iter(f"{{{XBRLI}}}context"):
        cid = c.get("id", "")
        members = [(e.get("dimension", "").rsplit(":", 1)[-1], (e.text or "").rsplit(":", 1)[-1])
                   for e in c.iter(f"{{{XBRLDI}}}explicitMember")]
        typed = c.find(f".//{{{XBRLDI}}}typedMember")
        if len(members) == 1 and typed is None and members[0][0] == "CategoryOfShareholdersAxis":
            cat_of[cid] = members[0][1]
        inst = c.find(f"{{{XBRLI}}}period/{{{XBRLI}}}instant")
        if inst is not None and inst.text:
            instants[cid] = inst.text.strip()
    scalar: dict[str, str] = {}
    pct: dict[str, float] = {}
    shares: dict[str, float] = {}
    pledged: dict[str, float] = {}
    holders: dict[str, int] = {}
    used_instants: Counter = Counter()
    for el in root:
        name = _local(el.tag)
        text = (el.text or "").strip()
        cid = el.get("contextRef", "")
        if name in ("Symbol", "ISIN", "NameOfTheCompany") and text:
            scalar.setdefault(name, text)
        cat = CATEGORIES.get(cat_of.get(cid, ""))
        if cat is None or not text:
            continue
        try:
            val = float(text)
        except ValueError:
            continue
        if cid in instants:
            used_instants[instants[cid]] += 1
        if name == "ShareholdingAsAPercentageOfTotalNumberOfShares":
            pct[cat] = val
        elif name == "NumberOfFullyPaidUpEquityShares":
            shares[cat] = val
        elif name == "NumberOfSharesEncumberedUnderPledged":
            pledged[cat] = val
        elif name == "NumberOfShareholders":
            holders[cat] = int(val)
    if "promoter" not in pct and "public" not in pct:
        raise ValueError("no promoter or public holding found in the file")
    as_on = None
    if used_instants:
        try:
            as_on = date.fromisoformat(used_instants.most_common(1)[0][0])
        except ValueError:
            as_on = None
    prom_shares = shares.get("promoter")
    pl = None
    if prom_shares and prom_shares > 0 and "promoter" in pledged:
        pl = min(1.0, pledged["promoter"] / prom_shares)
    return Shareholding(symbol=scalar.get("Symbol", "").upper(), isin=scalar.get("ISIN", ""), name=scalar.get("NameOfTheCompany", ""),
                        as_on=as_on, pct=pct, pledged_of_promoter=pl, shareholders=holders.get("total"),
                        total_shares=shares.get("total") if shares.get("total", 0) > 0 else None, source=source)


# ---- local store (CSV) ---------------------------------------------------------------------------------------

def default_store() -> Path:
    import os

    return Path(os.environ.get("INDIAFACTS_SHP_STORE") or Path.home() / ".indiafacts" / "shareholding.csv")


def repo_store() -> Path:
    import os

    return Path(os.environ.get("INDIAFACTS_SHP_REPO") or Path(__file__).resolve().parent.parent / "data" / "shareholding.csv")


def _row(sh: Shareholding, today: date) -> dict:
    g = lambda k: "" if sh.pct.get(k) is None else f"{sh.pct[k]:.6f}"
    return {"symbol": sh.symbol, "isin": sh.isin, "as_on": sh.as_on.isoformat() if sh.as_on else "", "promoter": g("promoter"),
            "pledged_of_promoter": "" if sh.pledged_of_promoter is None else f"{sh.pledged_of_promoter:.6f}",
            "foreign_inst": g("foreign_inst"), "domestic_inst": g("domestic_inst"), "mutual_funds": g("mutual_funds"),
            "insurance": g("insurance"), "public": g("public"), "retail": g("retail"),
            "shareholders": "" if sh.shareholders is None else sh.shareholders,
            "total_shares": "" if sh.total_shares is None else f"{sh.total_shares:.0f}", "source": sh.source, "fetched_on": today.isoformat()}


def save_snapshot(sh: Shareholding, path: Path | None = None, today: date | None = None) -> bool:
    """Append the snapshot unless the same symbol and as-on date is already stored. Returns True when added."""
    if not sh.symbol or sh.as_on is None:
        return False
    path = Path(path or default_store())
    have = {(r["symbol"], r["as_on"]) for r in _read(path)}
    if (sh.symbol, sh.as_on.isoformat()) in have:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    _upgrade_header(path)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=STORE_FIELDS)
        if new:
            w.writeheader()
        w.writerow(_row(sh, today or date.today()))
    return True


def _upgrade_header(path: Path) -> None:
    """A store written before a column existed gets the new header, so appended rows line up."""
    rows = _read(path)
    if not rows:
        return
    with open(path, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh), [])
    if header == STORE_FIELDS:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=STORE_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _read(path: Path) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _from_row(r: dict) -> Shareholding:
    f = lambda k: float(r[k]) if r.get(k) not in ("", None) else None
    pct = {k: f(k) for k in ("promoter", "foreign_inst", "domestic_inst", "mutual_funds", "insurance", "public", "retail") if f(k) is not None}
    return Shareholding(symbol=r["symbol"], isin=r.get("isin", ""), as_on=date.fromisoformat(r["as_on"]) if r.get("as_on") else None,
                        pct=pct, pledged_of_promoter=f("pledged_of_promoter"),
                        shareholders=int(r["shareholders"]) if r.get("shareholders") else None,
                        total_shares=f("total_shares"), source=r.get("source", ""))


def history(symbol: str, stores: list[Path] | None = None) -> list[Shareholding]:
    """Every stored snapshot for the symbol, oldest first, from the home store and the repo's data file."""
    sym = symbol.upper().removesuffix(".NS")
    seen: dict[str, Shareholding] = {}
    for p in (stores if stores is not None else [repo_store(), default_store()]):
        for r in _read(Path(p)):
            if r.get("symbol") == sym and r.get("as_on"):
                seen[r["as_on"]] = _from_row(r)
    return [seen[k] for k in sorted(seen)]


# ---- feed ------------------------------------------------------------------------------------------------------

def _get(url: str, opener: Callable = urlopen) -> bytes:
    with opener(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as r:
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("response larger than the size cap")
    return raw


def feed_items(opener: Callable = urlopen) -> list[tuple[str, str]]:
    """(company name, XBRL url) for the newest filings in NSE's shareholding feed."""
    root = ET.fromstring(_get(FEED_URL, opener))
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        if link.startswith("https://nsearchives.nseindia.com/corporate/") and link.endswith(".xml"):
            out.append(((it.findtext("title") or "").strip(), link))
    return out


def _norm(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    n = re.sub(r"\b(limited|ltd|the|pvt|private)\b", " ", n)
    return " ".join(n.split())


def fetch_latest(symbol: str, company_name: str | None, opener: Callable = urlopen) -> tuple[Shareholding | None, str]:
    """Look for the company in the feed. Returns (snapshot or None, note). Never raises."""
    sym = symbol.upper().removesuffix(".NS")
    try:
        items = feed_items(opener)
    except Exception as exc:
        return None, f"the exchange's shareholding feed could not be read ({type(exc).__name__})"
    want = _norm(company_name or "")
    for title, url in items:
        if want and _norm(title) == want or sym.lower() in url.lower().split("/")[-1]:
            try:
                sh = parse_shp(_get(url, opener), source=url)
            except Exception as exc:
                return None, f"found the filing but could not read it ({type(exc).__name__})"
            if sh.symbol and sh.symbol != sym:
                continue
            return sh, ""
    return None, "this company's pattern is not in the exchange's latest feed (it lists only the newest filings)"


def poll(store: Path | None = None, opener: Callable = urlopen, today: date | None = None) -> tuple[int, int]:
    """Download every filing currently in the feed into the store. Returns (added, failed)."""
    added = failed = 0
    for _, url in feed_items(opener):
        try:
            if save_snapshot(parse_shp(_get(url, opener), source=url), store, today):
                added += 1
        except Exception:
            failed += 1
    return added, failed


# ---- facts -------------------------------------------------------------------------------------------------------

def shareholding_facts(entity_key: str, snaps: list[Shareholding], now: datetime | None = None) -> list[Fact]:
    """Facts for the newest snapshot plus the change in percentage points against the one before it."""
    now = now or datetime.now(timezone.utc)
    if not snaps:
        return []
    cur = snaps[-1]
    prev = snaps[-2] if len(snaps) > 1 else None
    end = cur.as_on or now.date()
    out: list[Fact] = []

    def add(metric, value, unit="ratio", related=None, status=Status.ok, reason=""):
        out.append(Fact.make(entity_key=entity_key, metric=metric, unit=unit, period_end=end, period_type=PeriodType.point,
                             source=SOURCE, source_field=cur.source or "shareholding pattern", retrieved_at=now,
                             available_from=end, availability_kind=AvailabilityKind.filed,
                             value=None if value is None else Decimal(str(round(value, 6))), status=status, reason=reason,
                             related_fact_ids=related or [],
                             evidence=f"NSE shareholding pattern as on {end}" + (f", {cur.source}" if cur.source else "")))

    names = {"promoter": "sh_promoter", "foreign_inst": "sh_foreign_inst", "domestic_inst": "sh_domestic_inst",
             "mutual_funds": "sh_mutual_funds", "insurance": "sh_insurance", "public": "sh_public", "retail": "sh_retail"}
    for key, metric in names.items():
        if key in cur.pct:
            add(metric, cur.pct[key])
    if cur.pledged_of_promoter is not None:
        add("sh_promoter_pledged", cur.pledged_of_promoter)
    if cur.shareholders is not None:
        add("sh_shareholders", float(cur.shareholders), "count")
    if cur.total_shares:
        add("shares_outstanding", cur.total_shares, "shares")
    if prev is not None:
        for key in ("promoter", "foreign_inst", "domestic_inst"):
            if key in cur.pct and key in prev.pct:
                add(f"{names[key]}_change", cur.pct[key] - prev.pct[key], "ratio")
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(prog="indiafacts.shareholding", description="Collect shareholding patterns from the exchange's public feed.")
    p.add_argument("action", choices=["poll", "show"])
    p.add_argument("symbol", nargs="?", help="show: NSE symbol")
    p.add_argument("--store", type=Path, default=None, help="CSV to append to (default: the home store ~/.indiafacts/shareholding.csv)")
    a = p.parse_args(argv)
    if a.action == "poll":
        added, failed = poll(a.store or default_store())
        print(f"added {added} new filings, {failed} could not be read")
        return 0
    if not a.symbol:
        print("give a symbol", file=sys.stderr)
        return 2
    for sh in history(a.symbol):
        print(f"{sh.symbol} as on {sh.as_on}: promoter {sh.pct.get('promoter', 0):.1%}, foreign {sh.pct.get('foreign_inst', 0):.1%}, "
              f"domestic {sh.pct.get('domestic_inst', 0):.1%}, pledged of promoter {sh.pledged_of_promoter if sh.pledged_of_promoter is not None else 'n/a'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
