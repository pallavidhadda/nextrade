"""Price history: vendor frame in, cleaned PriceSeries plus an explicit quality report out. No LLM sees these rows."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Protocol

import numpy as np
import pandas as pd

SOURCE = "yahoo_prices"
BASIS = "split_adjusted_close"          # Yahoo Close is already split-adjusted to today's share count
MAX_GAP_WEEKDAYS = 5
STALE_AFTER_WEEKDAYS = 3


class PriceClient(Protocol):
    def history(self, symbol: str) -> pd.DataFrame: ...


class YfinancePriceClient:
    def history(self, symbol: str) -> pd.DataFrame:
        import yfinance as yf

        return yf.Ticker(symbol).history(period="max", auto_adjust=False, actions=True)


@dataclass
class QualityReport:
    zero_volume_days: int = 0
    gaps: list[tuple[date, date]] = field(default_factory=list)
    dropped_rows: int = 0
    duplicate_conflicts: int = 0
    stale_days: int | None = None
    events: list[str] = field(default_factory=list)


@dataclass
class PriceSeries:
    symbol: str
    dates: list[date]
    close: list[float]
    volume: list[float]
    source: str
    basis: str
    retrieved_at: datetime
    quality: QualityReport
    series_id: str

    @property
    def usable(self) -> bool:
        return len(self.dates) >= 2


def _weekdays_between(a: date, b: date) -> int:
    return int(np.busday_count(a + pd.Timedelta(days=1).to_pytimedelta(), b))


def load_series(symbol: str, client: PriceClient, as_of: date | None = None,
                now: datetime | None = None) -> PriceSeries:
    now = now or datetime.now(timezone.utc)
    q = QualityReport()
    df = client.history(symbol)
    rows: dict[date, tuple[float, float]] = {}
    if df is not None and not df.empty:
        for ts, r in df.iterrows():
            d = pd.Timestamp(ts).date()
            close, vol = r.get("Close"), r.get("Volume", 0.0)
            if close is None or pd.isna(close) or close <= 0:
                q.dropped_rows += 1
                continue
            if as_of is not None and d > as_of:
                continue
            vol = 0.0 if vol is None or pd.isna(vol) else float(vol)
            if d in rows and rows[d][0] != float(close):
                q.duplicate_conflicts += 1
            rows[d] = (float(close), vol)
            split = r.get("Stock Splits", 0.0)
            if split and not pd.isna(split) and split != 0:
                q.events.append(f"{d.isoformat()}: split {split:g}")
    dates = sorted(rows)
    close = [rows[d][0] for d in dates]
    volume = [rows[d][1] for d in dates]
    q.zero_volume_days = sum(1 for v in volume if v == 0)
    for a, b in zip(dates, dates[1:]):
        if _weekdays_between(a, b) > MAX_GAP_WEEKDAYS:
            q.gaps.append((a, b))
    if dates:
        ref = as_of or now.date()
        lag = int(np.busday_count(dates[-1], ref))
        q.stale_days = lag if lag > STALE_AFTER_WEEKDAYS else None
    sid = hashlib.sha256(f"{symbol}|{dates[:1]}|{dates[-1:]}|{len(dates)}|{close[-3:]}".encode()).hexdigest()[:12]
    return PriceSeries(symbol, dates, close, volume, SOURCE, BASIS, now, q, sid)
