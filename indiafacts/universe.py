"""Comparison pool: ticker file reader and a one-day disk cache so a score run does not refetch 30 companies."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from indiafacts.models import Entity, FactSet, Identifier, Status

DEFAULT_POOL = Path(__file__).parent / "data" / "pool30.txt"
CACHE_MAX_AGE = timedelta(days=1)
CACHE_SCHEMA = 2        # bump when FactSet gains fields the report needs (2: chart data)


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


NSE_COLUMNS = ("Company Name", "Industry", "Symbol", "ISIN Code")


@dataclass
class Pool:
    tickers: list[str]
    labels: dict[str, dict] = field(default_factory=dict)      # ticker -> {industry, isin, name} from an NSE index file
    kind: str = "ticker_list"


def read_pool(path: Path) -> Pool:
    """A ticker list, or an NSE index constituents CSV (Company Name, Industry, Symbol, Series, ISIN Code)."""
    path = Path(path)
    head = path.read_text(encoding="utf-8-sig").splitlines()[:1]
    if not head or "Symbol" not in head[0] or "," not in head[0]:
        return Pool(read_tickers(path))
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))
    missing = [c for c in NSE_COLUMNS if c not in (rows[0] if rows else {})]
    if missing:
        raise ValueError(f"index CSV {path.name}: missing column(s) {', '.join(missing)}")
    pool = Pool([], {}, "nse_index_csv")
    for r in rows:
        if (r.get("Series") or "EQ").strip() not in ("EQ", ""):
            continue
        t = Entity.from_ticker(r["Symbol"].strip() + ".NS").ticker
        if t in pool.labels:
            continue
        pool.tickers.append(t)
        pool.labels[t] = {"industry": r["Industry"].strip(), "isin": r["ISIN Code"].strip(), "name": r["Company Name"].strip()}
    return pool


def apply_labels(fs: FactSet, label: dict | None) -> FactSet:
    """NSE's industry group is authoritative and deterministic: it becomes the entity's sector."""
    if not label:
        return fs
    upd = {"sector": label["industry"]}
    if fs.entity.isin.value is None and label.get("isin"):
        upd["isin"] = Identifier(value=label["isin"], status=Status.ok)
    if not fs.entity.name and label.get("name"):
        upd["name"] = label["name"]
    return fs.model_copy(update={"entity": fs.entity.model_copy(update=upd)})


def _safe(ticker: str) -> str:
    return ticker.replace("&", "_AND_")


def build_universe(tickers: list[str], builder: Callable[[str], FactSet], cache_dir: Path | None = None,
                   now: datetime | None = None, labels: dict | None = None,
                   fresh: dict[str, FactSet] | None = None) -> tuple[dict[str, FactSet], dict[str, str]]:
    """Returns (factsets, failures). A failing or unresolved ticker is reported, never fatal."""
    cache_dir = Path(cache_dir or default_cache_dir())
    now = now or datetime.now(timezone.utc)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, FactSet] = {}
    failed: dict[str, str] = {}
    for t in tickers:
        path = cache_dir / f"{_safe(t)}.json"
        fs = (fresh or {}).get(t)          # a just-fetched copy always beats the cache, and refreshes it
        wrote = fs is not None
        if fs is None and path.exists():
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                if blob.get("schema") == CACHE_SCHEMA and now - datetime.fromisoformat(blob["fetched_at"]) < CACHE_MAX_AGE:
                    fs = FactSet.model_validate(blob["factset"])
            except (ValueError, KeyError, TypeError):
                fs = None                                  # corrupt cache entry: rebuild
        if fs is None:
            try:
                fs = builder(t)
            except Exception as exc:
                failed[t] = f"{type(exc).__name__}: {exc}"
                continue
            wrote = True
        if wrote:
            path.write_text(json.dumps({"schema": CACHE_SCHEMA, "fetched_at": now.isoformat(), "factset": json.loads(fs.model_dump_json())}),
                            encoding="utf-8")
        if fs.entity.resolution != "resolved":
            failed[t] = fs.entity.resolution_reason or "unresolved"
            continue
        out[t] = apply_labels(fs, (labels or {}).get(t))
    return out, failed
