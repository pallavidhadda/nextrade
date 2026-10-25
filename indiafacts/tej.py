"""TejHQ open data (huggingface.co/datasets/tejhq/indian-markets; MIT tag; exchange-published bhavcopy).
Used for identity (ISIN, symbol history), price-affecting corporate actions and a point-in-time liquidity universe.
Educational use; attribute TejHQ; verify exchange terms before any commercial use."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from indiafacts.securitymaster import SymbolChange, SymbolChanges

BASE_URL = "https://huggingface.co/datasets/tejhq/indian-markets/resolve/main/"
MAX_AGE = timedelta(days=1)
PRICE_AFFECTING = ("demerger", "merger")      # Yahoo Close is already adjusted for splits and bonuses, not these


class TejUnavailable(RuntimeError):
    pass


def default_cache_dir() -> Path:
    return Path.home() / ".indiafacts" / "tej"


def _http_fetch(url: str) -> bytes:
    import requests

    r = requests.get(url, timeout=180)
    r.raise_for_status()
    return r.content


class TejStore:
    def __init__(self, cache_dir: Path | None = None, fetch: Callable[[str], bytes] | None = None,
                 now: Callable[[], datetime] | None = None):
        self.dir = Path(cache_dir or default_cache_dir())
        self.fetch = fetch or _http_fetch
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.last_age_days: float | None = None        # set only when stale cache was served because the download failed

    def load(self, path: str) -> pd.DataFrame:
        self.dir.mkdir(parents=True, exist_ok=True)
        f = self.dir / path.replace("/", "__")
        age = None
        if f.exists():
            age = self.now() - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
            if age < MAX_AGE:
                try:
                    return pd.read_parquet(f)
                except Exception:
                    f.unlink(missing_ok=True)
                    age = None
        try:
            data = self.fetch(BASE_URL + path)
            df = pd.read_parquet(io.BytesIO(data))
        except Exception as exc:
            if f.exists() and age is not None:
                try:
                    df = pd.read_parquet(f)
                    self.last_age_days = age.total_seconds() / 86400
                    return df
                except Exception:
                    pass
            raise TejUnavailable(f"{type(exc).__name__}: {exc}") from exc
        f.write_bytes(data)
        return df


def _d(x) -> date:
    return pd.Timestamp(x).date()


def symbol_changes_from_history(df: pd.DataFrame) -> SymbolChanges:
    """A rename = the same ISIN trading under a new symbol. Same symbol under a new ISIN is not a rename."""
    out = SymbolChanges()
    for isin, g in df.groupby("isin"):
        rows = sorted(((_d(r.valid_from), r.symbol) for r in g.itertuples()))
        for (_, a), (start, b) in zip(rows, rows[1:]):
            if a != b:
                out.append(SymbolChange("", str(a).upper(), str(b).upper(), start))
    return out


def isin_for(df: pd.DataFrame, symbol: str, as_of: date | None = None) -> str | None:
    rows = df[df["symbol"].str.upper() == symbol.upper()]
    if rows.empty:
        return None
    if as_of is None:
        return str(rows.assign(_f=rows["valid_from"].map(_d)).sort_values("_f").iloc[-1]["isin"])
    for r in rows.itertuples():
        if _d(r.valid_from) <= as_of <= _d(r.valid_to):
            return str(r.isin)
    return None


def price_affecting_dates(actions: pd.DataFrame, history: pd.DataFrame, symbol: str) -> list[date]:
    isins = set(history[history["symbol"].str.upper() == symbol.upper()]["isin"])
    if not isins:
        return []
    syms = set(history[history["isin"].isin(isins)]["symbol"].str.upper())
    hit = actions[actions["symbol"].str.upper().isin(syms) & actions["type"].isin(PRICE_AFFECTING)]
    return sorted({_d(x) for x in hit["ex_date"]})


@dataclass(frozen=True)
class Member:
    rank: int
    symbol: str
    isin: str
    name: str


def universe_members(df: pd.DataFrame, as_of: date, top_n: int | None = None) -> list[Member]:
    dates = sorted({_d(x) for x in df["rebalance_date"]})
    usable = [d for d in dates if d <= as_of]
    if not usable:
        return []
    last = usable[-1]
    rows = df[df["rebalance_date"].map(_d) == last].sort_values("rank")
    members = [Member(int(r.rank), str(r.symbol), str(r.isin), str(r.name)) for r in rows.itertuples()]
    return members[:top_n] if top_n else members
