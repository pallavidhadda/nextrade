"""A refresh never makes a report worse; gaps per report in the drift report; our own payout ratio; 8 NSE quarters."""
import json
import time
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
from fastapi.testclient import TestClient

from indiafacts import drift, nseapi
from indiafacts.api import REFRESH_FAILED, REFRESH_WORSE, create_app
from indiafacts.completeness import attention_items
from indiafacts.fundamentals import annual_facts, ratio_facts
from indiafacts.models import Entity, Fact, FactSet, PeriodType, Status
from indiafacts.pipeline import _payout_check
from indiafacts.snapshots import SnapshotClient, record_gaps, safe_name
from indiafacts.summary import REPORT_VERSION

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
GAP = {"metric": "pe_ttm", "period": "2026-11-10", "status": "gap", "reason": "x"}


# ---- refresh guard ----------------------------------------------------------------------------------------------

def snap_client(gaps: int):
    today = date.today().isoformat()
    files = {"index.json": {"TCS.NS": {"as_of": today, "ok": True, "error": None, "generated_at": "x", "commit": "abc"}},
             "TCS.NS.json": {"ticker": "TCS.NS", "snap": True, "report_version": REPORT_VERSION, "gaps": [GAP] * gaps}}

    def fetch(url):
        name = url.rsplit("/", 1)[1]
        return b"<html>snapshot</html>" if name.endswith(".html") else json.dumps(files[name]).encode()
    return SnapshotClient("http://x", fetch, ttl=100)


def runner_with_gaps(n):
    def run(opts, progress):
        return {"summary": {"ticker": opts["ticker"], "gaps": [GAP] * n}, "html": "<html>live</html>"}
    return run


def refresh(c):
    job_id = c.post("/api/analyze", json={"ticker": "TCS.NS", "refresh": True}).json()["job_id"]
    for _ in range(200):
        r = c.get(f"/api/jobs/{job_id}").json()
        if r["status"] in ("done", "error"):
            return r
        time.sleep(0.02)
    raise AssertionError(r)


def test_thinner_live_refresh_keeps_snapshot():
    j = refresh(TestClient(create_app(runner_with_gaps(9), snapshots=snap_client(2))))
    assert j["status"] == "done" and j["served_from"] == "snapshot" and j["summary"]["snap"] is True
    assert j["summary"]["refresh_note"] == REFRESH_WORSE and j["refresh_note"] == REFRESH_WORSE


def test_equal_or_fuller_live_refresh_is_shown():
    for n in (2, 0):
        j = refresh(TestClient(create_app(runner_with_gaps(n), snapshots=snap_client(2))))
        assert j["served_from"] == "live" and "refresh_note" not in j["summary"]


def test_failed_live_refresh_keeps_snapshot():
    def boom(opts, progress):
        raise ValueError("Yahoo down")
    j = refresh(TestClient(create_app(boom, snapshots=snap_client(2))))
    assert j["status"] == "done" and j["served_from"] == "snapshot" and j["summary"]["refresh_note"] == REFRESH_FAILED


def test_failed_live_run_without_snapshot_is_an_error():
    def boom(opts, progress):
        raise ValueError("Yahoo down")
    assert refresh(TestClient(create_app(boom, snapshots=None)))["status"] == "error"


# ---- gaps per report ----------------------------------------------------------------------------------------------

def summaries(counts):
    return {f"T{i}.NS": {"gaps": [{"metric": f"m{j}"} for j in range(n)]} for i, n in enumerate(counts)}


def test_gap_stats():
    g = drift.gap_stats(summaries([0, 2, 4, 10]))
    assert g["reports"] == 4 and g["median"] == 3 and g["max"] == 10 and g["share_over"] == 0.25
    assert g["worst"][0] == ["T3.NS", 10] and g["top_metrics"][0] == ["m0", 3]


def test_gap_rise_is_breaking_and_opens_reports_issue():
    rep = drift.add_gap_stats({"status": "ok", "checks": [], "disabled_fields": [], "generated_at": "t"},
                              summaries([8, 9, 10]), drift.gap_stats(summaries([1, 2, 3])))
    assert rep["status"] == "breaking" and drift.breaking_sources(rep) == ["reports"]
    title, body = drift.issue_plan(rep)[0]
    assert title == "Source drift: reports" and "Most-missing figures" in body and "were published" in body
    assert "Gaps per report" in drift.summary_markdown(rep)


