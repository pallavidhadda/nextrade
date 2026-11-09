from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from indiafacts.checklist import CheckResult
from indiafacts.debate import build_debate, load_stance_params
from indiafacts.models import Entity, Fact, FactSet
from indiafacts.scoring import FactorScore, ScoreResult

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
ASOF = date(2026, 11, 2)
BANNED = ("buy", "sell", "undervalued", "overvalued", "target", "guarantee", "will rise", "will fall")


def fs_with(**vals):
    facts = [Fact.make(entity_key="ABC.NS", metric=m, value=Decimal(str(v)), unit="ratio", period_end=ASOF, period_type="point",
                       source="computed:valuation" if m.startswith("implied_growth") else "computed",
                       source_field="series:x" if not m.startswith("implied_growth") else "assumption", retrieved_at=NOW)
             for m, v in vals.items()]
    return FactSet(entity=Entity.from_ticker("ABC.NS"), facts=facts, retrieved_at=NOW)


def sc_with(overall, factors, checks, status="ok"):
    r = ScoreResult(ticker="ABC.NS", status=status, overall=overall if status == "ok" else None, rank=3, n=30, reason="" if status == "ok" else "too few factors",
                    factors={k: FactorScore(score=v, coverage=1.0 if v is not None else 0.0, reason="" if v is not None else "coverage 0%") for k, v in factors.items()})
    cl = [CheckResult(id=i, label=i.replace("_", " "), result=res, display="x", threshold="> 0", value=1.0 if res != "unavailable" else None)
          for i, res in checks.items()]
    return {"result": r, "checklist": cl, "n": 30, "checklist_summary": "x"}


STRONG = sc_with(72, {"value": 70, "quality": 80, "growth": 66, "momentum": 60, "risk": 70},
                 {"profitable_latest_quarter": "pass", "debt_moderate": "pass", "revenue_growing": "pass", "positive_1y_return": "pass"})
WEAK = sc_with(25, {"value": 20, "quality": 30, "growth": 15, "momentum": 22, "risk": 40},
               {"profitable_latest_quarter": "fail", "debt_moderate": "fail", "positive_1y_return": "fail", "beats_nifty_1y": "fail"})


def test_d1_strong_profile_leans_positive_with_cited_bull_points():
    d = build_debate(fs_with(implied_growth_r12_n10=0.07 * 100, max_drawdown_3y=-0.2, volatility_1y=0.2), STRONG)
    assert d.stance.label in ("Overweight", "Buy") and d.stance.confidence in ("Medium", "High")
    assert len(d.bull) >= 3 and len(d.bull) > len(d.bear)
    assert all(p.key for p in d.bull + d.bear)


def test_d2_weak_profile_leans_negative_with_bear_points():
    d = build_debate(fs_with(implied_growth_r12_n10=22.0, max_drawdown_3y=-0.55, volatility_1y=0.42), WEAK)
    assert d.stance.label in ("Underweight", "Sell") and len(d.bear) > len(d.bull)
    assert any("implies" in p.text.lower() for p in d.bear) and any("drawdown" in p.text.lower() for p in d.bear)


def test_d3_mixed_profile_is_neutral():
    mixed = sc_with(50, {"value": 60, "quality": 40, "growth": 50, "momentum": 45, "risk": 55},
                    {"profitable_latest_quarter": "pass", "positive_1y_return": "fail"})
    assert build_debate(fs_with(), mixed).stance.label == "Hold"


def test_d4_abstained_or_missing_score_gives_no_stance():
    d = build_debate(fs_with(), sc_with(None, {"momentum": 50, "risk": 40}, {}, status="abstain"))
    assert d.stance.label == "No rating" and "too few" in d.stance.reason
    assert build_debate(fs_with(), None).stance.label == "No rating"


def test_d5_confidence_drops_with_thin_coverage():
    # four factors with one fundamental pillar passes the gate but stays Low (fewer than five factors, other weak ingredients)
    thin = sc_with(70, {"value": None, "quality": 72, "growth": 66, "momentum": 70, "risk": 72},
                   {"profitable_latest_quarter": "pass", "positive_1y_return": "pass", "debt_moderate": "unavailable",
                    "revenue_growing": "unavailable"})
    thin["n"] = 6
    d = build_debate(fs_with(), thin)
    assert d.stance.label not in ("Insufficient evidence", "No rating") and d.stance.confidence == "Low"


