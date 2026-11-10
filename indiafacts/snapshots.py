"""Daily snapshots: precompute analyses on a scheduled job, serve them instantly from the API.
The job writes <dir>/<TICKER>.json (the API-shaped summary), <TICKER>.html (the report) and index.json.
The API side reads them over HTTP from INDIAFACTS_SNAPSHOT_BASE (an orphan git branch on raw.githubusercontent.com).
Education only; not financial, investment or trading advice."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote

DATA = Path(__file__).parent / "data"
EXAMPLES = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS"]           # the web app's example chips
PROBE_TICKERS = ["RELIANCE.NS", "TCS.NS"]
DEFAULT_MAX_AGE_DAYS = 4
CLIENT_TTL_SECONDS = 3600


def norm(ticker: str) -> str:
    t = ticker.strip().upper()
    return t if t.endswith((".NS", ".BO")) else t + ".NS"


def safe_name(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", norm(ticker))


UNIVERSES = ("nifty50", "tej500")


def tej500_tickers(store=None, today: date | None = None) -> list[str]:
    """Top 500 by 63-day average traded value (NSE liquidity rank, not market value) from TejHQ's open parquet; no key needed.
    Raises on any download or parse failure; the caller decides the fallback."""
    from indiafacts.tej import TejStore, universe_members

    df = (store or TejStore()).load("universe/nse_liquid.parquet")
    fund = re.compile(r"\b(ETF|BEES|FUND|NIFTY|SENSEX|LIQUID|GOLD|SILVER)\b|BEES$|ETF$|AML-", re.I)          # exchange-traded funds are not companies
    return [norm(m.symbol) for m in universe_members(df, today or date.today(), 500) if not (fund.search(m.name) or fund.search(m.symbol))]


def load_tickers(extra: list[str] | None = None, universe: str = "nifty50", tej_loader: Callable[[], list[str]] | None = None,
                 log=print) -> list[str]:
    """Nifty 50 and the example chips first (so they finish first), then the optional wider universe, then extras."""
    out: list[str] = []
    for line in (DATA / "nifty50.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            out.append(norm(line))
    out += [norm(t) for t in EXAMPLES]
    if universe == "tej500":
        try:
            out += (tej_loader or tej500_tickers)()
        except Exception as exc:                                                     # the Nifty 50 run still goes ahead
            log(f"tej500 universe unavailable ({type(exc).__name__}: {str(exc)[:120]}); using Nifty 50 plus examples only")
    out += [norm(t) for t in (extra or [])]
    return list(dict.fromkeys(out))


def summary_as_of(summary: dict) -> str | None:
    s = ((summary.get("stamp") or {}).get("as_of")) or str(summary.get("retrieved_at") or "")[:10]
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def is_fresh(entry: dict | None, today: date | None = None, max_age_days: int | None = None) -> bool:
    """An index entry is servable when the run succeeded and its as_of is at most max_age_days calendar days old."""
    if not entry or not entry.get("ok") or not entry.get("as_of"):
        return False
    if max_age_days is None:
        max_age_days = int(os.environ.get("INDIAFACTS_SNAPSHOT_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS))
    try:
        age = ((today or date.today()) - date.fromisoformat(entry["as_of"])).days
    except ValueError:
        return False
    return 0 <= age <= max_age_days


def _commit() -> str:
    from indiafacts.stamp import app_commit

    return app_commit()


def snapshot_one(ticker: str, out_dir: Path, runner: Callable, commit: str, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict:
    """Analyse one ticker and write its files. Returns its index entry; never raises."""
    entry = {"as_of": None, "ok": False, "error": None, "generated_at": now().isoformat(timespec="seconds"), "commit": commit}
    try:
        res = runner({"ticker": ticker}, lambda p: None)
        summary = res["summary"]
        entry["as_of"] = summary_as_of(summary)
        if not summary.get("key_facts"):
            raise ValueError("no key metrics in the result")
        (out_dir / f"{safe_name(ticker)}.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
        (out_dir / f"{safe_name(ticker)}.html").write_text(res["html"], encoding="utf-8")
        entry["ok"] = True
    except Exception as exc:                                                         # one bad ticker must not stop the run
        detail = getattr(exc, "detail", None)
        entry["error"] = (str(detail or exc)[:300] or type(exc).__name__)
    return entry


def run_snapshots(tickers: list[str], out_dir: Path, runner: Callable, delay: float = 5.0, sleep=time.sleep, log=print) -> dict:
    """Sequential and polite. A failed ticker keeps its last good files and entry, with the failure noted beside it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    idx_path = out_dir / "index.json"
    try:
        index = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {}
    commit = _commit()
    for i, t in enumerate(tickers):
        if i:
            sleep(delay)
        e = snapshot_one(t, out_dir, runner, commit)
        old = index.get(t) or {}
        failed = not e["ok"]
        if failed and old.get("ok"):
            e = {**old, "last_error": e["error"], "last_attempt": e["generated_at"]}
        index[t] = e
        log(f"[{i + 1}/{len(tickers)}] {t}: " + (f"FAILED {e.get('last_error') or e['error']}" if failed else f"ok as_of {e['as_of']}"))
        idx_path.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
    return index