def test_small_change_is_info_and_keeps_status():
    rep = drift.add_gap_stats({"status": "warning", "checks": [{"source": "marketlens", "check": "x", "field": None,
                                                                  "severity": "warning", "detail": ""}], "disabled_fields": []},
                              summaries([2, 3]), drift.gap_stats(summaries([2, 2])))
    assert rep["status"] == "warning" and [c["severity"] for c in rep["checks"] if c["check"] == "gaps_per_report"] == ["info"]


def test_record_gaps_writes_drift_report(tmp_path):
    for t, n in (("A.NS", 1), ("B.NS", 3)):
        (tmp_path / f"{safe_name(t)}.json").write_text(json.dumps({"gaps": [GAP] * n}))
    index = {"A.NS": {"ok": True}, "B.NS": {"ok": True}, "C.NS": {"ok": False}}
    rep = record_gaps(tmp_path, ["A.NS", "B.NS", "C.NS"], index, None, log=lambda *_: None)
    saved = json.loads((tmp_path / "drift_report.json").read_text())
    assert rep["gaps"]["reports"] == 2 and saved["gaps"]["median"] == 2
    assert json.loads((tmp_path / "index.json").read_text())["_meta"]["drift_status"] == "ok"


# ---- payout ratio -------------------------------------------------------------------------------------------------

def statements(dividends=True):
    cols = [pd.Timestamp("2026-03-31"), pd.Timestamp("2025-03-31")]
    inc = pd.DataFrame({c: {"Total Revenue": 1000.0, "Net Income": 200.0} for c in cols})
    bal = pd.DataFrame({c: {"Stockholders Equity": 2000.0, "Total Assets": 5000.0} for c in cols})
    cf = pd.DataFrame({c: ({"Free Cash Flow": 50.0, "Cash Dividends Paid": -60.0} if dividends else {"Free Cash Flow": 50.0}) for c in cols})
    return {"income": inc, "balance": bal, "cashflow": cf}


def ratios(dividends=True):
    facts = annual_facts("X.NS", statements(dividends), sector="Industrials", now=NOW)
    fs = FactSet(entity=Entity.from_ticker("X.NS").model_copy(update={"sector": "Industrials"}), facts=facts, retrieved_at=NOW)
    return facts, {f.metric: f for f in ratio_facts(fs, now=NOW)}


def test_payout_ratio_from_cash_flow():
    facts, r = ratios()
    assert float(r["fy_payout_ratio"].value) == 0.3
    div = [f for f in facts if f.metric == "fy_dividends_paid"]
    assert div and float(div[0].value) == 60                     # paid out, shown positive
    assert float(r["fy_roe"].value) == 0.1 and float(r["fy_roa"].value) == 0.04


def test_no_dividend_row_is_not_a_gap():
    facts, r = ratios(dividends=False)
    assert "fy_payout_ratio" not in r and not any(f.metric == "fy_dividends_paid" for f in facts)


def test_payout_alias_fills_yahoo_gap():
    _, r = ratios()
    g = Fact.make(entity_key="X.NS", metric="payout_ratio", value=None, unit="ratio", period_end=date(2026, 11, 10),
                  period_type=PeriodType.point, source="yahoo", retrieved_at=NOW, status=Status.gap, reason="not provided by Yahoo")
    assert attention_items([g, r["fy_payout_ratio"]]) == []


def point(metric, v, source="nse_marketlens"):
    return Fact.make(entity_key="X.NS", metric=metric, value=Decimal(str(v)), unit="ratio", period_end=date(2026, 11, 9),
                     period_type=PeriodType.point, source=source, retrieved_at=NOW, status=Status.ok)


def test_payout_cross_check_notice_only_when_far_apart():
    notes: list[str] = []
    _payout_check([point("fy_payout_ratio", 0.3, "computed:fundamentals"), point("dividend_yield", 0.015), point("pe_ttm", 20)], notes)
    assert notes == []                                            # 0.30 vs 0.30
    _payout_check([point("fy_payout_ratio", 0.3, "computed:fundamentals"), point("dividend_yield", 0.05), point("pe_ttm", 20)], notes)
    assert len(notes) == 1 and "30%" in notes[0] and "100%" in notes[0]


# ---- NSE quarters -------------------------------------------------------------------------------------------------

def test_nse_keeps_eight_quarters():
    import inspect

    assert nseapi.RESULT_QUARTERS == 8
    for fn in (nseapi.NseApi._live_results, nseapi.NseApi.quarterly_filings, nseapi.NseApi.quarterly_xbrl):
        assert inspect.signature(fn).parameters["n"].default == 8
