from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from indiafacts.backtest import (BacktestConfig, compute_signals, forward_returns, run_backtest, render_backtest,
                                 PanelSource)

DISCLAIMER = "Not financial, investment or trading advice"


def _dates(n, start=date(2020, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _panel(n_days=400, n_syms=10, seed=0, drift=None):
    rng = np.random.default_rng(seed)
    idx = pd.DatetimeIndex(_dates(n_days))
    drift = drift if drift is not None else np.zeros(n_syms)
    rets = rng.normal(0, 0.01, (n_days, n_syms)) + drift
    px = pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=[f"S{i}" for i in range(n_syms)])
    return px


def test_b1_momentum_hand_computed():
    px = _panel()
    sig = compute_signals(px)
    t = 300
    expected = px.iloc[t - 21] / px.iloc[t - 252] - 1
    pd.testing.assert_series_equal(sig["mom_12_1"].iloc[t], expected, check_names=False)


def test_b2_no_lookahead():
    px = _panel()
    a = compute_signals(px)
    px2 = px.copy()
    px2.iloc[301:] *= 5
    b = compute_signals(px2)
    for name in a:
        pd.testing.assert_series_equal(a[name].iloc[300], b[name].iloc[300], check_names=False)


def test_b3_forward_return_and_b4_carry():
    px = _panel(n_days=100, n_syms=3)
    px.iloc[60:, 2] = np.nan                       # S2 stops trading (delisted)
    fr, carried = forward_returns(px, 50, 21)
    assert fr["S0"] == pytest.approx(px.iloc[71, 0] / px.iloc[50, 0] - 1)
    assert fr["S2"] == pytest.approx(px.iloc[59, 2] / px.iloc[50, 2] - 1)
    assert carried == 1


class FakeSource(PanelSource):
    def __init__(self, px, members=None):
        self._px, self._members = px, members

    def prices(self, start, end):
        return self._px

    def members(self, as_of):
        return list(self._px.columns) if self._members is None else self._members(as_of)


def _predictive_panel():
    n = 10
    drift = np.linspace(-0.0015, 0.0015, n)         # stable cross-section: higher index = better trend
    return _panel(n_days=700, n_syms=n, seed=3, drift=drift)


def test_b6_predictive_signal_beats_chance():
    px = _predictive_panel()
    res = run_backtest(FakeSource(px), BacktestConfig(horizon_days=21, quantiles=5, cost_bps=0))
    r = res.signals["mom_12_1"]
    assert r.ic_mean > 0.3
    assert r.spread > 0
    assert r.net_excess_mean > 0


def test_b7_noise_is_not_significant():
    px = _panel(n_days=900, n_syms=20, seed=11)
    res = run_backtest(FakeSource(px), BacktestConfig(horizon_days=21, quantiles=5, cost_bps=0))
    for r in res.signals.values():
        assert abs(r.ic_t) < 3


def test_b5_too_few_names_skips_period():
    px = _panel(n_days=400, n_syms=3)
    res = run_backtest(FakeSource(px), BacktestConfig(horizon_days=21, quantiles=5))
    assert res.periods_used == 0
    assert res.periods_skipped > 0


def test_b8_cost_charged_on_turnover():
    px = _predictive_panel()
    free = run_backtest(FakeSource(px), BacktestConfig(cost_bps=0)).signals["mom_12_1"]
    paid = run_backtest(FakeSource(px), BacktestConfig(cost_bps=100)).signals["mom_12_1"]
    assert paid.net_excess_mean < free.net_excess_mean
    assert paid.turnover_mean == pytest.approx(free.turnover_mean)
    # the first rebalance buys the whole Q5 set, so turnover can never be below 1 there
    assert 0 < paid.turnover_mean <= 1


def test_b9_point_in_time_membership():
    n = 20
    px = _panel(n_days=700, n_syms=n, seed=3, drift=np.linspace(-0.0015, 0.0015, n))
    late = {"S19"}
    def members(as_of):
        cols = [c for c in px.columns if c not in late]
        return cols if pd.Timestamp(as_of) < px.index[500] else list(px.columns)
    res = run_backtest(FakeSource(px, members), BacktestConfig(cost_bps=0))
    assert min(res.universe_sizes) == 19 and max(res.universe_sizes) == 20


def test_b10_subperiods():
    px = _predictive_panel()
    r = run_backtest(FakeSource(px), BacktestConfig(cost_bps=0)).signals["mom_12_1"]
    assert len(r.halves) == 2
    assert r.halves[0].periods + r.halves[1].periods == r.periods


def test_b11_render_has_caveats_and_disclaimer():
    px = _predictive_panel()
    text = render_backtest(run_backtest(FakeSource(px), BacktestConfig()))
    assert DISCLAIMER in text
    for word in ("in-sample", "cost", "multiple", "carried", "demerger", "equal-weight"):
        assert word.lower() in text.lower()


def test_b12_no_secret_material(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "SECRET123")
    text = render_backtest(run_backtest(FakeSource(_predictive_panel()), BacktestConfig()))
    assert "SECRET123" not in text


def test_b14_out_of_sample_split_by_date():
    px = _predictive_panel()
    split = px.index[500].date()
    r = run_backtest(FakeSource(px), BacktestConfig(cost_bps=0, oos_start=split)).signals["mom_12_1"]
    assert r.in_sample.periods + r.out_of_sample.periods == r.periods
    assert r.in_sample.periods > 0 and r.out_of_sample.periods > 0
    assert r.out_of_sample.first_date >= split > r.in_sample.last_date


def test_b15_render_labels_out_of_sample():
    px = _predictive_panel()
    text = render_backtest(run_backtest(FakeSource(px), BacktestConfig(oos_start=px.index[500].date())))
    assert "out-of-sample" in text.lower() and "not untouched" in text.lower()


def test_b16_render_maps_the_composite_buckets_to_the_five_ratings():
    px = _predictive_panel()
    text = render_backtest(run_backtest(FakeSource(px), BacktestConfig(cost_bps=0)))
    assert "Rating buckets" in text
    for r in ("Sell", "Underweight", "Hold", "Overweight", "Buy"):
        assert r in text
    assert "price-only" in text.lower() and "not the full rating" in text.lower()
