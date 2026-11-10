"""NSE Market Lens (https://marketlens.nseindia.com), the exchange's own screener, as a data source.

The owner states they have NSE's permission to use Market Lens for educational purposes (see docs/DATA_PERMISSIONS.md).
Access is plain HTTP with an honest User-Agent, one request at a time at least one second apart, timeouts, and an on-disk cache.
No browser imitation, no cookie tricks, no key extraction. Nothing here raises to callers: failures become an empty result and a reason.

Endpoints used: GET /api/sectors, GET /api/sectors/{id}/stocks. Percent fields are converted to ratios so metric units match
yahoo.py and shareholding.py (0.45 means 45%). Placeholder zeros (the field exists but NSE fills 0) produce no fact.
Education only; not financial advice.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from indiafacts.models import Fact, PeriodType, Status

SOURCE = "nse_marketlens"
BASE = "https://marketlens.nseindia.com"
USER_AGENT = "NexTrade-research/0.1 (education; permitted use of NSE Market Lens)"
MIN_DELAY = 1.0
TIMEOUT = 20
LIVE_TIMEOUT = 10
MAX_BYTES = 8_000_000
CACHE_TTL = 24 * 3600
URL_TTL = 3600

_mem: dict = {"url": None, "at": 0.0, "rows": None, "fetched": None}


def enabled() -> bool:
    return os.environ.get("INDIAFACTS_MARKETLENS", "1").strip().lower() not in ("0", "off", "false", "no")


def cache_path() -> Path:
    env = os.environ.get("INDIAFACTS_MARKETLENS_CACHE")
    return Path(env) if env else Path.home() / ".indiafacts" / "marketlens.json"


class Client:
    """Polite reader. `opener(request, timeout=)` is injectable for tests; `sleep` too."""

    def __init__(self, opener: Callable = urlopen, sleep: Callable[[float], None] = time.sleep, delay: float = MIN_DELAY,
                 clock: Callable[[], float] = time.monotonic, timeout: float = TIMEOUT):
        self.opener, self.sleep, self.delay, self.clock = opener, sleep, max(delay, MIN_DELAY), clock
        self.timeout = timeout
        self._last: float | None = None

    def _get(self, path: str) -> dict:
        if self._last is not None:
            wait = self.delay - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()
        req = Request(BASE + path, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with self.opener(req, timeout=self.timeout) as r:
            raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("response larger than the size cap")
        body = json.loads(raw)
        if not isinstance(body, dict) or body.get("success") is False:
            raise ValueError(f"Market Lens reported an error: {(body or {}).get('error') if isinstance(body, dict) else 'bad body'}")
        return body

    def sectors(self) -> tuple[list[dict], str]:
        try:
            data = self._get("/api/sectors").get("data")
            if not isinstance(data, list):
                return [], "sector list had an unexpected shape"
            return data, ""
        except Exception as exc:
            return [], f"Market Lens sector list unavailable ({type(exc).__name__})"

    def sector_stocks(self, sector_id: str) -> tuple[list[dict], str]:
        try:
            body = self._get(f"/api/sectors/{quote(str(sector_id), safe='')}/stocks?sortBy=marketCap&sortOrder=desc")
            rows = body.get("data")
            if not isinstance(rows, list):
                return [], f"sector '{sector_id}' had an unexpected shape"
            meta = body.get("meta") or {}
            note = ""
            total = meta.get("total")
            if meta.get("hasMore") or (isinstance(total, int) and total > len(rows)):
                note = f"sector '{sector_id}' returned {len(rows)} of {total} rows (partial)"
            return rows, note
        except Exception as exc:
            return [], f"sector '{sector_id}' unavailable ({type(exc).__name__})"


def fetch_universe(client: Client | None = None) -> tuple[dict[str, dict], list[str]]:
    """Every sector's stocks, {SYMBOL: row}. Rows get `_sectorId`. Returns (rows, problems); never raises."""
    c = client or Client()
    secs, why = c.sectors()
    if not secs:
        return {}, [why or "no sectors returned"]
    out: dict[str, dict] = {}
    problems: list[str] = []
    for s in secs:
        sid = s.get("id") if isinstance(s, dict) else None
        if not sid:
            continue
        rows, note = c.sector_stocks(sid)
        if note:
            problems.append(note)
        for r in rows:
            sym = str(r.get("id") or r.get("ticker") or "").strip().upper()
            if sym and isinstance(r, dict):
                out[sym] = {**r, "_sectorId": sid}
    return out, problems


