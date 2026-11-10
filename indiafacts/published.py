"""Where the files the daily snapshot job publishes are read from.

Each file has its own variable (INDIAFACTS_MARKETLENS_URL, INDIAFACTS_POOL_METRICS_URL, INDIAFACTS_NSE_COPY_BASE). When that
variable is unset, the address is derived from INDIAFACTS_SNAPSHOT_BASE (the snapshots branch), so a server that already reads
snapshots also reads the comparison data, the Market Lens copy and the NSE filings copy without more settings. Setting a
variable to an empty string switches that file off. The snapshot job never sets INDIAFACTS_SNAPSHOT_BASE, so it is unaffected."""
from __future__ import annotations

import os


def url(var: str, name: str) -> str:
    """The explicit value of `var` if it is set (empty means off), else <INDIAFACTS_SNAPSHOT_BASE>/<name>, else ''."""
    if var in os.environ:
        return os.environ[var].strip()
    base = os.environ.get("INDIAFACTS_SNAPSHOT_BASE", "").strip()
    return base.rstrip("/") + "/" + name if base else ""
