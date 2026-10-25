from datetime import date, datetime, timezone

import numpy as np
import pandas as pd


def frame(dates, close, volume=None, splits=None, dividends=None, tz="Asia/Kolkata"):
    n = len(dates)
    idx = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    if tz:
        idx = idx.tz_localize(tz)
    return pd.DataFrame({
        "Open": close, "High": close, "Low": close, "Close": close, "Adj Close": close,
        "Volume": volume if volume is not None else [1000.0] * n,
        "Dividends": dividends if dividends is not None else [0.0] * n,
        "Stock Splits": splits if splits is not None else [0.0] * n,
    }, index=idx)


def bdays(start: str, n: int):
    return list(pd.bdate_range(start, periods=n).date)


class FakePrices:
    def __init__(self, frames):
        self.frames, self.calls = frames, []

    def history(self, symbol):
        self.calls.append(symbol)
        f = self.frames.get(symbol)
        if f is None:
            return pd.DataFrame()
        return f


NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
