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
NOTE = "Insufficient evidence: quality and value could not be scored, so this rating rests on growth and risk only."
COMP = {"level": "Low", "reason": "average pillar coverage 40%", "overall_coverage_pct": 40.0, "stale_total": 2, "issues_total": 3,
        "verification": {"official_n": 0, "vendor_n": 5, "computed_n": 3, "label": "No figure comes from an official filing."},
        "pillars": {"ownership": {"label": "Ownership", "coverage_pct": 40.0, "vendor_only": True, "expected_n": 5, "fresh_ok": 2},
                    "valuation": {"label": "Valuation", "coverage_pct": 0.0, "expected_n": 6, "fresh_ok": 0},
                    "fundamentals": {"label": "Fundamentals", "coverage_pct": 50.0, "expected_n": 4, "fresh_ok": 2},
                    "price_history": {"label": "Price history", "coverage_pct": 100.0, "expected_n": 4, "fresh_ok": 4},
                    "balance_sheet": {"label": "Balance sheet", "coverage_pct": 80.0, "expected_n": 5, "fresh_ok": 4},
                    "filings": {"label": "Official filings", "coverage_pct": 0.0, "expected_n": 4, "fresh_ok": 0}},
        "conflicts": [{"metric": "revenue", "period": "2026-09-30", "chosen": {"value": "100", "source": "nse", "unit": "INR"},
                       "alternative": {"value": "90", "source": "yahoo", "unit": "INR"}, "reason": "sources differ by 10%"}]}
SUMMARY = {
    "debate": {"stance": {"label": "Overweight", "confidence": "Low", "reason": "overall score 50.0 of 100", "partial": True, "evidence_note": NOTE},
               "bull": [], "bear": []},
    "completeness": COMP, "stamp": STAMP, "scenario_reason": "",
    "explanation": {"triggers": [{"text": "Needs data: ROE (no data for roe)"}, {"text": "Whether the price climbs back above where it was a year ago (it is 10.4% lower now)."}]},
    "score": {"overall": 50.0, "rank": 3, "n": 6, "pool_failed": 4, "factors": {},
              "contributions": {"growth": {"score": 40.0, "base_weight": 0.2, "effective_weight": 0.5, "contribution": 20.0},
                                "risk": {"score": 60.0, "base_weight": 0.2, "effective_weight": 0.5, "contribution": 30.0}},
              "missing_factors": [{"factor": "quality", "base_weight": 0.35, "reason": ""}, {"factor": "value", "base_weight": 0.25, "reason": ""}]},
}


def test_exec_view_wording():
    x = exec_view(SUMMARY)
    assert x["meaning"] == f"Rule-based rating: Overweight, low confidence. {NOTE}"
    assert x["insufficient"] and x["directional"]
    assert x["missing"][0].startswith("Valuation (P/E, price-to-book, market value): not available, so we can't say whether the price is high or low")
    assert any(m.startswith("Ownership: only a data vendor's estimate, not the official exchange filing") for m in x["missing"])
    assert any(m.startswith("Company results") and "only partly found" in m for m in x["missing"])
    assert not any("Price history" in m or "Balance sheet" in m or "filings" in m.lower() for m in x["missing"])
    assert x["monitor"] == ["Whether the price climbs back above where it was a year ago (it is 10.4% lower now)."]
    c = x["comp"]
    assert c["words"] == "About half the figures are missing" and c["stale"] == "2 figures are out of date"
    assert ("Ownership", "Vendor estimate only") in c["items"] and ("Valuation", "Not found") in c["items"]
    assert ("Company results", "Partly found (2 of 4)") in c["items"] and ("Price history", "Complete") in c["items"]
    assert not any(n == "Official filings" or n == "filings" for n, _ in c["items"])
    assert c["verification"] == "No figure comes from an official filing."
    assert x["comp"]["tone"] == "bad" and x["decomp"]["total"] == 50.0
    assert x["decomp"]["sentence"] == "Quality (35%) and Value (25%) could not be scored: their weight moved to the remaining factors."
    assert "rank 3 of 6 in a comparison set of 6 (small: rank is unstable)" in x["rank_notes"]
    assert "4 of 10 comparison companies could not be loaded" in x["rank_notes"]
    assert x["stamp_line"] == "" and x["report_id"] == "abc123def0"


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
    return Debate(stance=Stance("Overweight", "Low", "overall score 50.0 of 100", partial=True, evidence_note=NOTE))


def test_exec_view_without_a_rating_has_no_duplicated_prefix():
    s = {"debate": {"stance": {"label": "No rating", "confidence": "n/a", "reason": "no rating because the score could not be computed (too few metrics)", "partial": True}}}
    x = exec_view(s)
    assert not x["directional"] and x["meaning"].count("o rating") == 1 and "too few metrics" in x["meaning"]


def test_text_and_html_reports_state_rating_with_insufficient_tag_completeness_and_stamp():
    fs = reliance()
    kw = dict(scorecard=_scorecard(), debate=_debate(), stamp=STAMP)
    text = render(fs, as_of=date(2026, 11, 9), **kw)
    for needle in ("Rule-based rating: Overweight, low confidence. " + NOTE, "WHAT IS MISSING", "HOW COMPLETE IS THE DATA: ",
                   "EDUCATIONAL RATING: Overweight [Insufficient evidence] (confidence Low)",
                   "could not be scored: their weight moved",
                   "rank 3 of 6 in a comparison set of 6 (small: rank is unstable)", "2 of 8 comparison companies could not be loaded"):
        assert needle in text, needle
    assert "rules b828fb090c36" not in text and "Report abc123def0" not in text
    assert "Partial research snapshot" not in text and "stale figures" not in text
    html = build_html(fs, scorecard=_scorecard(), as_of=date(2026, 11, 9), debate=_debate(), stamp=STAMP)
    for needle in ("Rule-based rating: Overweight, low confidence.", 'id="completeness"', "How complete is the data", "Insufficient evidence</span>",
                   "could not be scored: their weight moved",
                   "Report ID abc123def0", "Sum of contributions"):
        assert needle in html, needle
    assert "rules b828fb090c36" not in html and html.count("abc123def0") == 1
    assert "✕" not in html and "stale figures" not in html


def test_peer_pick_without_size_ratio_does_not_crash():
    from indiafacts.peers import NO_SIZE_NOTE, PeerGroup, PeerPick
    from indiafacts.render import peer_pick_text
    p = PeerPick(ticker="A.NS", tier=1, size_ratio=None, reason="r", fact_ids=[])
    assert peer_pick_text(p) == "same industry"
    assert peer_pick_text(PeerPick(ticker="B.NS", tier=2, size_ratio=1.5, reason="r", fact_ids=[])) == "same sector, 1.50x size"
    sc = {**_scorecard(), "peers": PeerGroup(target="RELIANCE.NS", picks=[p], size_matched=False, notes=[NO_SIZE_NOTE])}
    assert "A.NS (tier 1, same industry)" in render(reliance(), as_of=date(2026, 11, 9), scorecard=sc, debate=_debate(), stamp=STAMP)
    html = build_html(reliance(), scorecard=sc, as_of=date(2026, 11, 9), debate=_debate(), stamp=STAMP)
    assert "A.NS (same industry)" in html and NO_SIZE_NOTE in html
