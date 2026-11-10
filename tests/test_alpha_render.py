"""Renderers state how sure the report is: partial snapshots, completeness, score decomposition, rank caveats, stamp."""
from datetime import date

from indiafacts.debate import Debate, Stance
from indiafacts.htmlreport import build_html
from indiafacts.render import exec_view, level_formula, render
from indiafacts.checklist import CheckResult
from indiafacts.scoring import FactorContribution, FactorScore, MissingFactor, ScoreResult
from tests.test_render import reliance

STAMP = {"report_id": "abc123def0", "ticker": "RELIANCE.NS", "as_of": "2026-11-09", "pool_size": 6, "pool_members": [],
         "params_hash": "b828fb090c36", "commit": "c24d2c8", "llm_model": None}
COMP = {"level": "Low", "reason": "average pillar coverage 40%", "overall_coverage_pct": 40.0, "stale_total": 2, "issues_total": 3,
        "pillars": {"own": {"label": "Ownership", "coverage_pct": 0.0}, "val": {"label": "Valuation", "coverage_pct": 50.0},
                    "qual": {"label": "Quality", "coverage_pct": 60.0}, "px": {"label": "Prices", "coverage_pct": 100.0}},
        "conflicts": [{"metric": "revenue", "period": "2026-09-30", "chosen": {"value": "100", "source": "nse", "unit": "INR"},
                       "alternative": {"value": "90", "source": "yahoo", "unit": "INR"}, "reason": "sources differ by 10%"}]}
SUMMARY = {
    "debate": {"stance": {"label": "Insufficient evidence", "confidence": "n/a", "reason": "quality and value are missing", "partial": True},
               "bull": [], "bear": []},
    "completeness": COMP, "stamp": STAMP, "scenario_reason": "no scenario plan: the evidence is not enough for a rating",
    "explanation": {"triggers": [{"text": "Needs data: ROE"}]},
    "score": {"overall": 50.0, "rank": 3, "n": 6, "pool_failed": 4, "factors": {},
              "contributions": {"growth": {"score": 40.0, "base_weight": 0.2, "effective_weight": 0.5, "contribution": 20.0},
                                "risk": {"score": 60.0, "base_weight": 0.2, "effective_weight": 0.5, "contribution": 30.0}},
              "missing_factors": [{"factor": "quality", "base_weight": 0.35, "reason": ""}, {"factor": "value", "base_weight": 0.25, "reason": ""}]},
}


def test_exec_view_wording():
    x = exec_view(SUMMARY)
    assert x["meaning"].startswith("Partial research snapshot — no rating: quality and value are missing")
    assert x["missing"][0] == "Ownership: 0% covered" and len(x["missing"]) == 3
    assert x["comp"]["tone"] == "bad" and x["decomp"]["total"] == 50.0
    assert x["decomp"]["sentence"] == "Quality (35%) and Value (25%) could not be scored: their weight moved to the remaining factors."
    assert "rank 3 of 6 in a comparison set of 6 (small: rank is unstable)" in x["rank_notes"]
    assert "4 of 10 comparison companies could not be loaded" in x["rank_notes"]
    assert x["stamp_line"] == "Report abc123def0 · data as of 2026-11-09 · rules b828fb090c36 · build c24d2c8"


def test_level_formula_inline():
    f = level_formula(1267.0, 1324.0, 1267.0, [(1.5, 1409.5)])
    assert f == "₹1,267 = last close ₹1,324 − 3 × average daily move ₹19"


def _scorecard():
    r = ScoreResult(ticker="RELIANCE.NS", status="ok", overall=50.0, rank=3, n=6, config_hash="h",
                    factors={"growth": FactorScore(score=40.0, coverage=1.0), "risk": FactorScore(score=60.0, coverage=1.0)},
                    contributions={"growth": FactorContribution(score=40.0, base_weight=0.2, effective_weight=0.5, contribution=20.0, coverage=1.0, n_metrics=2),
                                   "risk": FactorContribution(score=60.0, base_weight=0.2, effective_weight=0.5, contribution=30.0, coverage=1.0, n_metrics=2)},
                    missing_factors=[MissingFactor(factor="quality", base_weight=0.35), MissingFactor(factor="value", base_weight=0.25)])
    return {"result": r, "checklist": [], "n": 6, "checklist_summary": "0 passed", "failed": {"A.NS": "x", "B.NS": "y"}, "pool": "p.txt",
            "members": ["RELIANCE.NS"], "peers": None, "peer_comparisons": []}


def _debate():
    return Debate(stance=Stance("Insufficient evidence", "n/a", "quality and value are missing", partial=True))


def test_text_and_html_reports_state_partial_snapshot_completeness_and_stamp():
    fs = reliance()
    kw = dict(scorecard=_scorecard(), debate=_debate(), stamp=STAMP)
    text = render(fs, as_of=date(2026, 11, 9), **kw)
    for needle in ("Partial research snapshot — no rating", "WHAT IS MISSING", "DATA COMPLETENESS:", "could not be scored: their weight moved",
                   "rank 3 of 6 in a comparison set of 6 (small: rank is unstable)", "2 of 8 comparison companies could not be loaded",
                   "Report abc123def0 · data as of 2026-11-09 · rules b828fb090c36 · build c24d2c8"):
        assert needle in text, needle
    html = build_html(fs, scorecard=_scorecard(), as_of=date(2026, 11, 9), debate=_debate(), stamp=STAMP)
    for needle in ("Partial research snapshot — no rating", 'id="completeness"', "could not be scored: their weight moved",
                   "Report abc123def0 · data as of 2026-11-09 · rules b828fb090c36 · build c24d2c8", "Sum of contributions"):
        assert needle in html, needle
