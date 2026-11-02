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
    assert d.stance.label in ("Positive lean", "Strong positive lean") and d.stance.confidence in ("Medium", "High")
    assert len(d.bull) >= 3 and len(d.bull) > len(d.bear)
    assert all(p.key for p in d.bull + d.bear)


def test_d2_weak_profile_leans_negative_with_bear_points():
    d = build_debate(fs_with(implied_growth_r12_n10=22.0, max_drawdown_3y=-0.55, volatility_1y=0.42), WEAK)
    assert d.stance.label in ("Negative lean", "Strong negative lean") and len(d.bear) > len(d.bull)
    assert any("implies" in p.text.lower() for p in d.bear) and any("drawdown" in p.text.lower() for p in d.bear)


def test_d3_mixed_profile_is_neutral():
    mixed = sc_with(50, {"value": 60, "quality": 40, "growth": 50, "momentum": 45, "risk": 55},
                    {"profitable_latest_quarter": "pass", "positive_1y_return": "fail"})
    assert build_debate(fs_with(), mixed).stance.label == "Neutral"


def test_d4_abstained_or_missing_score_gives_no_stance():
    d = build_debate(fs_with(), sc_with(None, {"momentum": 50, "risk": 40}, {}, status="abstain"))
    assert d.stance.label == "No stance" and "too few" in d.stance.reason
    assert build_debate(fs_with(), None).stance.label == "No stance"


def test_d5_confidence_drops_with_thin_coverage():
    thin = sc_with(70, {"value": None, "quality": None, "growth": None, "momentum": 70, "risk": 72},
                   {"profitable_latest_quarter": "pass", "positive_1y_return": "pass", "debt_moderate": "unavailable"})
    d = build_debate(fs_with(), thin)
    assert d.stance.confidence == "Low"


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
