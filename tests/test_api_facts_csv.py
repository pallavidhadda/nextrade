import csv
import io

from fastapi.testclient import TestClient

from indiafacts.api import create_app
from tests.test_api import wait

FACTS = [
    {"fact_id": "ab12", "metric": "revenue", "value": "123.45", "unit": "INR", "period_end": "2026-09-30", "period_type": "Q",
     "basis": "consolidated", "source": "nse", "status": "ok", "reason": "", "evidence": "https://example.com/x.pdf, row 4"},
    {"fact_id": "cd34", "metric": "pe_ttm", "value": None, "unit": "ratio", "period_end": "2026-09-30", "period_type": "point",
     "basis": "unknown", "source": "yahoo", "status": "unavailable", "reason": "=HYPERLINK(\"x\")", "evidence": ""},
]


def runner_with(facts):
    def run(opts, progress):
        s = {"ticker": opts["ticker"], "retrieved_at": "2026-11-10T00:00:00+00:00", "disclaimer": "d"}
        if facts is not None:
            s.update(facts=facts, facts_total=len(facts))
        return {"summary": s, "html": "<html></html>"}
    return run


def test_facts_csv_has_disclaimer_header_rows_and_safe_text():
    c = TestClient(create_app(runner_with(FACTS), snapshots=None))
    job = c.post("/api/analyze", json={"ticker": "RELIANCE.NS"}).json()["job_id"]
    done = wait(c, job)
    assert "facts" not in done["summary"]                           # not sent to the web page
    r = c.get(f"/api/jobs/{job}/facts.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="nextrade_RELIANCE_2026-11-10_facts.csv"'
    lines = r.text.splitlines()
    assert lines[0].startswith("# ") and "advice" in lines[0].lower()
    rows = list(csv.reader(io.StringIO("\n".join(lines[1:]))))
    assert rows[0] == ["fact_id", "metric", "value", "unit", "period_end", "period_type", "basis", "source", "status", "reason", "evidence"]
    assert rows[1][:3] == ["ab12", "revenue", "123.45"] and rows[1][-1] == "https://example.com/x.pdf, row 4"
    assert rows[2][2] == "" and rows[2][9].startswith("'=")           # missing stays empty; formula text is neutralised


def test_facts_csv_404_for_unknown_job_and_for_summary_without_facts():
    c = TestClient(create_app(runner_with(None), snapshots=None))
    assert c.get("/api/jobs/nope/facts.csv").status_code == 404
    job = c.post("/api/analyze", json={"ticker": "RELIANCE.NS"}).json()["job_id"]
    wait(c, job)
    assert c.get(f"/api/jobs/{job}/facts.csv").status_code == 404