def _write(path: Path, rows: dict, problems: list[str], now: datetime) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": now.isoformat(), "problems": problems, "rows": rows}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


_disk: dict = {}


def _read(path: Path) -> tuple[dict, datetime | None]:
    try:
        mt = path.stat().st_mtime_ns
        hit = _disk.get(str(path))
        if hit and hit[0] == mt:
            return hit[1], hit[2]
        d = json.loads(path.read_text(encoding="utf-8"))
        rows = d.get("rows")
        at = datetime.fromisoformat(d["fetched_at"])
        rows = rows if isinstance(rows, dict) else {}
        _disk[str(path)] = (mt, rows, at)
        return rows, at
    except Exception:
        return {}, None


def refresh(path: Path | None = None, client: Client | None = None, now: datetime | None = None) -> tuple[dict, list[str]]:
    """Fetch from NSE now and write the cache file (only when complete enough: at least one row and no failed sector)."""
    now = now or datetime.now(timezone.utc)
    rows, problems = fetch_universe(client)
    if rows and not any("unavailable" in p for p in problems):
        _write(path or cache_path(), rows, problems, now)
    return rows, problems


LAST: dict = {"kind": "", "at": None}          # where the last universe_with_reason() result came from


def _since(at: datetime | None) -> str:
    return f" as of {at.date().isoformat()}" if at else ""


def universe_with_reason(client: Client | None = None, now: datetime | None = None, mono: Callable[[], float] = time.monotonic) -> tuple[dict[str, dict], str]:
    """{symbol: row} and a reason string ('' when fine). Published daily copy (Render) > fresh disk cache > full live fetch >
    older disk cache. LAST records which one answered."""
    LAST.update(kind="", at=None)
    if not enabled():
        return {}, "Market Lens switched off"
    now = now or datetime.now(timezone.utc)
    url = os.environ.get("INDIAFACTS_MARKETLENS_URL", "").strip()
    why_url = ""
    if url:
        if _mem["rows"] is not None and _mem["url"] == url and mono() - _mem["at"] < URL_TTL:
            LAST.update(kind="daily copy", at=_mem.get("fetched"))
            return _mem["rows"], ""
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=10) as r:
                raw = r.read(MAX_BYTES * 2)
            body = json.loads(raw)
            rows = body.get("rows") or {}
            try:
                fetched = datetime.fromisoformat(body["fetched_at"])
            except Exception:
                fetched = None
            if rows:
                _mem.update(url=url, at=mono(), rows=rows, fetched=fetched)
                LAST.update(kind="daily copy", at=fetched)
                return rows, ""
            why_url = "published Market Lens file was empty"
        except Exception as exc:
            why_url = f"published Market Lens file unavailable ({type(exc).__name__})"
        if _mem["rows"] is not None and _mem["url"] == url:
            LAST.update(kind="daily copy", at=_mem.get("fetched"))
            return _mem["rows"], why_url
    path = cache_path()
    cached, at = _read(path)
    if cached and at is not None and (now - at).total_seconds() < CACHE_TTL:
        LAST.update(kind="local cache", at=at)
        return cached, why_url
    if url:                                          # Render never walks all of NSE: older cache or nothing
        if cached:
            LAST.update(kind="local cache", at=at)
        return cached, why_url or "Market Lens unavailable"
    rows, problems = refresh(path, client, now)
    if rows:
        LAST.update(kind="live", at=now)
        return rows, "; ".join(problems[:3])
    if cached:
        LAST.update(kind="local cache", at=at)
        return cached, "Market Lens refresh failed; using an older cache (" + (problems[0] if problems else "no detail") + ")"
    return {}, problems[0] if problems else "Market Lens unavailable"


