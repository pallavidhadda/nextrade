import pytest
from streamlit.testing.v1 import AppTest

from pathlib import Path

from indiafacts import webui

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")

SUMMARY = {
    "ticker": "ABC.NS", "name": "ABC Ltd", "sector": "Energy", "industry": "Refining", "isin": "INE000A01000",
    "profile": {"horizon": "5y+", "risk": "medium", "experience": "beginner"},
    "key_facts": [{"metric": "revenue", "value": 3.09468e12, "unit": "INR", "period": "Q1 FY27", "source": "yahoo", "basis": "unknown", "fact_id": "a1"},
                  {"metric": "pe_ttm", "value": 19.2, "unit": "ratio", "period": "2026-10-31", "source": "yahoo", "basis": "unknown", "fact_id": "a2"}],
    "score": {"status": "ok", "overall": 45.0, "rank": 24, "n": 30, "reason": "", "pool": "the built-in pool of 30 large companies", "flags": [],
              "factors": {"growth": {"score": None, "coverage": 0, "reason": "coverage 0% < 60%"}, "risk": {"score": 65.0, "coverage": 1, "reason": ""}}},
    "checklist": [{"label": "Latest quarter profit is positive", "result": "pass", "display": "₹20,946 cr", "threshold": "> 0", "reason": ""},
                  {"label": "Revenue is higher than a year earlier", "result": "unavailable", "display": "", "threshold": "", "reason": "no data"}],
    "gaps": [{"metric": "roe", "period": "2026-10-31", "status": "unavailable", "reason": "not provided by Yahoo"}],
    "notices": [], "changes": [],
    "valuation": {"method": "reverse_dcf_earnings", "assumptions": "assumption: terminal growth 5%", "unavailable_reason": None,
                  "items": [{"metric": "implied_growth_r12_n10", "value": 8.4, "unit": "percent", "fact_id": "v1"}]},
    "explanation": {"source": "template", "summary": "The company scores 45.0 of 100.", "uncertainty": "Some items are missing.",
                    "claims": [{"type": "fact", "text": "Score is 45.0.", "ids": ["F1"]}], "triggers": [], "usage": {}},
    "debate": {"bull": [{"text": "Quality scores 80 of 100 against the comparison pool", "evidence": "score:quality"}],
               "bear": [{"text": "Check failed: price is higher than a year ago", "evidence": "check:positive_1y_return"}],
               "stance": {"label": "Neutral", "confidence": "Medium", "reason": "overall score 45.0 of 100 and 1 supporting against 1 cautionary points"}},
    "news": [{"title": "<b>Shares surge</b> on record order", "publisher": "Wire", "published": "2026-11-01", "url": "", "sentiment_hint": "positive"}],
    "llm": None, "disclaimer": "Research and education only. Not financial, investment or trading advice.",
}


def test_ticker_validation():
    assert webui.valid_ticker(" reliance.ns ") == "RELIANCE.NS"
    for bad in ("", "../x", "A B", "--html", "X" * 40):
        assert webui.valid_ticker(bad) is None


def test_value_formatting_matches_the_web_app():
    assert webui.format_value(209460000000, "INR") == "₹20,946 cr"
    assert webui.format_value(16103642234880, "INR") == "₹16.10 lakh cr"
    assert webui.format_value(None, "INR") == "n/a" and webui.format_value(19.2, "ratio") == "19.20"


def test_html_escapes_model_text():
    s = {**SUMMARY, "explanation": {**SUMMARY["explanation"], "summary": "<script>alert(1)</script>",
                                    "claims": [{"type": "fact", "text": "<img src=x onerror=1>", "ids": ["F1"]}]}}
    out = webui.explanation_html(s)
    assert "<script>" not in out and "<img" not in out and "&lt;script&gt;" in out


def test_cards_show_score_gaps_and_labels():
    assert "45.0" in webui.score_html(SUMMARY) and "Not scored" in webui.score_html(SUMMARY)
    assert "Pass" in webui.checklist_html(SUMMARY) and "Unavailable" in webui.checklist_html(SUMMARY)
    assert "not provided by Yahoo" in webui.gaps_html(SUMMARY)
    assert "8.4% a year" in webui.valuation_html(SUMMARY) and "not a forecast" in webui.valuation_html(SUMMARY).lower()
    assert "₹3.09 lakh cr" in webui.facts_html(SUMMARY)


def fake_runner(opts, progress):
    progress("1/2 TCS.NS")
    return {"summary": {**SUMMARY, "ticker": opts["ticker"]}, "html": "<html><body>full report</body></html>"}


def test_app_landing_has_disclaimer_and_no_key_field(monkeypatch):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Not financial, investment or trading advice" in text
    assert not [t for t in at.text_input if t.type == "password"]


def test_app_rejects_bad_ticker(monkeypatch):
    monkeypatch.setattr(webui, "RUNNER", fake_runner)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input[0].set_value("../etc")
    at.button[0].click().run()
    assert at.error and "ticker" in at.error[0].value.lower()
    assert "result" not in at.session_state


def test_app_runs_and_shows_result(monkeypatch):
    monkeypatch.setattr(webui, "RUNNER", fake_runner)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input[0].set_value("tcs.ns")
    at.button[0].click().run()
    assert not at.exception
    joined = " ".join(m.value for m in at.markdown)
    assert "45.0" in joined and "TCS.NS" in joined
    assert [t.label for t in at.tabs] == ["Summary", "Full report", "Gaps (1)"]


def test_debate_and_news_cards_escape_and_label():
    d = webui.debate_html(SUMMARY)
    assert "Bull case" in d and "Bear case" in d and "Neutral" in d and "not a recommendation" in d
    n = webui.news_html(SUMMARY)
    assert "&lt;b&gt;Shares surge" in n and "<b>Shares" not in n and "unverified" in n.lower()
    assert webui.debate_html({}) == "" and webui.news_html({"news": []}) == ""
