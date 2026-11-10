"""Reproducibility stamp: enough to say which inputs, parameters and code produced a report. No network; never raises."""
from __future__ import annotations

import hashlib
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
            "params_hash": ph, "commit": cm, "llm_model": llm_model}
