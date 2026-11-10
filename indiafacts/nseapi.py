"""Client for NSE's website data API, used with NSE's permission (educational use; see docs/DATA_PERMISSIONS.md).

Fetches, for one listed symbol, the OFFICIAL shareholding pattern (the filed XBRL) and the newest quarterly results (the filed XBRL),
which the existing parsers (shareholding.parse_shp, xbrl.facts_from_nse_xbrl) turn into Facts. This is our own code: endpoint
names are public website paths; no third-party client is used.

Manners: an honest User-Agent, a Referer, at least one second between requests, a 15 second timeout, retries only on 429/503
(at most two, with backoff), and an on-disk cache (list endpoints one day, XBRL files forever, since a filing never changes).
Nothing here raises to the caller: a failure comes back as an empty result plus a reason.
Switches: INDIAFACTS_NSE_API=0 turns everything off. INDIAFACTS_NSE_BROWSER_HEADERS=1 (default off) sends browser-like headers and
warms up a cookie from the NSE home page, for use only if the API starts refusing the honest client. Education only; not advice.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, datetime
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

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
_last = {"t": 0.0}                       # time of the last request, shared by every client in this process


def enabled() -> bool:
    return os.environ.get("INDIAFACTS_NSE_API", "1").strip() != "0"


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
                return None, f"NSE answered HTTP {exc.code}"
            except Exception as exc:                           # timeout, DNS, TLS, anything
                return None, f"NSE not reachable ({type(exc).__name__})"
        return None, "NSE kept refusing"

    # ---- cached fetches -------------------------------------------------------------------------------------------
    def _key(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:24]

    def get_json(self, endpoint: str, params: dict, ttl: int = LIST_TTL):
        """(data, reason). data is None on failure; a stale cached copy is used when the live call fails."""
        if not enabled():
            return None, "NSE API disabled (INDIAFACTS_NSE_API=0)"
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
        """(Shareholding | None, rows, reason): the newest row's XBRL parsed with the existing SHP parser."""
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

    def quarterly_xbrl(self, symbol: str, n: int = 5):
        """(paths, notes): the newest n quarters' XBRL files. Consolidated when the company has any, else standalone (noted).
        One basis only, so year-on-year compares like with like."""
        entries, why = self.result_filings(symbol)
        if not entries:
            return [], [why or "NSE listed no quarterly results filings"]
        cons = [e for e in entries if e["basis"] == "consolidated"]
        chosen, notes = (cons, []) if cons else ([e for e in entries if e["basis"] == "standalone"],
                                                 ["no consolidated results filings found; standalone results used"])
        paths, failed = [], 0
        for e in chosen[:n]:
            p, w = self.get_file(e["xbrl"])
            if p is None:
                failed += 1
                continue
            paths.append(p)
        if failed:
            notes.append(f"{failed} of {min(n, len(chosen))} results files could not be downloaded")
        return paths, notes
