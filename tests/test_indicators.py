from datetime import date, datetime, timedelta, timezone

import pytest

from indiafacts.indicators import indicator_facts
from indiafacts.prices import PriceSeries, QualityReport

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def series(closes):
    start = date(2025, 1, 1)
    dates = [start + timedelta(days=i) for i in range(len(closes))]
    return PriceSeries(symbol="ABC.NS", dates=dates, close=list(closes), volume=[1.0] * len(closes), source="yahoo",
                       basis="split_adjusted_close", retrieved_at=NOW, quality=QualityReport(), series_id="s1")


def get(fs, m):
    return next(f for f in fs if f.metric == m)


def test_i1_sma_hand_computed():
    fs = indicator_facts(series(range(1, 61)))
    assert float(get(fs, "sma_50").value) == pytest.approx(sum(range(11, 61)) / 50)
    assert get(fs, "sma_200").status == "unavailable" and "shorter than 200" in get(fs, "sma_200").reason


def test_i2_rsi_is_100_when_only_gains_and_low_when_only_losses():
    assert float(get(indicator_facts(series(range(1, 40))), "rsi_14").value) == pytest.approx(100.0)
    assert float(get(indicator_facts(series(range(40, 1, -1))), "rsi_14").value) == pytest.approx(0.0)


def test_i3_flat_series_has_no_rsi_or_band_position_and_zero_average_move():
    fs = indicator_facts(series([100.0] * 60))
    assert get(fs, "rsi_14").status == "unavailable" and get(fs, "bollinger_pct_b").status == "unavailable"
    assert float(get(fs, "avg_move_14").value) == 0.0


def test_i4_average_move_is_mean_absolute_close_change():
    assert float(get(indicator_facts(series(range(1, 60))), "avg_move_14").value) == pytest.approx(1.0)


def test_i5_macd_histogram_positive_when_rising_faster_and_band_position_above_one_at_a_spike():
    closes = [100.0] * 40 + [100 + 2 * i for i in range(1, 21)]
    fs = indicator_facts(series(closes))
    assert float(get(fs, "macd_hist").value) > 0
    spike = indicator_facts(series([100.0] * 30 + [100.0 + (i % 2) for i in range(10)] + [130.0]))
    assert float(get(spike, "bollinger_pct_b").value) > 1


def test_i6_short_history_marks_everything_unavailable_with_reasons():
    fs = indicator_facts(series([1.0, 2.0, 3.0]))
    assert all(f.status == "unavailable" and f.reason for f in fs)


def test_i7_facts_carry_series_provenance_like_other_price_metrics():
    f = get(indicator_facts(series(range(1, 60))), "sma_50")
    assert f.source == "computed" and f.source_field.startswith("series:s1") and f.period_type == "point"
