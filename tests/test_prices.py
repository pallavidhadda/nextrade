from datetime import date

import pandas as pd

from indiafacts.prices import load_series
from tests.pricefakes import NOW, FakePrices, bdays, frame


def series(df, as_of=None, symbol="X.NS"):
    return load_series(symbol, FakePrices({symbol: df}), as_of=as_of, now=NOW)


def test_clean_rows_pass_through_with_dates_not_timestamps():
    d = bdays("2026-10-01", 5)
    s = series(frame(d, [10.0, 11.0, 12.0, 13.0, 14.0]), as_of=date(2026, 10, 7))
    assert s.dates == d[:5] and s.close == [10.0, 11.0, 12.0, 13.0, 14.0] and s.usable
    assert s.basis == "split_adjusted_close" and s.quality.dropped_rows == 0


def test_nan_zero_negative_rows_dropped_and_counted():
    d = bdays("2026-10-01", 5)
    s = series(frame(d, [10.0, float("nan"), 0.0, -3.0, 14.0]), as_of=date(2026, 10, 7))
    assert s.close == [10.0, 14.0] and s.quality.dropped_rows == 3


def test_duplicate_dates_deduped_and_conflicts_flagged():
    d = bdays("2026-10-01", 3)
    df = frame([d[0], d[1], d[1], d[2]], [10.0, 11.0, 11.5, 12.0])
    s = series(df, as_of=date(2026, 10, 6))
    assert s.dates == d and s.close == [10.0, 11.5, 12.0] and s.quality.duplicate_conflicts == 1
    same = series(frame([d[0], d[1], d[1], d[2]], [10.0, 11.0, 11.0, 12.0]), as_of=date(2026, 10, 6))
    assert same.quality.duplicate_conflicts == 0


def test_gap_of_ten_weekdays_flagged_but_weekend_is_not():
    d1, d2 = bdays("2026-09-01", 5), bdays("2026-09-22", 5)        # 10-weekday hole between
    s = series(frame(d1 + d2, [1.0] * 10), as_of=date(2026, 9, 28))
    assert len(s.quality.gaps) == 1 and s.quality.gaps[0][0] == d1[-1]
    weekend = series(frame(bdays("2026-10-01", 10), [1.0] * 10), as_of=date(2026, 10, 14))
    assert weekend.quality.gaps == []


def test_zero_volume_days_counted():
    d = bdays("2026-10-01", 4)
    s = series(frame(d, [1.0] * 4, volume=[0.0, 5.0, 0.0, 5.0]), as_of=date(2026, 10, 6))
    assert s.quality.zero_volume_days == 2


def test_as_of_truncation_ignores_later_spike():
    d = bdays("2026-10-01", 6)
    s = series(frame(d, [10.0, 10.0, 10.0, 10.0, 10.0, 999.0]), as_of=d[4])
    assert 999.0 not in s.close and s.dates[-1] == d[4]


def test_stale_last_bar_flagged():
    d = bdays("2026-10-01", 3)
    s = series(frame(d, [1.0] * 3), as_of=date(2026, 10, 20))
    assert s.quality.stale_days is not None and s.quality.stale_days > 3
    fresh = series(frame(d, [1.0] * 3), as_of=d[-1])
    assert fresh.quality.stale_days is None


def test_split_event_listed_and_close_untouched():
    d = bdays("2026-10-01", 4)
    s = series(frame(d, [100.0, 100.5, 101.0, 100.8], splits=[0.0, 0.0, 2.0, 0.0]), as_of=date(2026, 10, 6))
    assert s.close == [100.0, 100.5, 101.0, 100.8]
    assert any("split 2" in e for e in s.quality.events)


def test_empty_and_single_row_unusable():
    assert not series(pd.DataFrame()).usable
    one = series(frame(bdays("2026-10-01", 1), [10.0]), as_of=date(2026, 10, 1))
    assert not one.usable


def test_series_id_stable_and_changes_with_data():
    d = bdays("2026-10-01", 3)
    a = series(frame(d, [1.0, 2.0, 3.0]), as_of=date(2026, 10, 5)).series_id
    assert a == series(frame(d, [1.0, 2.0, 3.0]), as_of=date(2026, 10, 5)).series_id
    assert a != series(frame(d, [1.0, 2.0, 4.0]), as_of=date(2026, 10, 5)).series_id


def test_chart_data_rebased_downsampled_and_drawdown():
    import pandas as pd

    from indiafacts.prices import chart_data

    d = list(pd.bdate_range(end=date(2026, 10, 23), periods=1400).date)
    close = [100.0 + i * 0.1 for i in range(1400)]
    close[700] = 50.0                                       # a crash for the drawdown series
    bench = [200.0 + i * 0.05 for i in range(1400)]
    s = series(frame(d, close), as_of=d[-1])
    b = series(frame(d, bench), as_of=d[-1], symbol="^NSEI")
    c = chart_data(s, b, years=5, max_points=260)
    assert c["stock"][0] == 100.0 and c["bench"][0] == 100.0
    assert len(c["dates"]) <= 260 and c["dates"][-1] == d[-1].isoformat()
    assert len(c["dates"]) == len(c["stock"]) == len(c["bench"]) == len(c["drawdown"])
    assert all(x <= 0 for x in c["drawdown"]) and min(c["drawdown"]) < -0.3
    assert c["series_id"] == s.series_id and c["basis"] == "split_adjusted_close"
    assert chart_data(s, None, years=5)["bench"] == []
    assert chart_data(series(pd.DataFrame()), None, years=5) == {}
