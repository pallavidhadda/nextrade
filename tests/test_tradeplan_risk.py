from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from indiafacts.models import Entity, Fact, FactSet
from indiafacts.profile import InvestorProfile, default_profile
from indiafacts.riskpanel import build_risk_panel, load_risk_lenses
from indiafacts.tradeplan import load_levels_params, reference_levels

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
ASOF = date(2026, 11, 2)
BANNED = ("buy", "sell", "undervalued", "overvalued", "guarantee", "will rise", "will fall", "target price")


def fs_with(**vals):
    facts = [Fact.make(entity_key="ABC.NS", metric=m, value=None if v is None else Decimal(str(v)), unit="INR", period_end=ASOF, period_type="point",
                       source="computed", source_field="series:s1|window:x", retrieved_at=NOW,
                       status="ok" if v is not None else "unavailable", reason="" if v is not None else "n/a") for m, v in vals.items()]
    return FactSet(entity=Entity.from_ticker("ABC.NS"), facts=facts, retrieved_at=NOW)


FULL = dict(last_close=100, avg_move_14=2, high_52w=130, low_52w=70, sma_50=95, sma_200=90)


def test_l1_bullish_rating_gets_stop_targets_and_ratio():
    lv = reference_levels(fs_with(**FULL), "Buy")
    assert lv.applies and lv.stop == pytest.approx(94.0) and lv.risk_pct == pytest.approx(6.0)
    assert lv.targets == [pytest.approx(109.0), pytest.approx(118.0)] and lv.reward_risk == [1.5, 3.0]


def test_l2_stop_never_below_the_52_week_low():
    lv = reference_levels(fs_with(**{**FULL, "avg_move_14": 20, "low_52w": 70}), "Overweight")
    assert lv.stop == pytest.approx(70.0)


def test_l3_non_bullish_rating_lists_support_and_resistance_only():
    lv = reference_levels(fs_with(**FULL), "Hold")
    assert not lv.applies and lv.stop is None and lv.targets == []
    assert [n for n, _ in lv.support] == ["50-day average", "200-day average", "52-week low"]
    assert [n for n, _ in lv.resistance] == ["52-week high"]


def test_l4_missing_inputs_give_a_reason_not_a_guess():
    lv = reference_levels(fs_with(**{**FULL, "avg_move_14": None}), "Buy")
    assert not lv.applies and "average move" in lv.reason.lower()
    assert reference_levels(fs_with(), "Buy").reason


def test_l5_params_have_review_date():
    assert load_levels_params(today=ASOF)["stop_multiple"] > 0
    with pytest.raises(ValueError):
        load_levels_params(today=date(2031, 1, 1), strict=True)


def vals(vol=0.30, dd=-0.30, beta=1.0):
    return fs_with(volatility_1y=vol, max_drawdown_3y=dd, beta_1y=beta)


def test_r1_each_lens_checks_volatility_drawdown_and_beta():
    panel = build_risk_panel(vals(vol=0.45, dd=-0.50, beta=1.3), default_profile(), None)
    by = {l.name: l for l in panel.lenses}
    assert by["aggressive"].fits and not by["neutral"].fits and not by["conservative"].fits
    assert any("volatility" in b for b in by["neutral"].breaches) and any("drawdown" in b for b in by["neutral"].breaches)
    assert any("beta" in b for b in by["neutral"].breaches)


def test_r2_position_ceiling_is_risk_over_stop_distance_capped_by_profile():
    lv = reference_levels(fs_with(**FULL), "Buy")                           # stop distance 6%
    prof = InvestorProfile(**{**default_profile().model_dump(), "max_single_stock_pct": 10})
    panel = build_risk_panel(vals(), prof, lv)
    by = {l.name: l for l in panel.lenses}
    assert by["neutral"].max_position_pct == pytest.approx(10.0)             # 1.0 / 6 * 100 = 16.7, capped at 10
    assert by["conservative"].max_position_pct == pytest.approx(0.5 / 6 * 100)


def test_r3_profile_lens_is_marked_and_follows_effective_risk():
    low = InvestorProfile(**{**default_profile().model_dump(), "risk_tolerance": "low", "risk_capacity": "low"})
    assert build_risk_panel(vals(), low, None).profile_lens == "conservative"


def test_r4_missing_measurements_say_unavailable():
    panel = build_risk_panel(fs_with(), default_profile(), None)
    assert all(l.fits is None and l.reason for l in panel.lenses) and all(l.max_position_pct is None for l in panel.lenses)


def test_r5_texts_have_no_opinion_words_and_config_is_reviewed():
    panel = build_risk_panel(vals(vol=0.9, dd=-0.8, beta=2.0), default_profile(), None)
    for l in panel.lenses:
        assert not any(w in " ".join(l.breaches).lower() for w in BANNED)
    assert load_risk_lenses(today=ASOF)["lenses"]["neutral"]["volatility_max"] > 0
    with pytest.raises(ValueError):
        load_risk_lenses(today=date(2031, 1, 1), strict=True)