def universe(client: Client | None = None, now: datetime | None = None) -> dict[str, dict]:
    return universe_with_reason(client, now)[0]


_live: dict = {}


def live_enabled() -> bool:
    return os.environ.get("INDIAFACTS_MARKETLENS_LIVE", "1").strip().lower() not in ("0", "off", "false", "no")


def target_row(symbol: str, opener: Callable | None = None, now: datetime | None = None, mono: Callable[[], float] = time.monotonic,
               sleep: Callable[[float], None] = time.sleep) -> tuple[dict | None, str, str]:
    """The target's own row for a live analysis: (row or None, origin, reason). Order: a direct Market Lens request for the
    target's sector (10 s timeout, cached 1 h in this process), then the published daily copy, then the local cache.
    origin is 'live', 'daily copy as of <date>' or 'local cache as of <date>'. Never raises."""
    if not enabled():
        return None, "", "Market Lens switched off"
    sym = symbol.upper().removesuffix(".NS")
    opener = opener or (lambda req, timeout=None: urlopen(req, timeout=timeout))
    try:
        hit = _live.get(sym)
        if hit and mono() - hit[0] < URL_TTL:
            return hit[1], "live", ""
        rows, why = universe_with_reason(Client(opener=opener, sleep=sleep), now, mono)
        kind, at = LAST["kind"], LAST["at"]
        row = rows.get(sym)
        if row is None:
            return None, "", why
        if kind == "live":                                       # the whole universe was just fetched from NSE
            _live[sym] = (mono(), row)
            return row, "live", why
        if live_enabled() and row.get("_sectorId"):
            got, note = Client(opener=opener, sleep=sleep, timeout=LIVE_TIMEOUT).sector_stocks(row["_sectorId"])
            fresh = next((r for r in got if str(r.get("id") or r.get("ticker") or "").upper() == sym), None)
            if fresh is not None:
                fresh = {**fresh, "_sectorId": row["_sectorId"]}
                _live[sym] = (mono(), fresh)
                return fresh, "live", ""
            why = (why + "; " if why else "") + (note or "target not in the sector response") + "; live request failed, using the stored copy"
        return row, f"{kind}{_since(at)}", why
    except Exception as exc:
        return None, "", f"Market Lens target lookup failed ({type(exc).__name__})"


# ---- facts ------------------------------------------------------------------------------------------------------

_drift: dict = {"key": None, "fields": frozenset()}


def disabled_fields() -> frozenset:
    """Fields the daily drift check found to be placeholders today (drift_report.json named by INDIAFACTS_DRIFT_REPORT); never used. See drift.py."""
    path = os.environ.get("INDIAFACTS_DRIFT_REPORT", "").strip()
    if not path:
        return frozenset()
    try:
        key = (path, Path(path.removeprefix("file://")).stat().st_mtime_ns)
    except OSError:
        key = (path, None)
    if _drift["key"] != key:
        from indiafacts.drift import disabled_marketlens_fields

        _drift.update(key=key, fields=disabled_marketlens_fields(path))
    return _drift["fields"]


def _num(row: dict, key: str) -> float | None:
    if key in disabled_fields():
        return None
    v = row.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return None
    return float(v)


def _stamp(row: dict, now: datetime) -> tuple[date, str]:
    ts = str(row.get("lastUpdated") or "")
    try:
        return datetime.fromisoformat(ts).date(), ts
    except ValueError:
        return now.date(), ts or "unknown"


