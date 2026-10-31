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


def _runner_with_digest(opts, progress):
    text = "F1 net profit 100 crore\nF2 pe ratio 20.5"
    return {"summary": {"ticker": opts["ticker"], "llm": {"system": "s", "user": "DIGEST:\n" + text, "max_tokens": 700, "ids": ["F1", "F2"], "digest": text}},
            "html": "<html></html>"}


def _job(c):
    job = c.post("/api/analyze", json={"ticker": "TCS.NS"}).json()["job_id"]
    wait(c, job)
    return job


GOOD = '{"summary":"Profit is 100 crore and P/E 20.5.","uncertainty":"Some data is missing.","claims":[{"type":"fact","text":"Net profit is 100 crore.","ids":["F1"]},{"type":"fact","text":"The P/E is 20.5.","ids":["F2"]}]}'


def test_validate_accepts_good_output_without_any_key():
    c = TestClient(create_app(_runner_with_digest))
    job = _job(c)
    r = c.post(f"/api/jobs/{job}/validate", json={"raw": GOOD, "model": "my-model"})
    assert r.status_code == 200 and len(r.json()["explanation"]["claims"]) == 2
    assert r.json()["explanation"]["source"] == "your model"


def test_validate_rejects_unknown_ids_and_advice():
    c = TestClient(create_app(_runner_with_digest))
    job = _job(c)
    bad = GOOD.replace('"ids":["F1"]', '"ids":["F99"]').replace("The P/E is 20.5.", "You should buy at 20.5.")
    r = c.post(f"/api/jobs/{job}/validate", json={"raw": bad})
    assert r.json()["explanation"] is None and r.json()["reasons"]


def test_validate_limits_size_and_unknown_job():
    c = TestClient(create_app(_runner_with_digest))
    job = _job(c)
    assert c.post(f"/api/jobs/{job}/validate", json={"raw": "x" * 30000}).status_code == 422
    assert c.post("/api/jobs/nope/validate", json={"raw": GOOD}).status_code == 404


def test_server_never_logs_or_returns_request_secrets(caplog):
    c = TestClient(create_app(_runner_with_digest))
    job = _job(c)
    r = c.post(f"/api/jobs/{job}/validate", json={"raw": GOOD}, headers={"x-api-key": "SECRET123", "authorization": "Bearer SECRET123"})
    assert "SECRET123" not in r.text and "SECRET123" not in caplog.text


def test_per_client_rate_limit():
    c = TestClient(create_app(fake_runner, max_running=10, per_minute=3))
    codes = [c.post("/api/analyze", json={"ticker": f"T{i}.NS"}).status_code for i in range(5)]
    assert codes[:3] == [202, 202, 202] and codes[3:] == [429, 429]


def test_forwarded_for_ignored_unless_trusted(monkeypatch):
    c = TestClient(create_app(fake_runner, max_running=10, per_minute=1))
    assert c.post("/api/analyze", json={"ticker": "A.NS"}, headers={"x-forwarded-for": "1.1.1.1"}).status_code == 202
    assert c.post("/api/analyze", json={"ticker": "B.NS"}, headers={"x-forwarded-for": "2.2.2.2"}).status_code == 429


def test_security_headers_on_every_response():
    r = TestClient(create_app(fake_runner)).get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
