"""Shared comparison data: every score metric for every company in the snapshot universe, computed once a day with the same
extraction rules scoring uses (scoring.extract_facts), published as pool_metrics.json and read back at analysis time so a live
run never fetches the comparison companies one by one.

File shape: {"meta": {generated_at, commit, policy_hash, n}, "metrics": {"TCS.NS": {metric: {value, source, as_of}}, "^NSEI": {"return_1y": {...}}}}.
load() never raises. Education only; not financial advice."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

NIFTY = "^NSEI"
URL_TTL = 3600
POLICY_PATH = Path(__file__).parent / "data" / "source_policy.json"
_mem: dict = {"key": None, "at": 0.0, "store": None}
_lock = threading.Lock()


def local_path() -> Path:
    return Path.home() / ".indiafacts" / "pool_metrics.json"


def policy_hash() -> str:
    try:
        return hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()[:12]
    except OSError:
        return "unknown"


def _entry(value: float, source: str, as_of: date) -> dict:
    return {"value": round(float(value), 8), "source": source, "as_of": as_of.isoformat()}


def metrics_for(fs, cfg=None, as_of: date | None = None, now: datetime | None = None) -> dict[str, dict]:
    """{metric: {value, source, as_of}} for every score metric scoring would use for this company."""
    from indiafacts.scoring import extract_facts, load_score_config

    now = now or datetime.now(timezone.utc)
    facts, _ = extract_facts(fs, cfg or load_score_config(strict=False), as_of or now.date(), now)
    return {m: _entry(f.value, f.source, f.period_end) for m, f in facts.items()}


def nifty_return_1y(fs) -> dict | None:
    """Nifty 50's 1-year return, implied by a company's return_1y minus its relative_return_1y (same price series)."""
    def val(metric):
        c = [f for f in fs.facts if f.metric == metric and f.value is not None and f.status.value == "ok"]
        return max(c, key=lambda f: (f.period_end, f.retrieved_at)) if c else None

    r, rel = val("return_1y"), val("relative_return_1y")
    if r is None or rel is None or r.period_end != rel.period_end:
        return None
    return _entry(float(r.value) - float(rel.value), "yahoo", r.period_end)


def from_factsets(factsets: dict, cfg=None, as_of: date | None = None, now: datetime | None = None, commit: str | None = None) -> dict:
    from indiafacts.scoring import load_score_config

    now = now or datetime.now(timezone.utc)
    cfg = cfg or load_score_config(strict=False)
    out: dict[str, dict] = {}
    nifty = None
    for t, fs in sorted(factsets.items()):
        m = metrics_for(fs, cfg, as_of, now)
        if m:
            out[t] = m
        nifty = nifty or nifty_return_1y(fs)
    if nifty:
        out[NIFTY] = {"return_1y": nifty}
    if commit is None:
        from indiafacts.stamp import app_commit

        commit = app_commit()
    return {"meta": {"generated_at": now.isoformat(timespec="seconds"), "commit": commit, "policy_hash": policy_hash(),
                     "n": len([k for k in out if k != NIFTY])}, "metrics": out}


def build(tickers: list[str], builder: Callable, cache_dir: Path | None = None, now: datetime | None = None,
          as_of: date | None = None, workers: int | None = None, log=print) -> dict:
    """Facts for every ticker through the existing cached universe fetch, then the store. A failing ticker is skipped."""
    from indiafacts.universe import DEFAULT_WORKERS, build_universe

    now = now or datetime.now(timezone.utc)
    universe, failed = build_universe(list(tickers), builder, cache_dir=cache_dir, now=now, workers=workers or DEFAULT_WORKERS)
    if failed:
        log(f"pool_metrics: {len(failed)} of {len(tickers)} tickers not fetched")
    return from_factsets(universe, as_of=as_of, now=now)


def write(store: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return path


def _valid(d) -> bool:
    return isinstance(d, dict) and isinstance(d.get("metrics"), dict) and isinstance(d.get("meta"), dict) and bool(d["metrics"])


def load(mono: Callable[[], float] = time.monotonic) -> dict | None:
    """The published store (env INDIAFACTS_POOL_METRICS_URL, http(s) or file://, cached 1 h in memory), else the local copy
    ~/.indiafacts/pool_metrics.json, else None. Never raises."""
    try:
        url = os.environ.get("INDIAFACTS_POOL_METRICS_URL", "").strip()
        with _lock:
            if _mem["store"] is not None and _mem["key"] == url and mono() - _mem["at"] < URL_TTL:
                return _mem["store"]
        if url:
            try:
                with urlopen(Request(url, headers={"User-Agent": "nextrade-poolstore"}), timeout=10) as r:
                    d = json.loads(r.read(64_000_000))
                if not _valid(d):
                    raise ValueError("published comparison data is empty or malformed")
                with _lock:
                    _mem.update(key=url, at=mono(), store=d)
                if not url.startswith("file:"):
                    try:
                        write(d, local_path())
                    except OSError:
                        pass
                return d
            except Exception:
                with _lock:
                    if _mem["store"] is not None and _mem["key"] == url:
                        return _mem["store"]
        d = json.loads(local_path().read_text(encoding="utf-8"))
        return d if _valid(d) else None
    except Exception:
        return None


def reset_cache() -> None:
    with _lock:
        _mem.update(key=None, at=0.0, store=None)
