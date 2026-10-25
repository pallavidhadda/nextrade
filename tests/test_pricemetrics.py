import math
from datetime import date, timedelta

import pandas as pd

import pytest

from indiafacts.pricemetrics import price_metrics
from indiafacts.prices import load_series
from tests.pricefakes import NOW, FakePrices, bdays, frame

END = date(2026, 10, 23)


def S(dates, closes, symbol="X.NS"):
    return load_series(symbol, FakePrices({symbol: frame(dates, closes)}), as_of=END, now=NOW)


def get(facts, metric):
    [f] = [f for f in facts if f.metric == metric]
    return f


SPARSE_D = [date(2021, 10, 22), date(2023, 10, 20), date(2024, 10, 18), date(2025, 10, 17), date(2025, 10, 24), END]
SPARSE_C = [50.0, 80.0, 90.0, 100.0, 105.0, 120.0]


def test_returns_use_nearest_earlier_trading_day_and_hand_values():
    f = price_metrics(S(SPARSE_D, SPARSE_C), None, END)
    assert float(get(f, "return_1y").value) == pytest.approx(0.2)      # start 2025-10-17 (not the later 10-24)
    assert float(get(f, "return_3y").value) == pytest.approx(0.5)
    assert float(get(f, "return_5y").value) == pytest.approx(1.4)
    assert get(f, "return_1y").period_start == date(2025, 10, 17) and get(f, "return_1y").period_end == END


def test_short_history_unavailable_with_reason():
    f = price_metrics(S(SPARSE_D[2:], SPARSE_C[2:]), None, END)
    r = get(f, "return_5y")
    assert r.status == "unavailable" and "history shorter than 5 years" in r.reason
    assert get(f, "return_1y").status == "ok"


def long_dates(n_tail=4):
    """An old anchor point (so a 1-year window is covered) followed by n_tail business days ending at END."""
    tail = list(pd.bdate_range(end=END, periods=n_tail).date)
    return [END - timedelta(days=400)] + tail


def test_drawdown_known_series_and_monotonic():
    d = long_dates()
    f = price_metrics(S(d, [100.0, 120.0, 60.0, 90.0, 150.0]), None, END)
    assert float(get(f, "max_drawdown_1y").value) == pytest.approx(-0.5)
    up = price_metrics(S(d, [1.0, 2.0, 3.0, 4.0, 5.0]), None, END)
    assert float(get(up, "max_drawdown_1y").value) == 0.0


def test_window_not_covered_is_unavailable_for_every_windowed_metric():
    d = list(pd.bdate_range(end=END, periods=5).date)
    f = price_metrics(S(d, [1.0, 2.0, 3.0, 4.0, 5.0]), None, END)
    for m in ("return_1y", "max_drawdown_1y", "volatility_1y", "high_52w", "beta_1y"):
        assert get(f, m).status == "unavailable" and "history shorter than 1 years" in get(f, m).reason


def test_52_week_uses_only_last_365_days():
    dates = [date(2025, 6, 2), date(2025, 9, 1), date(2026, 3, 2), date(2026, 6, 1), END]
    f = price_metrics(S(dates, [500.0, 70.0, 80.0, 100.0, 90.0]), None, END)
    assert float(get(f, "high_52w").value) == 100.0 and float(get(f, "low_52w").value) == 80.0
    assert float(get(f, "pct_from_52w_high").value) == pytest.approx(90 / 100 - 1)


def test_volatility_constant_zero_and_alternating_hand_value():
    d = long_dates()
    assert float(get(price_metrics(S(d, [10.0] * 5), None, END), "volatility_1y").value) == 0.0
    f = price_metrics(S(d, [100.0, 110.0, 100.0, 110.0, 100.0]), None, END)
    a = math.log(1.1)
    assert float(get(f, "volatility_1y").value) == pytest.approx(a * math.sqrt(4 / 3) * math.sqrt(252), abs=1e-4)


def bench_pair(n=300, mult=2.0):
    d = list(pd.bdate_range(end=END, periods=n).date)
    r = [0.01 if i % 2 else -0.005 for i in range(n - 1)]
    b, s = [100.0], [100.0]
    for x in r:
        b.append(b[-1] * (1 + x))
        s.append(s[-1] * (1 + mult * x))
    return d, s, b


def test_beta_of_double_returns_is_two_and_relative_return():
    d, s, b = bench_pair()
    f = price_metrics(S(d, s), S(d, b, "^NSEI"), d[-1])
    assert float(get(f, "beta_1y").value) == pytest.approx(2.0, abs=1e-6)
    i = max(k for k, x in enumerate(d) if x <= d[-1] - timedelta(days=365))     # window start, not first row
    assert float(get(f, "relative_return_1y").value) == pytest.approx((s[-1] / s[i] - 1) - (b[-1] / b[i] - 1), abs=1e-6)


def test_beta_unavailable_for_constant_benchmark_and_missing_benchmark():
    d, s, _ = bench_pair()
    f = price_metrics(S(d, s), S(d, [100.0] * len(d), "^NSEI"), d[-1])
    assert get(f, "beta_1y").status == "unavailable"
    g = price_metrics(S(d, s), None, d[-1])
    assert get(g, "beta_1y").status == "unavailable" and "benchmark unavailable" in get(g, "beta_1y").reason
    assert get(g, "return_1y").status in ("ok", "unavailable") and get(g, "volatility_1y").status == "ok"


def test_only_common_dates_used_and_no_overlap_unavailable():
    d, s, b = bench_pair()
    other = list(pd.bdate_range(end=date(2024, 6, 3), periods=300).date)
    f = price_metrics(S(d, s), S(other, b, "^NSEI"), d[-1])
    assert get(f, "beta_1y").status == "unavailable" and "overlap" in get(f, "beta_1y").reason


def test_corporate_action_inside_window_marks_unverified():
    f = price_metrics(S(SPARSE_D, SPARSE_C), None, END, corporate_actions=[date(2025, 12, 1)])
    r = get(f, "return_1y")
    assert r.status == "unverified" and "2025-12-01" in r.reason and r.value is not None
    assert get(f, "return_3y").status == "unverified"
    clean = price_metrics(S(SPARSE_D, SPARSE_C), None, END, corporate_actions=[date(2020, 1, 1)])
    assert get(clean, "return_1y").status == "ok"


def test_unusable_series_gives_unavailable_facts_not_crash():
    d = bdays("2026-10-01", 1)
    f = price_metrics(S(d, [10.0]), None, d[-1])
    assert all(x.status == "unavailable" for x in f) and f


def test_provenance_fields_on_every_fact():
    f = price_metrics(S(SPARSE_D, SPARSE_C), None, END)
    for x in f:
        assert x.source == "computed" and "series:" in x.source_field and "basis:split_adjusted_close" in x.source_field