def facts_for(symbol: str, row: dict, now: datetime | None = None, origin: str = "") -> list[Fact]:
    """Facts from one Market Lens row. Placeholder zeros and unknown units produce nothing."""
    now = now or datetime.now(timezone.utc)
    sym = symbol.upper().removesuffix(".NS")
    key = sym + ".NS"
    end, ts = _stamp(row, now)
    sid = row.get("_sectorId") or str(row.get("sector") or "").lower()
    out: list[Fact] = []

    def add(metric: str, field: str, value: float, unit: str, status=Status.ok, reason: str = "", scale: float = 1.0) -> None:
        out.append(Fact.make(
            entity_key=key, metric=metric, value=Decimal(str(round(value / scale, 8))), unit=unit, period_end=end,
            period_type=PeriodType.point, source=SOURCE, source_field=field, retrieved_at=now, available_from=end,
            status=status, reason=reason,
            evidence=f"NSE Market Lens /api/sectors/{sid}/stocks field {field}, lastUpdated {ts}" + (f"; fetched {origin}" if origin else "")))

    v = _num(row, "marketCap")
    if v and v > 0:
        add("market_cap", "marketCap", v, "INR")
    v = _num(row, "peRatio")
    if v and v > 0:
        add("pe_ttm", "peRatio", v, "ratio")
    v = _num(row, "pbRatio")
    if v and v > 0:
        add("pb", "pbRatio", v, "ratio")
    v = _num(row, "debtToEquity")
    if v is not None and (v > 0 or (v == 0 and _num(row, "totalBorrowings") == 0)):
        add("debt_to_equity", "debtToEquity", v, "ratio")           # a plain ratio (0.41), unlike Yahoo's percent-style figure
    v = _num(row, "roce")
    if v:
        add("ml_roce", "roce", v, "ratio", status=Status.unverified, scale=100.0,
            reason="Market Lens states ROCE as a percent; its definition is not published, so it is not the same as our fy_roce")
    v = _num(row, "divYield")
    if v and v > 0:
        add("dividend_yield", "divYield", v, "ratio", scale=100.0)
    prom, pub = _num(row, "promoterHolding"), _num(row, "publicHolding")
    if prom is not None and pub is not None and pub > 0 and 0 <= prom <= 100 and abs(prom + pub - 100) <= 1.0:
        add("sh_promoter", "promoterHolding", prom, "ratio", scale=100.0,
            reason="exchange-sourced; as-of is the Market Lens refresh date, not the quarter end")
        add("sh_public", "publicHolding", pub, "ratio", scale=100.0,
            reason="exchange-sourced; as-of is the Market Lens refresh date, not the quarter end")
    hi, lo = _num(row, "week52High"), _num(row, "week52Low")
    if hi and lo and hi >= lo > 0:
        add("high_52w", "week52High", hi, "INR")
        add("low_52w", "week52Low", lo, "INR")
    return out


# Fields deliberately not used: returnOnEquity, revenueGrowth, industryPe, avgVolume (placeholder 0), patGrowth (equals netProfit),
# netProfit/revenue/opRevenue/totalEquity/totalAssets/borrowings (mixed or unproven units).


def fallback_facts(symbol: str, row: dict, now: datetime | None = None, origin: str = "") -> list[Fact]:
    """The price-side figures Market Lens states, used only when Yahoo is unavailable for the target: last price, 1/3/5-year
    price returns, 1-year volatility, distance from the 52-week high and the 50/200-day averages. Returns and volatility are
    stated as percents (divided by 100). Placeholder zeros and nulls produce nothing."""
    now = now or datetime.now(timezone.utc)
    key = symbol.upper().removesuffix(".NS") + ".NS"
    end, ts = _stamp(row, now)
    sid = row.get("_sectorId") or str(row.get("sector") or "").lower()
    out: list[Fact] = []

    def add(metric: str, field: str, value: float, unit: str, scale: float = 1.0) -> None:
        out.append(Fact.make(
            entity_key=key, metric=metric, value=Decimal(str(round(value / scale, 8))), unit=unit, period_end=end,
            period_type=PeriodType.point, source=SOURCE, source_field=field, retrieved_at=now, available_from=end,
            status=Status.ok,
            evidence=f"NSE Market Lens /api/sectors/{sid}/stocks field {field}, lastUpdated {ts}" + (f"; fetched {origin}" if origin else "")))

    v = _num(row, "closePrice")
    if v and v > 0:
        add("price", "closePrice", v, "INR")
    for n, field in ((1, "oneYearReturn"), (3, "threeYearReturn"), (5, "fiveYearReturn")):
        v = _num(row, field)
        if v:
            add(f"return_{n}y", field, v, "ratio", scale=100.0)
    v = _num(row, "annVolatility")
    if v and v > 0:
        add("volatility_1y", "annVolatility", v, "ratio", scale=100.0)
    close, hi = _num(row, "closePrice"), _num(row, "week52High")
    if close and hi and close > 0 and hi > 0:
        add("pct_from_52w_high", "closePrice/week52High", close / hi - 1.0, "ratio")
    for k in (50, 200):
        v = _num(row, f"dma{k}")
        if v and v > 0:
            add(f"sma_{k}", f"dma{k}", v, "INR")
    return out


