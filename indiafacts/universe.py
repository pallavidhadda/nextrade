"""Comparison pool: ticker file reader and a one-day disk cache so a score run does not refetch 30 companies."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from indiafacts.models import Entity, FactSet

DEFAULT_POOL = Path(__file__).parent / "data" / "pool30.txt"
CACHE_MAX_AGE = timedelta(days=1)


def default_cache_dir() -> Path:
    return Path.home() / ".indiafacts" / "cache"


def read_tickers(path: Path) -> list[str]:
    out: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        t = Entity.from_ticker(line).ticker          # validates; raises ValueError('invalid ticker ...')
        if t not in out:
            out.append(t)
    return out


def _safe(ticker: str) -> str:
    return ticker.replace("&", "_AND_")


def build_universe(tickers: list[str], builder: Callable[[str], FactSet], cache_dir: Path | None = None,
                   now: datetime | None = None) -> tuple[dict[str, FactSet], dict[str, str]]:
    """Returns (factsets, failures). A failing or unresolved ticker is reported, never fatal."""
    cache_dir = Path(cache_dir or default_cache_dir())
    now = now or datetime.now(timezone.utc)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, FactSet] = {}
    failed: dict[str, str] = {}
    for t in tickers:
        path = cache_dir / f"{_safe(t)}.json"
        fs = None
        if path.exists():
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                if now - datetime.fromisoformat(blob["fetched_at"]) < CACHE_MAX_AGE:
                    fs = FactSet.model_validate(blob["factset"])
            except (ValueError, KeyError, TypeError):
                fs = None                                  # corrupt cache entry: rebuild
        if fs is None:
            try:
                fs = builder(t)
            except Exception as exc:
                failed[t] = f"{type(exc).__name__}: {exc}"
                continue
            path.write_text(json.dumps({"fetched_at": now.isoformat(), "factset": json.loads(fs.model_dump_json())}),
                            encoding="utf-8")
        if fs.entity.resolution != "resolved":
            failed[t] = fs.entity.resolution_reason or "unresolved"
            continue
        out[t] = fs
    return out, failed
