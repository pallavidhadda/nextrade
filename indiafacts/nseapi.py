"""Client for NSE's website data API, used with NSE's permission (educational use; see docs/DATA_PERMISSIONS.md).

Fetches, for one listed symbol, the OFFICIAL shareholding pattern (the filed XBRL) and the newest quarterly results (the filed XBRL),
which the existing parsers (shareholding.parse_shp, xbrl.facts_from_nse_xbrl) turn into Facts. This is our own code: endpoint
names are public website paths; no third-party client is used.

Manners: an honest User-Agent, a Referer, at least one second between requests, a 15 second timeout, retries only on 429/503
(at most two, with backoff), and an on-disk cache (list endpoints one day, XBRL files forever, since a filing never changes).
Nothing here raises to the caller: a failure comes back as an empty result plus a reason.
Switches: INDIAFACTS_NSE_API=0 turns everything off (live and the daily copy). INDIAFACTS_NSE_API_LIVE=0 turns only the live calls off.
Daily copy: NSE answers GitHub's runners but not every datacenter address, so the snapshot job also publishes, per symbol, a compact
<SYMBOL>.json of what it parsed (INDIAFACTS_NSE_COPY_OUT=<dir> writes it). INDIAFACTS_NSE_COPY_BASE=<url or file:// dir> says where to read it;
it is the fallback when a live call fails, and INDIAFACTS_NSE_COPY_FIRST=1 reads it before trying live. INDIAFACTS_NSE_BROWSER_HEADERS=1 (default off) sends browser-like headers and
warms up a cookie from the NSE home page, for use only if the API starts refusing the honest client. Education only; not advice.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from indiafacts import published

BASE = "https://www.nseindia.com/api"
HOME = "https://www.nseindia.com/"
ARCHIVE_HOST = "nsearchives.nseindia.com"
USER_AGENT = "NexTrade-research/0.1 (education; permitted use of NSE data)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
TIMEOUT = 15
MIN_GAP = 1.0
LIST_TTL = 24 * 3600
MAX_FILE = 20 * 1024 * 1024
MAX_RETRIES = 2
COPY_TTL = 3600
COPY_MISS_TTL = 300
COPY_VERSION = 1
COPY_ROW_KEYS = ("date", "pr_and_prgrp", "recordId", "xbrl", "broadcastDate", "submissionDate")
COPY_ROWS = 8
_copy_cache: dict[str, tuple[float, dict | None]] = {}   # url -> (time, document); shared by every client in this process
_last = {"t": 0.0}                       # time of the last request, shared by every client in this process


def enabled() -> bool:
    return os.environ.get("INDIAFACTS_NSE_API", "1").strip() != "0"


def live_enabled() -> bool:
    return enabled() and os.environ.get("INDIAFACTS_NSE_API_LIVE", "1").strip() != "0"


def copy_base() -> str:
    base = published.url("INDIAFACTS_NSE_COPY_BASE", "nse/")
    return base if not base or base.endswith("/") else base + "/"


def copy_first() -> bool:
    return os.environ.get("INDIAFACTS_NSE_COPY_FIRST", "0").strip() == "1" and bool(copy_base())


def copy_out() -> Path | None:
    out = os.environ.get("INDIAFACTS_NSE_COPY_OUT", "").strip()
    return Path(out) if out else None


def browser_headers() -> bool:
    return os.environ.get("INDIAFACTS_NSE_BROWSER_HEADERS", "0").strip() == "1"


def cache_dir() -> Path:
    return Path(os.environ.get("INDIAFACTS_NSE_CACHE") or Path.home() / ".indiafacts" / "nse_api")


def _date(text: str | None) -> date | None:
    for fmt in ("%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime((text or "").strip().title(), fmt).date()
        except ValueError:
            continue
    return None


class NseApi:
    def __init__(self, opener: Callable | None = None, cache: Path | None = None, sleep: Callable = time.sleep,
                 clock: Callable = time.time):
        self._opener = opener
        self._cache = Path(cache) if cache else None
        self._sleep, self._clock = sleep, clock
        self._warm = False
        self.reasons: list[str] = []         # why calls failed, for a notice
        self.ok = 0                          # successful network or cache answers
        self.copy_dates: list[date] = []     # as-of dates of daily copies actually used this run
        self._dead = ""                      # set when live NSE refused (403) or was unreachable: no more live calls from this client
        self._live: dict = {}                # what live calls produced, for save_copy

    # ---- transport ----------------------------------------------------------------------------------------------
    @property
    def cache(self) -> Path:
        return self._cache or cache_dir()

    def _open(self, req: Request):
        if self._opener is None:
            if browser_headers():
                self._opener = build_opener(HTTPCookieProcessor(CookieJar())).open
            else:
                self._opener = build_opener().open
        return self._opener(req, timeout=TIMEOUT)

    def _headers(self, accept: str) -> dict:
        if browser_headers():
            return {"User-Agent": BROWSER_UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9", "Referer": HOME}
        return {"User-Agent": USER_AGENT, "Accept": accept, "Referer": HOME}

    def _pace(self) -> None:
        wait = MIN_GAP - (self._clock() - _last["t"])
        if wait > 0:
            self._sleep(wait)
        _last["t"] = self._clock()

    def _request(self, url: str, accept: str) -> tuple[bytes | None, str]:
        """One polite GET. Returns (body, "") or (None, reason). Never raises."""
        if browser_headers() and not self._warm:
            self._warm = True
            try:
                self._pace()
                self._open(Request(HOME, headers=self._headers("text/html"))).read(2000)
            except Exception:
                pass                                           # a failed warm-up is not fatal; the real call decides
        if self._dead:
            return None, self._dead
        for attempt in range(MAX_RETRIES + 1):
            self._pace()
            try:
                resp = self._open(Request(url, headers=self._headers(accept)))
                body = resp.read(MAX_FILE + 1)
                if len(body) > MAX_FILE:
                    return None, "response larger than the size cap"
                return body, ""
            except HTTPError as exc:
                if exc.code in (429, 503) and attempt < MAX_RETRIES:
                    self._sleep(2 ** (attempt + 1))
                    continue
                if exc.code == 403:
                    self._dead = f"NSE answered HTTP {exc.code}"
                return None, f"NSE answered HTTP {exc.code}"
            except Exception as exc:                           # timeout, DNS, TLS, anything
                self._dead = f"NSE not reachable ({type(exc).__name__})"
                return None, self._dead
        return None, "NSE kept refusing"

    # ---- cached fetches -------------------------------------------------------------------------------------------
    def _key(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:24]

    def get_json(self, endpoint: str, params: dict, ttl: int = LIST_TTL):
        """(data, reason). data is None on failure; a stale cached copy is used when the live call fails."""
        if not enabled():
            return None, "NSE API disabled (INDIAFACTS_NSE_API=0)"
        if not live_enabled():
            self.reasons.append("live NSE access is off (INDIAFACTS_NSE_API_LIVE=0)")
            return None, self.reasons[-1]
        url = f"{BASE}/{endpoint}?{urlencode(params)}"
        path = self.cache / f"{endpoint}_{self._key(url)}.json"
        cached = None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if cached and self._clock() - cached.get("fetched", 0) < ttl:
            self.ok += 1
            return cached.get("data"), ""
        body, why = self._request(url, "application/json")
        data = None
        if body is not None:
            try:
                data = json.loads(body.decode("utf-8", "replace"))
            except ValueError:
                why = "NSE did not return JSON"
        if data is None:
            self.reasons.append(why)
            if cached:
                self.ok += 1
                return cached.get("data"), f"{why}; used a cached copy"
            return None, why
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"fetched": self._clock(), "url": url, "data": data}), encoding="utf-8")
        except OSError:
            pass
        self.ok += 1
        return data, ""

    def get_file(self, url: str):
        """(path, reason) for an NSE archive file. Cached forever by URL. Never raises."""
        if not enabled():
            return None, "NSE API disabled (INDIAFACTS_NSE_API=0)"
        if not live_enabled():
            self.reasons.append("live NSE access is off (INDIAFACTS_NSE_API_LIVE=0)")
            return None, self.reasons[-1]
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != ARCHIVE_HOST:
            return None, "not an NSE archive URL"
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(parsed.path).name)[:120] or "file.xml"
        path = self.cache / "files" / f"{self._key(url)[:8]}_{name}"
        if path.exists() and path.stat().st_size > 0:
            self.ok += 1
            return path, ""
        body, why = self._request(url, "application/xml,text/xml,*/*")
        if body is None:
            self.reasons.append(why)
            return None, why
        if not body.lstrip()[:1] == b"<":
            self.reasons.append("NSE did not return an XML file")
            return None, "NSE did not return an XML file"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(body)
            tmp.replace(path)
        except OSError as exc:
            return None, f"could not cache the file ({type(exc).__name__})"
        self.ok += 1
        return path, ""

    # ---- shareholding -----------------------------------------------------------------------------------------------
    def shareholding_rows(self, symbol: str):
        data, why = self.get_json("corporate-share-holdings-master", {"index": "equities", "symbol": symbol.upper()})
        rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
        rows = [r for r in rows if _date(r.get("date"))]
        rows.sort(key=lambda r: _date(r["date"]), reverse=True)
        if not rows and not why:
            why = "NSE returned no shareholding rows"
        return rows, why

    def latest_shareholding(self, symbol: str):
        """(Shareholding | None, rows, reason): live from NSE, or from the daily copy (first when INDIAFACTS_NSE_COPY_FIRST=1,
        otherwise when the live call fails)."""
        if copy_first():
            got = self._copy_shareholding(symbol)
            if got[0] is not None:
                return got
        sh, rows, why = self._live_shareholding(symbol) if live_enabled() else (None, [], "live NSE access is off (INDIAFACTS_NSE_API_LIVE=0)")
        if sh is not None:
            self._live["sh"] = (sh, rows)
            return sh, rows, why
        if not copy_first() and enabled():
            got = self._copy_shareholding(symbol)
            if got[0] is not None:
                return got
        return sh, rows, why

    def _live_shareholding(self, symbol: str):
        """The newest row's XBRL parsed with the existing SHP parser."""
        from indiafacts.shareholding import parse_shp

        rows, why = self.shareholding_rows(symbol)
        if not rows:
            return None, rows, why
        top = rows[0]
        if not top.get("xbrl"):
            return None, rows, "newest shareholding row has no XBRL file"
        path, why = self.get_file(top["xbrl"])
        if path is None:
            return None, rows, why
        try:
            sh = parse_shp(path, source=f"NSE API {Path(path).name} (filed {top.get('broadcastDate') or top.get('submissionDate') or ''})".strip())
        except (ValueError, OSError) as exc:
            return None, rows, f"shareholding file not readable: {exc}"
        sh.symbol = sh.symbol or symbol.upper()
        sh.as_on = sh.as_on or _date(top.get("date"))
        return sh, rows, ""

    # ---- quarterly results ----------------------------------------------------------------------------------------------
    def result_filings(self, symbol: str) -> tuple[list[dict], str]:
        """Quarterly results filings, newest quarter first, from both NSE listings: the integrated-filing one (recent quarters)
        and the older results one. One entry per (quarter end, basis); the latest broadcast wins. Entries:
        {end, basis ('consolidated'|'standalone'), xbrl, filed, audited, origin}."""
        sym = symbol.upper()
        found: dict[tuple, dict] = {}
        reasons = []

        def keep(end, basis, xbrl, filed, audited, origin):
            if not (end and xbrl):
                return
            k = (end, basis)
            if k not in found or (filed or date.min) > (found[k]["filed"] or date.min):
                found[k] = {"end": end, "basis": basis, "xbrl": xbrl, "filed": filed, "audited": audited, "origin": origin}

        data, why = self.get_json("integrated-filing-results", {"index": "equities", "period_ended": "all",
                                                                  "type": "Integrated Filing- Financials", "symbol": sym})
        rows = data.get("data") if isinstance(data, dict) else None
        if rows is None:
            reasons.append(why or "integrated-filing list unreadable")
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            basis = "consolidated" if str(r.get("consolidated", "")).lower().startswith("consol") else "standalone"
            keep(_date(r.get("qe_Date")), basis, r.get("xbrl"), _date(r.get("broadcast_Date")), r.get("audited", ""), "integrated filing")
        data, why = self.get_json("corporates-financial-results", {"index": "equities", "period": "Quarterly", "symbol": sym})
        if isinstance(data, list):
            for r in data:
                if not isinstance(r, dict):
                    continue
                basis = "standalone" if str(r.get("consolidated", "")).lower().startswith("non") else "consolidated"
                keep(_date(r.get("toDate")), basis, r.get("xbrl"), _date(r.get("broadcastDate") or r.get("filingDate")),
                     r.get("audited", ""), "results filing")
        elif why:
            reasons.append(why)
        out = sorted(found.values(), key=lambda e: (e["end"], e["basis"] == "consolidated"), reverse=True)
        return out, ("; ".join(dict.fromkeys(reasons)) if not out else "")

    def _live_results(self, symbol: str, n: int = 5):
        """([(entry, path)], notes): the newest n quarters' XBRL files. Consolidated when the company has any, else standalone (noted).
        One basis only, so year-on-year compares like with like."""
        entries, why = self.result_filings(symbol)
        if not entries:
            return [], [why or "NSE listed no quarterly results filings"]
        cons = [e for e in entries if e["basis"] == "consolidated"]
        chosen, notes = (cons, []) if cons else ([e for e in entries if e["basis"] == "standalone"],
                                                 ["no consolidated results filings found; standalone results used"])
        pairs, failed = [], 0
        for e in chosen[:n]:
            p, w = self.get_file(e["xbrl"])
            if p is None:
                failed += 1
                continue
            pairs.append((e, p))
        if failed:
            notes.append(f"{failed} of {min(n, len(chosen))} results files could not be downloaded")
        return pairs, notes

    def quarterly_xbrl(self, symbol: str, n: int = 5):
        """(paths, notes) of the newest n quarters' XBRL files, live from NSE."""
        pairs, notes = self._live_results(symbol, n)
        return [p for _, p in pairs], notes

    def quarterly_filings(self, symbol: str, n: int = 5):
        """(list of parsed FactSets, notes): the quarterly results as Facts, live or from the daily copy (same order as latest_shareholding)."""
        if copy_first():
            got = self._copy_results(symbol)
            if got[0]:
                return got
        parsed, notes = [], []
        if live_enabled():
            from indiafacts.xbrl import facts_from_nse_xbrl

            pairs, notes = self._live_results(symbol, n)
            kept = []
            for e, p in pairs:
                try:
                    parsed.append(facts_from_nse_xbrl(p))
                    kept.append((e, parsed[-1]))
                except (ValueError, OSError) as exc:
                    notes.append(f"skipped filing {Path(p).name}: {exc}")
            if kept:
                self._live["results"] = kept
        else:
            self.reasons.append("live NSE access is off (INDIAFACTS_NSE_API_LIVE=0)")
        if not parsed and not copy_first() and enabled():
            got = self._copy_results(symbol)
            if got[0]:
                return got
        return parsed, notes

    # ---- the daily copy -------------------------------------------------------------------------------------------------
    def _copy_doc(self, symbol: str) -> dict | None:
        """The published <SYMBOL>.json, from INDIAFACTS_NSE_COPY_BASE; one hour in memory. Never raises."""
        base = copy_base()
        if not base or not enabled():
            return None
        sym = re.sub(r"[^A-Z0-9&_-]", "", symbol.upper().removesuffix(".NS"))
        url = f"{base}{sym}.json"
        hit = _copy_cache.get(url)
        now = self._clock()
        if hit and now - hit[0] < (COPY_TTL if hit[1] is not None else COPY_MISS_TTL):
            return hit[1]
        doc = None
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT) as r:
                raw = r.read(MAX_FILE + 1)
            if len(raw) <= MAX_FILE:
                d = json.loads(raw.decode("utf-8"))
                if isinstance(d, dict) and d.get("version") == COPY_VERSION and d.get("symbol") == sym and _date(_iso_to_nse(d.get("generated_at"))):
                    doc = d
        except Exception:
            doc = None
        if doc is None:
            self.reasons.append("no daily copy of NSE filings available")
        _copy_cache[url] = (now, doc)
        return doc

    def _copy_asof(self, doc: dict) -> date:
        d = date.fromisoformat(str(doc["generated_at"])[:10])
        self.copy_dates.append(d)
        return d

    def _copy_shareholding(self, symbol: str):
        from indiafacts.shareholding import Shareholding

        try:
            doc = self._copy_doc(symbol)
            blk = (doc or {}).get("shareholding")
            if not blk:
                return None, [], "no shareholding in the daily copy"
            asof = self._copy_asof(doc)
            f = dict(blk["sh"])
            f["as_on"] = date.fromisoformat(f["as_on"]) if f.get("as_on") else None
            sh = Shareholding(**f)
            sh.source = f"{sh.source} (daily copy as of {asof})"
            rows = [r for r in blk.get("rows", []) if isinstance(r, dict) and _date(r.get("date"))]
            self.ok += 1
            return sh, rows, ""
        except Exception:
            return None, [], "daily copy shareholding unreadable"

    def _copy_results(self, symbol: str):
        from indiafacts.models import Entity, Fact, FactSet, FilingMeta

        try:
            doc = self._copy_doc(symbol)
            if not (doc or {}).get("results"):
                return [], ["no quarterly results in the daily copy"]
            asof = self._copy_asof(doc)
            out = []
            for r in doc["results"]:
                common = r["common"]
                facts = []
                for f in r["facts"]:
                    d = {**common, **f}
                    d.setdefault("reported_value", d["value"])
                    d.setdefault("reported_unit", d["unit"])
                    d["evidence"] = (f"{r['filing']['document']} | {d.get('evidence', '')}"
                                     f" | official NSE filing {r['xbrl_url']}; daily copy as of {asof}")
                    v = Fact.model_validate({**d, "fact_id": ""})
                    facts.append(v.model_copy(update={"fact_id": Fact.compute_id(v.entity_key, v.metric, v.period_end, str(v.period_type), v.source)}))
                out.append(FactSet(entity=Entity.model_validate(r["entity"]), facts=facts, retrieved_at=common["retrieved_at"],
                                   filings=[FilingMeta.model_validate(r["filing"])]))
            self.ok += 1
            return out, []
        except Exception:
            return [], ["daily copy results unreadable"]

    def copy_notice(self) -> str:
        if not self.copy_dates:
            return ""
        return (f"official NSE filings from the daily copy as of {min(self.copy_dates)} "
                "(NSE does not answer this server directly)")

    def save_copy(self, symbol: str, out: Path | None = None) -> Path | None:
        """Write what live calls produced this run to <out>/<SYMBOL>.json (INDIAFACTS_NSE_COPY_OUT). A part live did not produce keeps the
        earlier copy's version of it. Writes nothing when live produced nothing. Never raises."""
        try:
            out = out or copy_out()
            if out is None or not self._live:
                return None
            sym = symbol.upper().removesuffix(".NS")
            path = Path(out) / f"{sym}.json"
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                old = old if isinstance(old, dict) and old.get("version") == COPY_VERSION else {}
            except (OSError, ValueError):
                old = {}
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            doc = {"version": COPY_VERSION, "symbol": sym, "generated_at": now,
                   "shareholding": old.get("shareholding"), "results": old.get("results") or []}
            if "sh" in self._live:
                sh, rows = self._live["sh"]
                f = asdict(sh)
                f["as_on"] = sh.as_on.isoformat() if sh.as_on else None
                doc["shareholding"] = {"as_on": f["as_on"], "sh": f,
                                       "rows": [{k: r[k] for k in COPY_ROW_KEYS if k in r} for r in rows[:COPY_ROWS]]}
            if "results" in self._live:
                doc["results"] = [_pack_result(e, fs) for e, fs in self._live["results"]]
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.part")
            tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            return path
        except Exception:
            return None