def score_metrics_for(row: dict, nifty_1y: float | None = None) -> dict[str, float]:
    """The score metrics (scoring metric ids, ratio units) Market Lens can state honestly for one row. 0 and null are placeholders,
    not values; return on equity, growth, beta and drawdown are never taken from Market Lens. relative_return_1y needs the Nifty 50's
    1-year return (a ratio) and is left out without it."""
    out: dict[str, float] = {}
    v = _num(row, "peRatio")
    if v and v > 0:
        out["pe_ttm"] = v
    v = _num(row, "pbRatio")
    if v and v > 0:
        out["pb"] = v
    v = _num(row, "debtToEquity")
    if v is not None and (v > 0 or (v == 0 and _num(row, "totalBorrowings") == 0)):
        out["debt_to_equity"] = v
    v = _num(row, "oneYearReturn")
    if v:
        out["return_1y"] = v / 100.0
        if nifty_1y is not None:
            out["relative_return_1y"] = v / 100.0 - nifty_1y
    v = _num(row, "annVolatility")
    if v and v > 0:
        out["volatility_1y"] = v / 100.0
    close, hi = _num(row, "closePrice"), _num(row, "week52High")
    if close and hi and close > 0 and hi > 0:
        out["pct_from_52w_high"] = close / hi - 1.0
    return out


def row_as_of(row: dict, now: datetime | None = None) -> date:
    return _stamp(row, now or datetime.now(timezone.utc))[0]


def sector_members(sym: str, rows: dict, min_sector: int = 8) -> tuple[list[str], str, str] | None:
    """Symbols in the target's Market Lens sector; if fewer than min_sector, its sub-sector. Returns (symbols, kind, name)
    with kind 'sector' or 'subSector', or None when the target has no row. The target is always included."""
    row = (rows or {}).get(sym)
    if not row:
        return None
    sector, sub = row.get("sector") or None, row.get("subSector") or None
    if sector:
        got = sorted(s for s, r in rows.items() if r.get("sector") == sector)
        if len(got) >= min_sector or not sub:
            return (got if sym in got else sorted(got + [sym])), "sector", sector
    if sub:
        got = sorted(s for s, r in rows.items() if r.get("subSector") == sub)
        return (got if sym in got else sorted(got + [sym])), "subSector", sub
    return None


def peer_factset(symbol: str, row: dict, now: datetime | None = None):
    """A minimal FactSet for one Market Lens row, so peers.py can treat it like any pool member.
    Entity industry = Market Lens sector (fine), sector = Market Lens subSector (broad)."""
    from indiafacts.models import Entity, FactSet

    now = now or datetime.now(timezone.utc)
    ent = Entity.from_ticker(symbol.upper().removesuffix(".NS") + ".NS").model_copy(update={
        "name": row.get("name"), "sector": row.get("subSector") or None, "industry": row.get("sector") or None})
    return FactSet(entity=ent, facts=[f for f in facts_for(symbol, row, now) if f.metric in ("market_cap", "pe_ttm", "pb")], retrieved_at=now)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="python -m indiafacts.marketlens", description="Fetch the Market Lens universe to a cache file.")
    p.add_argument("--out", type=Path, default=None, help="cache file to write (default: the cache path)")
    a = p.parse_args(argv)
    rows, problems = refresh(a.out)
    print(f"{len(rows)} stocks; {len(problems)} problem(s)" + ("".join(f"\n  {x}" for x in problems[:5])))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
