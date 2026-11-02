"""Classic price indicators as deterministic facts (SMA, RSI, MACD, Bollinger, average move), computed from the stored closes.
They describe the past price path only and are not predictions. Research/education only; not financial advice."""
from __future__ import annotations

import math

import numpy as np

from indiafacts.models import Fact
from indiafacts.pricemetrics import _Maker
from indiafacts.prices import PriceSeries


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def indicator_facts(series: PriceSeries) -> list[Fact]:
    if not series.dates:
        return []
    mk = _Maker(series, series.dates[-1], [])
    c = np.array(series.close, dtype=float)
    n = len(c)
    out: list[Fact] = []

    def short(k: int) -> str:
        return f"history shorter than {k} bars"

    for k in (50, 200):
        out.append(mk.make(f"sma_{k}", float(c[-k:].mean()) if n >= k else None, "INR", f"{k}d", reason="" if n >= k else short(k)))

    # RSI(14) with Wilder smoothing
    rsi, why = None, short(15)
    if n >= 15:
        d = np.diff(c)
        gain, loss = np.clip(d, 0, None), np.clip(-d, 0, None)
        ag, al = gain[:14].mean(), loss[:14].mean()
        for g, l in zip(gain[14:], loss[14:]):
            ag, al = (ag * 13 + g) / 14, (al * 13 + l) / 14
        if ag == 0 and al == 0:
            why = "no price movement, so RSI is undefined"
        else:
            rsi, why = (100.0 if al == 0 else 100 - 100 / (1 + ag / al)), ""
    out.append(mk.make("rsi_14", rsi, "points", "14d", reason=why))

    # MACD histogram (12, 26, 9)
    if n >= 35:
        macd = _ema(c, 12) - _ema(c, 26)
        hist, why = float(macd[-1] - _ema(macd, 9)[-1]), ""
    else:
        hist, why = None, short(35)
    out.append(mk.make("macd_hist", hist, "INR", "12-26-9", reason=why))

    # Bollinger %B (20, 2 standard deviations)
    pct_b, why = None, short(20)
    if n >= 20:
        w = c[-20:]
        mean, sd = float(w.mean()), float(w.std())
        if sd == 0 or math.isnan(sd):
            why = "no variation in the last 20 closes, so the bands have no width"
        else:
            lo, hi = mean - 2 * sd, mean + 2 * sd
            pct_b, why = float((c[-1] - lo) / (hi - lo)), ""
    out.append(mk.make("bollinger_pct_b", pct_b, "ratio", "20d", reason=why))

    # average absolute close-to-close move over 14 sessions (a rough range measure, not a true ATR)
    out.append(mk.make("avg_move_14", float(np.abs(np.diff(c[-15:])).mean()) if n >= 15 else None, "INR", "14d",
                       reason="" if n >= 15 else short(15)))
    return out