def failure_rate(index: dict, tickers: list[str]) -> float:
    """Share of tickers whose latest attempt failed (a kept older snapshot still counts as a failure)."""
    if not tickers:
        return 0.0
    bad = sum(1 for t in tickers if not (index.get(t) or {}).get("ok") or (index.get(t) or {}).get("last_error"))
    return bad / len(tickers)


def probe(runner: Callable, tickers: list[str] | None = None, log=print) -> bool:
    """Fetch 1-2 tickers and say plainly whether Yahoo works from this machine."""
    good = 0
    for t in tickers or PROBE_TICKERS:
        try:
            res = runner({"ticker": t}, lambda p: None)
            kf = res["summary"].get("key_facts") or []
            log(f"PROBE {t}: {len(kf)} key metrics present, as_of {summary_as_of(res['summary'])}")
            good += bool(kf)
        except Exception as exc:
            log(f"PROBE {t}: FAILED {str(exc)[:200]}")
    ok = good > 0
    log("PROBE VERDICT: Yahoo WORKS from this machine (key metrics present: yes)" if ok
        else "PROBE VERDICT: Yahoo does NOT work from this machine (key metrics present: no)")
    return ok


class SnapshotClient:
    """Read side for the API: index and per-ticker files from a base URL, cached in memory for about an hour."""

    def __init__(self, base: str, fetch: Callable[[str], bytes] | None = None, ttl: float = CLIENT_TTL_SECONDS, clock=time.time):
        self.base, self.ttl, self.clock = base.rstrip("/"), ttl, clock
        self._fetch = fetch or self._http
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _http(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"user-agent": "nextrade-snapshots"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read()

    def _get(self, name: str, as_json: bool):
        now = self.clock()
        with self._lock:
            hit = self._cache.get(name)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        raw = self._fetch(f"{self.base}/{quote(name)}")
        val = json.loads(raw) if as_json else raw.decode("utf-8")
        with self._lock:
            self._cache[name] = (now, val)
        return val

    def lookup(self, ticker: str, today: date | None = None, max_age_days: int | None = None) -> dict | None:
        """Return {"summary", "html", "as_of"} for a fresh snapshot, else None. Never raises."""
        try:
            t = norm(ticker)
            entry = self._get("index.json", True).get(t)
            if not is_fresh(entry, today, max_age_days):
                return None
            from indiafacts.summary import REPORT_VERSION

            summary = self._get(f"{safe_name(t)}.json", True)
            if int((summary or {}).get("report_version") or 0) < REPORT_VERSION:
                return None                    # built by older code: run a fresh analysis rather than show outdated content
            return {"summary": summary, "html": self._get(f"{safe_name(t)}.html", False), "as_of": entry["as_of"]}
        except Exception:
            return None


def client_from_env() -> SnapshotClient | None:
    base = os.environ.get("INDIAFACTS_SNAPSHOT_BASE", "").strip()
    return SnapshotClient(base) if base else None


def _prepare_marketlens(out: Path, log=print) -> None:
    """Fetch NSE Market Lens once (58 requests, 1 s apart) into <out>/marketlens.json, published with the reports. Every analysis
    in this run then reads that file, so NSE is not called per ticker. If the fetch fails, yesterday's file (if any) is kept."""
    from indiafacts import marketlens

    if not marketlens.enabled():
        return
    out.mkdir(parents=True, exist_ok=True)
    path = out / "marketlens.json"
    rows, problems = marketlens.refresh(path)
    log(f"marketlens: {len(rows)} stocks, {len(problems)} problem(s)" + (f" ({problems[0]})" if problems else ""))
    if path.exists():
        os.environ["INDIAFACTS_MARKETLENS_URL"] = path.resolve().as_uri()
        os.environ["INDIAFACTS_MARKETLENS_LIVE"] = "0"       # one fetch per run, not one per ticker
    else:
        os.environ["INDIAFACTS_MARKETLENS"] = "0"


def _prepare_nse_copy(out: Path) -> Path:
    """The snapshot job fetches NSE live (it works from GitHub's runners) and publishes what it parsed as <out>/nse/<SYMBOL>.json for servers
    NSE refuses. Yesterday's copy (already in <out>/nse from the snapshots branch) is the fallback if NSE fails during this run."""
    d = out / "nse"
    d.mkdir(parents=True, exist_ok=True)
    os.environ["INDIAFACTS_NSE_COPY_OUT"] = str(d.resolve())
    os.environ["INDIAFACTS_NSE_COPY_BASE"] = d.resolve().as_uri() + "/"
    os.environ.pop("INDIAFACTS_NSE_COPY_FIRST", None)            # live first here, always
    os.environ.pop("INDIAFACTS_NSE_API_LIVE", None)
    return d


def _default_pool_builder() -> Callable[[str], object]:
    """The same member build the live pool path used: Yahoo facts and prices, no per-member NSE filings."""
    from indiafacts.cli import _MemoPrices
    from indiafacts.pipeline import build_factset
    from indiafacts.prices import YfinancePriceClient

    memo = _MemoPrices(YfinancePriceClient())
    return lambda t: build_factset(t, prices=True, price_client=memo, tej=True, marketlens=True, marketlens_live=False, nse_api=False)


def _prepare_pool_metrics(out: Path, tickers: list[str], builder: Callable[[str], object] | None = None, log=print) -> Path | None:
    """Stage 1: every score metric for the whole universe, from the cached per-ticker fetch, into <out>/pool_metrics.json (published with
    the reports). Stage 2 (the reports) reads it through INDIAFACTS_POOL_METRICS_URL, so no report fetches pool members. If nothing
    could be built, yesterday's file (if any) is kept. Never raises."""
    from indiafacts import poolstore

    try:
        out.mkdir(parents=True, exist_ok=True)
        path = out / "pool_metrics.json"
        store = poolstore.build(tickers, builder or _default_pool_builder(), log=log)
        n = store["meta"]["n"]
        log(f"pool_metrics: {n} companies")
        if n:
            poolstore.write(store, path)
        if path.exists():
            os.environ["INDIAFACTS_POOL_METRICS_URL"] = path.resolve().as_uri()
            return path
    except Exception as exc:
        log(f"pool_metrics: failed ({type(exc).__name__}: {str(exc)[:160]})")
    return None


DRIFT_FILES = {"marketlens": "marketlens.json", "pool_metrics": "pool_metrics.json"}


def backup_previous(out: Path, dest: Path) -> Path:
    """Copy yesterday's published marketlens.json / pool_metrics.json aside before today's fetch overwrites them."""
    import shutil

    dest.mkdir(parents=True, exist_ok=True)
    for name in DRIFT_FILES.values():
        if (out / name).exists():
            shutil.copy2(out / name, dest / name)
    return dest


def _json_or_none(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def drift_gate(out: Path, prev_dir: Path, anchors: dict | None = None, log=print) -> dict:
    """Run the source drift check on today's marketlens.json and pool_metrics.json against yesterday's copies (prev_dir).
    A breaking source keeps yesterday's file (or publishes none if there was none). Placeholder pool metrics are stripped from the
    published file, and placeholder Market Lens fields are skipped through INDIAFACTS_DRIFT_REPORT. Writes <out>/drift_report.json; never raises."""
    from indiafacts import drift

    try:
        ml, pool = _json_or_none(out / "marketlens.json"), _json_or_none(out / "pool_metrics.json")
        if anchors is None:
            anchors = {t.removesuffix(".NS"): (m.get("market_cap") or {}).get("value") for t, m in ((pool or {}).get("metrics") or {}).items()
                       if isinstance(m, dict) and isinstance(m.get("market_cap"), dict)} or None
        report = drift.build_report(ml, _json_or_none(prev_dir / "marketlens.json"), pool, _json_or_none(prev_dir / "pool_metrics.json"),
                                    anchors=anchors)
    except Exception as exc:                                                          # a broken checker must not stop the daily job
        report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "warning", "disabled_fields": [],
                  "checks": [{"source": "drift", "check": "checker", "field": None, "severity": "warning", "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}]}
    bad = drift.breaking_sources(report)
    for source, name in DRIFT_FILES.items():
        if source not in bad:
            continue
        kept = prev_dir / name
        if kept.exists():
            (out / name).write_bytes(kept.read_bytes())
            log(f"drift: {source} is breaking; kept yesterday's {name}")
        else:
            (out / name).unlink(missing_ok=True)
            log(f"drift: {source} is breaking and there is no earlier {name}; none published")
    pool_now = _json_or_none(out / "pool_metrics.json")
    if "pool_metrics" not in bad and pool_now and any(d.startswith("pool_metrics.") for d in report.get("disabled_fields", [])):
        from indiafacts import poolstore

        poolstore.write(drift.strip_disabled_pool(pool_now, report["disabled_fields"]), out / "pool_metrics.json")
    (out / "drift_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    os.environ["INDIAFACTS_DRIFT_REPORT"] = str((out / "drift_report.json").resolve())
    if not (out / "marketlens.json").exists():
        os.environ["INDIAFACTS_MARKETLENS"] = "0"
    if not (out / "pool_metrics.json").exists():
        os.environ.pop("INDIAFACTS_POOL_METRICS_URL", None)
    log(f"drift: {report['status']} ({len(report['checks'])} finding(s), {len(report['disabled_fields'])} field(s) not scored)")
    mark_index(out, report)
    return report


def record_gaps(out: Path, tickers: list[str], index: dict, yesterday: dict | None, log=print) -> dict | None:
    """Gaps per published report into drift_report.json (`gaps`, plus a gaps_per_report check that is breaking on a sharp rise
    since yesterday, which opens a "Source drift: reports" issue). Never raises."""
    from indiafacts import drift

    try:
        summaries = {}
        for t in tickers:
            if (index.get(t) or {}).get("ok"):
                s = _json_or_none(out / f"{safe_name(t)}.json")
                if isinstance(s, dict):
                    summaries[t] = s
        report = _json_or_none(out / "drift_report.json") or {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "ok", "checks": [], "disabled_fields": []}
        report = drift.add_gap_stats(report, summaries, yesterday)
        (out / "drift_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        mark_index(out, report)
        g = report["gaps"]
        if g.get("reports"):
            log(f"gaps: median {g['median']:g} per report, {g['share_over']:.0%} of {g['reports']} reports have more than {g['over']}")
        return report
    except Exception as exc:
        log(f"gaps: not recorded ({type(exc).__name__})")
        return None


def mark_index(out: Path, report: dict) -> None:
    """index.json gets a `_meta` entry (not a ticker) so readers can see today's drift status."""
    from indiafacts import drift

    idx = _json_or_none(out / "index.json")
    idx = idx if isinstance(idx, dict) else {}
    idx["_meta"] = {"drift_status": report["status"], "drift_checked_at": report["generated_at"],
                    "drift_breaking": drift.breaking_sources(report)}
    (out / "index.json").write_text(json.dumps(idx, indent=1, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None, runner: Callable | None = None, sleep=time.sleep) -> int:
    p = argparse.ArgumentParser(prog="python -m indiafacts.snapshots", description="Precompute analysis snapshots (education only).")
    p.add_argument("--out", default="snapshots", help="output directory")
    p.add_argument("--tickers", default="", help="comma-separated tickers to run instead of the default list")
    p.add_argument("--probe", action="store_true", help="fetch 1-2 tickers and say whether Yahoo works from this machine")
    p.add_argument("--delay", type=float, default=5.0, help="seconds between tickers")
    p.add_argument("--max-fail-pct", type=float, default=float(os.environ.get("SNAPSHOT_MAX_FAIL_PCT", "30")), help="exit 1 when more than this percent failed")
    p.add_argument("--universe", choices=UNIVERSES, default="nifty50", help="nifty50 (default) or tej500: also the top 500 by traded value from TejHQ's open data")
    p.add_argument("--limit", type=int, default=0, help="only the first N tickers (testing)")
    a = p.parse_args(argv)
    real_runner = runner is None
    if runner is None:
        from indiafacts.runner import subprocess_runner as runner
    given = [norm(t) for t in a.tickers.split(",") if t.strip()]
    if a.probe:
        return 0 if probe(runner, given[:2] or None) else 1
    tickers = given or load_tickers(universe=a.universe)
    if a.limit:
        tickers = tickers[:a.limit]
    prev_gaps = (_json_or_none(Path(a.out) / "drift_report.json") or {}).get("gaps")      # yesterday's, before it is overwritten
    if real_runner:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            prev = backup_previous(Path(a.out), Path(tmp))
            _prepare_marketlens(Path(a.out))
            _prepare_pool_metrics(Path(a.out), tickers)
            drift_gate(Path(a.out), prev)
        _prepare_nse_copy(Path(a.out))
    index = run_snapshots(tickers, Path(a.out), runner, a.delay, sleep)
    if real_runner:
        record_gaps(Path(a.out), tickers, index, prev_gaps)
    rate = failure_rate(index, tickers) * 100
    print(f"{len(tickers)} tickers, {rate:.0f}% failed (limit {a.max_fail_pct:.0f}%)", file=sys.stderr)
    return 1 if rate > a.max_fail_pct else 0


if __name__ == "__main__":
    raise SystemExit(main())
