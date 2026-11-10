"""Reproducibility stamp: enough to say which inputs, parameters and code produced a report. No network; never raises."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def params_hash(data_dir: Path | None = None) -> str:
    """sha256 over every data/*.json (name and bytes, sorted by name), first 12 hex characters."""
    h = hashlib.sha256()
    for p in sorted(Path(data_dir or DATA_DIR).glob("*.json"), key=lambda p: p.name):
        h.update(p.name.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()[:12]


def source_policy_hash(data_dir: Path | None = None) -> str:
    """First 12 hex characters of sha256 over data/source_policy.json; 'none' when absent."""
    try:
        return hashlib.sha256((Path(data_dir or DATA_DIR) / "source_policy.json").read_bytes()).hexdigest()[:12]
    except OSError:
        return "none"


def drift_status() -> str:
    """ok | warning | breaking from the drift report the snapshot job points INDIAFACTS_DRIFT_REPORT at; 'unknown' when there is none."""
    try:
        p = os.environ.get("INDIAFACTS_DRIFT_REPORT", "").strip().removeprefix("file://")
        return str(json.loads(Path(p).read_text(encoding="utf-8")).get("status") or "unknown") if p else "unknown"
    except Exception:
        return "unknown"


def app_commit() -> str:
    for var in ("GIT_COMMIT", "RENDER_GIT_COMMIT"):
        v = os.environ.get(var, "").strip()
        if v:
            return v[:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "unknown"
    except Exception:
        return "unknown"


def report_stamp(ticker: str, as_of: date, pool: list[str] | None = None, llm_model: str | None = None,
                 data_dir: Path | None = None, commit: str | None = None) -> dict:
    ph = params_hash(data_dir)
    cm = commit if commit is not None else app_commit()
    members = sorted(pool or [])
    rid = hashlib.sha256(f"{ticker}|{as_of.isoformat()}|{ph}|{cm}".encode()).hexdigest()[:10]
    return {"report_id": rid, "ticker": ticker, "as_of": as_of.isoformat(), "pool_size": len(members), "pool_members": members,
            "params_hash": ph, "commit": cm, "llm_model": llm_model,
            "drift_status": drift_status(), "source_policy": source_policy_hash(data_dir)}
