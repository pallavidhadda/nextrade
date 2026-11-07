from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from indiafacts.debate import Debate, Point, Stance
from indiafacts.digest import BANNED_WORDS
from indiafacts.models import Entity, Fact, FactSet
from indiafacts.riskpanel import Lens, RiskPanel
from indiafacts.scenario import build_scenario, scenario_lines
from indiafacts.tradeplan import Levels

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)
FS = FactSet(entity=Entity.from_ticker("ABC.NS"), facts=[
    Fact.make(entity_key="ABC.NS", metric="net_income", value=Decimal(5), unit="INR", period_end=date(2026, 9, 30), period_type="Q",
              source="yahoo", retrieved_at=NOW)], retrieved_at=NOW)
PANEL = RiskPanel([Lens("neutral", True, [], 6.0)], "neutral")


def levels(applies=True):
    return Levels(applies=applies, last_close=100.0, stop=88.0 if applies else None, risk_pct=12.0, sizing_risk_pct=12.0,
                  targets=[118.0, 136.0] if applies else [], reward_risk=[1.5, 3.0] if applies else [],
                  support=[("50-day average", 95.0), ("52-week low", 80.0)], resistance=[("200-day average", 108.0), ("52-week high", 130.0)])


def deb(label, conf="High"):
    return Debate(bull=[Point("Quality scores 80 of 100", "score:quality")], bear=[Point("Momentum scores only 20 of 100", "score:momentum")],
                  stance=Stance(label, conf, "x"))


@pytest.mark.parametrize("label,tone", [("Overweight", "constructive"), ("Buy", "constructive"), ("Hold", "neutral"), ("Underweight", "cautious"), ("Sell", "cautious")])
def test_every_rating_gets_a_plan_with_levels_and_stages(label, tone):
    sc = build_scenario(FS, deb(label), levels(label in ("Buy", "Overweight")), PANEL, today=date(2026, 11, 7))
    assert sc.applies and sc.tone == tone and sc.levels and sc.stages and sc.watch
    assert all(v > 0 for _, v, _ in sc.levels)


def test_constructive_plan_stages_split_the_ceiling_in_thirds_and_halve_on_low_confidence():
    sc = build_scenario(FS, deb("Overweight"), levels(), PANEL, today=date(2026, 11, 7))
    assert [round(p, 2) for _, p, _ in sc.stages] == [2.0, 2.0, 2.0]
    low = build_scenario(FS, deb("Overweight", "Low"), levels(), PANEL, today=date(2026, 11, 7))
    assert [round(p, 2) for _, p, _ in low.stages] == [1.0, 1.0, 1.0] and any("halved" in n for n in low.notes)


def test_neutral_plan_adds_nothing_now_and_cautious_caps_at_a_third():
    n = build_scenario(FS, deb("Hold"), levels(False), PANEL, today=date(2026, 11, 7))
    assert n.stages[0][1] == 0.0 and any(l == "Upside trigger" for l, _, _ in n.levels)
    c = build_scenario(FS, deb("Underweight"), levels(False), PANEL, today=date(2026, 11, 7))
    assert c.stages[0][1] == 2.0


def test_next_results_date_and_what_would_change_the_view():
    sc = build_scenario(FS, deb("Hold"), levels(False), PANEL, today=date(2026, 11, 7))
    assert any("Next quarterly results are due by" in w for w in sc.watch)
    assert sc.more_positive_if == ["Momentum scores only 20 of 100"] and sc.more_cautious_if == ["Quality scores 80 of 100"]


def test_no_rating_or_no_price_means_no_plan_and_no_advice_words():
    assert not build_scenario(FS, Debate(), levels(), PANEL).applies
    assert not build_scenario(FS, deb("Hold"), Levels(), PANEL).applies
    import re
    for label in ("Overweight", "Hold", "Underweight"):
        text = "\n".join(scenario_lines(build_scenario(FS, deb(label), levels(label == "Overweight"), PANEL, today=date(2026, 11, 7)))).lower()
        assert not any(re.search(rf"\b{w}\b", text) for w in BANNED_WORDS), (label, text)
