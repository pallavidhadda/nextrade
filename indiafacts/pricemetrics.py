"""Deterministic price metrics as Facts. Windows must be fully covered by history or the metric is unavailable."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable

import numpy as np

from indiafacts.models import Fact, PeriodType, Status
from indiafacts.prices import PriceSeries

COMPUTED = "computed"
BENCHMARK_LABEL = "^NSEI Nifty 50 price index (dividends excluded)"


def _dec(x: float) -> Decimal:
    return Decimal(repr(float(x)))


def _start_index(dates: list[date], end: date, years: int) -> int | None:
    target = end - timedelta(days=365 * years)
    ok = [i for i, d in enumerate(dates) if d <= target]
    return ok[-1] if ok else None


class _Maker:
    def __init__(self, s: PriceSeries, end: date, actions: Iterable[date]):
        self.s, self.end, self.actions = s, end, sorted(actions)

    def make(self, metric: str, value: float | None, unit: str, window: str, start: date | None = None,
             reason: str = "") -> Fact:
        status = Status.ok if value is not None else Status.unavailable
        if value is not None and start is not None:
            hit = [a for a in self.actions if start < a <= self.end]
            if hit:
                status, reason = Status.unverified, (
                    f"window spans corporate action on {hit[0].isoformat()}; price return not adjusted for it")
        return Fact.make(
            entity_key=self.s.symbol, metric=metric, value=None if value is None else _dec(value), unit=unit,
            period_start=start, period_end=self.end, period_type=PeriodType.point, source=COMPUTED,
            source_field=f"series:{self.s.series_id}|window:{window}|basis:{self.s.basis}|benchmark:{BENCHMARK_LABEL}",
            retrieved_at=self.s.retrieved_at, status=status, reason=reason if status != Status.ok else "",
        )


def _short(years: int) -> str:
    return f"history shorter than {years} years"


def price_metrics(series: PriceSeries, benchmark: PriceSeries | None, as_of: date,
                  corporate_actions: Iterable[date] = ()) -> list[Fact]:
    names = ["return", "benchmark_return", "relative_return", "max_drawdown"]
    mk = _Maker(series, series.dates[-1] if series.dates else as_of, corporate_actions)
    out: list[Fact] = []
    if not series.usable:
        why = "price history unusable (fewer than 2 valid rows)"
        for n in (1, 3, 5):
            out += [mk.make(f"{m}_{n}y", None, "ratio", f"{n}y", reason=why) for m in names]
        out += [mk.make("high_52w", None, "INR", "52w", reason=why), mk.make("low_52w", None, "INR", "52w", reason=why),
                mk.make("pct_from_52w_high", None, "ratio", "52w", reason=why),
                mk.make("volatility_1y", None, "ratio", "1y", reason=why),
                mk.make("beta_1y", None, "ratio", "1y", reason=why), mk.make("beta_3y", None, "ratio", "3y", reason=why)]
        return out

    d, c, end = series.dates, np.array(series.close), series.dates[-1]
    bench_ok = benchmark is not None and benchmark.usable
    bnote = "benchmark unavailable"

    for n in (1, 3, 5):
        i = _start_index(d, end, n)
        w = f"{n}y"
        if i is None:
            for m in names:
                out.append(mk.make(f"{m}_{n}y", None, "ratio", w, reason=_short(n)))
            continue
        start = d[i]
        ret = c[-1] / c[i] - 1
        out.append(mk.make(f"return_{n}y", ret, "ratio", w, start))
        seg = c[i:]
        out.append(mk.make(f"max_drawdown_{n}y", float(np.min(seg / np.maximum.accumulate(seg) - 1)), "ratio", w, start))
        if bench_ok:
            bi = _start_index(benchmark.dates, benchmark.dates[-1], n)
            if bi is None:
                out += [mk.make(f"benchmark_return_{n}y", None, "ratio", w, reason=_short(n)),
                        mk.make(f"relative_return_{n}y", None, "ratio", w, reason=_short(n))]
            else:
                bret = benchmark.close[-1] / benchmark.close[bi] - 1
                out.append(mk.make(f"benchmark_return_{n}y", bret, "ratio", w, benchmark.dates[bi]))
                out.append(mk.make(f"relative_return_{n}y", ret - bret, "ratio", w, start))
        else:
            out += [mk.make(f"benchmark_return_{n}y", None, "ratio", w, reason=bnote),
                    mk.make(f"relative_return_{n}y", None, "ratio", w, reason=bnote)]

    out.append(mk.make("last_close", float(c[-1]), "INR", "last"))
    i1 = _start_index(d, end, 1)
    if i1 is None:
        why = _short(1)
        out += [mk.make("high_52w", None, "INR", "52w", reason=why), mk.make("low_52w", None, "INR", "52w", reason=why),
                mk.make("pct_from_52w_high", None, "ratio", "52w", reason=why),
                mk.make("volatility_1y", None, "ratio", "1y", reason=why)]
    else:
        cutoff = end - timedelta(days=365)
        last_year = [x for dd, x in zip(d, c) if dd > cutoff]
        hi, lo = max(last_year), min(last_year)
        out += [mk.make("high_52w", hi, "INR", "52w", d[i1]), mk.make("low_52w", lo, "INR", "52w", d[i1]),
                mk.make("pct_from_52w_high", c[-1] / hi - 1, "ratio", "52w", d[i1])]
        r = np.diff(np.log(c[i1:]))
        vol = float(np.std(r, ddof=1) * math.sqrt(252)) if len(r) > 1 else None
        out.append(mk.make("volatility_1y", vol, "ratio", "1y", d[i1],
                           reason="" if vol is not None else "too few observations"))

    for n in (1, 3):
        w, i = f"{n}y", _start_index(d, end, n)
        if i is None:
            out.append(mk.make(f"beta_{n}y", None, "ratio", w, reason=_short(n)))
        elif not bench_ok:
            out.append(mk.make(f"beta_{n}y", None, "ratio", w, reason=bnote))
        else:
            bmap = dict(zip(benchmark.dates, benchmark.close))
            common = [(dd, x, bmap[dd]) for dd, x in zip(d[i:], c[i:]) if dd in bmap]
            if len(common) < 3:
                out.append(mk.make(f"beta_{n}y", None, "ratio", w, reason="no overlap between stock and benchmark dates"))
                continue
            sr = np.diff([x for _, x, _ in common]) / np.array([x for _, x, _ in common][:-1])
            br = np.diff([b for _, _, b in common]) / np.array([b for _, _, b in common][:-1])
            var = float(np.var(br, ddof=1))
            if var == 0:
                out.append(mk.make(f"beta_{n}y", None, "ratio", w, reason="benchmark variance zero"))
            else:
                out.append(mk.make(f"beta_{n}y", float(np.cov(sr, br, ddof=1)[0, 1] / var), "ratio", w, d[i]))
    return out