def _iso_to_nse(text) -> str:
    try:
        return date.fromisoformat(str(text)[:10]).strftime("%d-%b-%Y")
    except ValueError:
        return ""


def _pack_result(entry: dict, fs) -> dict:
    """One results filing, compact: the fields every fact shares are written once under `common`; fact_id is recomputed on read."""
    doc = fs.filings[0].document + " | "
    dumps = [f.model_dump(mode="json", exclude_defaults=True, exclude={"fact_id"}) for f in fs.facts]
    for d in dumps:                                    # three fields that repeat others: the file name, the value and the unit
        if d.get("evidence", "").startswith(doc):
            d["evidence"] = d["evidence"][len(doc):]
        if d.get("reported_value") == d.get("value"):
            d.pop("reported_value", None)
        if d.get("reported_unit") == d.get("unit"):
            d.pop("reported_unit", None)
    keys = set(dumps[0]) if dumps else set()
    common = {k: dumps[0][k] for k in keys if all(d.get(k) == dumps[0][k] for d in dumps)}
    common["retrieved_at"] = fs.retrieved_at.isoformat()
    for k in ("metric", "value", "period_end", "period_type", "unit"):      # always per fact
        common.pop(k, None)
    return {"period": entry["end"].isoformat(), "basis": entry["basis"], "audited": entry.get("audited", ""),
            "filing_date": entry["filed"].isoformat() if entry.get("filed") else None, "xbrl_url": entry["xbrl"],
            "entity": fs.entity.model_dump(mode="json", exclude_defaults=True), "filing": fs.filings[0].model_dump(mode="json", exclude_defaults=True),
            "common": common, "facts": [{k: v for k, v in d.items() if k not in common} for d in dumps]}
