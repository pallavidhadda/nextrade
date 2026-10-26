import time

import pytest
from fastapi.testclient import TestClient

from indiafacts.api import create_app


def fake_runner(opts, progress):
    progress("1/2 RELIANCE.NS")
    return {"summary": {"ticker": opts["ticker"], "disclaimer": "Not financial, investment or trading advice"},
            "html": "<html><body>report</body></html>"}


def slow_runner(opts, progress):
    time.sleep(0.5)
    return fake_runner(opts, progress)


def wait(c, job_id, want="done"):
    for _ in range(100):
        r = c.get(f"/api/jobs/{job_id}").json()
        if r["status"] == want or r["status"] == "error":
            return r
        time.sleep(0.02)
    raise AssertionError(r)


def test_submit_poll_done_and_report():
    c = TestClient(create_app(fake_runner))
    r = c.post("/api/analyze", json={"ticker": "reliance.ns"})
    assert r.status_code == 202
    job = r.json()["job_id"]
    done = wait(c, job)
    assert done["status"] == "done" and done["summary"]["ticker"] == "RELIANCE.NS"
    rep = c.get(f"/api/jobs/{job}/report")
    assert rep.status_code == 200 and "report" in rep.text and rep.headers["content-type"].startswith("text/html")
    assert "default-src" in rep.headers.get("content-security-policy", "")


@pytest.mark.parametrize("bad", ["", "../../etc/passwd", "RELIANCE.NS; rm -rf /", "A" * 40, "X Y", "--html"])
def test_bad_tickers_rejected(bad):
    c = TestClient(create_app(fake_runner))
    assert c.post("/api/analyze", json={"ticker": bad}).status_code == 422


def test_unknown_options_rejected():
    c = TestClient(create_app(fake_runner))
    assert c.post("/api/analyze", json={"ticker": "TCS.NS", "horizon": "forever"}).status_code == 422
    assert c.post("/api/analyze", json={"ticker": "TCS.NS", "filing": "/etc/passwd"}).status_code == 422


def test_unknown_job_404():
    assert TestClient(create_app(fake_runner)).get("/api/jobs/nope").status_code == 404


def test_concurrency_limit():
    c = TestClient(create_app(slow_runner, max_running=1))
    assert c.post("/api/analyze", json={"ticker": "TCS.NS"}).status_code == 202
    assert c.post("/api/analyze", json={"ticker": "INFY.NS"}).status_code == 429


def test_runner_error_is_reported_without_traceback():
    def boom(opts, progress):
        raise RuntimeError("secret path /Users/apple/x")
    c = TestClient(create_app(boom))
    job = c.post("/api/analyze", json={"ticker": "TCS.NS"}).json()["job_id"]
    r = wait(c, job)
    assert r["status"] == "error" and "/Users" not in r["error"] and "Traceback" not in r["error"]


def test_health_and_disclaimer_header():
    c = TestClient(create_app(fake_runner))
    r = c.get("/api/health")
    assert r.json()["ok"] is True and "Not financial" in r.json()["disclaimer"]