# Reliance alpha run (2026-11-10): growth 50, momentum 75, risk 58; quality and value not scored; pool of 5 -> was "Overweight, low"
RELIANCE_ALPHA = sc_with(55.2, {"value": None, "quality": None, "growth": 50, "momentum": 75, "risk": 58},
                         {"profit_growth": "pass", "revenue_growing": "pass", "interest_cover": "pass", "positive_1y_return": "fail",
                          "beats_nifty_1y": "fail"})


def test_d9_gate_withholds_rating_without_fundamental_pillars():
    d = build_debate(fs_with(), RELIANCE_ALPHA)
    assert d.stance.label == "Insufficient evidence" and d.stance.confidence == "n/a" and d.stance.partial
    assert "Quality and Value could not be scored" in d.stance.reason and "partial research snapshot" in d.stance.reason
    assert d.bull and d.bear                     # the evidence is still shown, only the rating is withheld
    assert not any(w in d.stance.reason.lower() for w in BANNED)


def test_d9_gate_passes_with_both_pillars_or_four_factors_with_one():
    both = sc_with(60, {"value": 60, "quality": 62, "growth": None, "momentum": None, "risk": 55}, {})
    assert build_debate(fs_with(), both).stance.label not in ("Insufficient evidence", "No rating")
    three_one = sc_with(60, {"value": None, "quality": 62, "growth": 55, "momentum": 70, "risk": None}, {})
    assert build_debate(fs_with(), three_one).stance.label == "Insufficient evidence"
    assert not build_debate(fs_with(), STRONG).stance.partial


def test_d9_gate_threshold_comes_from_params():
    p = load_stance_params(strict=False)
    p["evidence_gate"] = {"min_factors_with_one_fundamental": 3}
    three_one = sc_with(60, {"value": None, "quality": 62, "growth": 55, "momentum": 70, "risk": None}, {})
    assert build_debate(fs_with(), three_one, params=p).stance.label != "Insufficient evidence"


def test_d9_no_scenario_plan_without_a_rating():
    from indiafacts.debate import has_direction
    from indiafacts.scenario import build_scenario
    d = build_debate(fs_with(), RELIANCE_ALPHA)
    assert not has_direction(d.stance.label) and not has_direction("No rating") and has_direction("Hold")
    sc = build_scenario(fs_with(), d, levels=None, panel=None, today=ASOF)
    assert not sc.applies and "not enough for a rating" in sc.reason


def test_d6_no_opinion_words_and_every_point_has_a_reason_text():
    for sc in (STRONG, WEAK):
        d = build_debate(fs_with(implied_growth_r12_n10=18.0, max_drawdown_3y=-0.5, volatility_1y=0.4), sc)
        for p in d.bull + d.bear + [d.stance]:
            text = (getattr(p, "text", "") or getattr(p, "reason", "")).lower()
            assert text and not any(w in text for w in BANNED), text


def test_d7_params_have_review_date_and_strict_overdue_fails():
    assert load_stance_params(today=ASOF)["bull_factor_min"] > load_stance_params(today=ASOF)["bear_factor_max"]
    with pytest.raises(ValueError):
        load_stance_params(today=date(2031, 1, 1), strict=True)


def test_d7_confidence_uses_pool_size_edges_and_disagreement():
    strong = dict(STRONG)
    big = {**strong, "n": 30}
    small = {**strong, "n": 8}
    hi = build_debate(fs_with(fy_roce=0.2), big).stance
    lo = build_debate(fs_with(fy_roce=0.2), small).stance
    order = {"Low": 0, "Medium": 1, "High": 2}
    assert order[lo.confidence] <= order[hi.confidence]
    assert "small comparison pool" in lo.reason or lo.confidence == "High"
    # score says strong, evidence points say weak: disagreement must not give High
    conflict = sc_with(72, {"value": 70, "quality": 80, "growth": 66, "momentum": 60, "risk": 70},
                       {"debt_moderate": "fail", "revenue_growing": "fail", "positive_1y_return": "fail", "beats_nifty_1y": "fail", "near_52w_high": "fail"})
    assert build_debate(fs_with(), conflict).stance.confidence != "High"


def test_d8_confidence_is_not_nearly_always_high():
    """Across varied inputs the label must spread; the old rule gave High almost every time."""
    labels = set()
    for overall, n in ((52, 8), (45, 12), (70, 30), (30, 30)):
        sc = sc_with(overall, {"value": overall, "quality": overall + 5, "growth": overall - 5, "momentum": overall, "risk": overall},
                     {"profitable_latest_quarter": "pass", "debt_moderate": "unavailable", "revenue_growing": "unavailable"})
        sc["n"] = n
        labels.add(build_debate(fs_with(), sc).stance.confidence)
    assert len(labels) >= 2
