import json
import time

from fastapi.testclient import TestClient

from indiafacts.api import create_app

HEAD = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


def runner(opts, progress):
    text = "F1 SCORE overall 45.0/100 rank 24 of 30\nF2 pe ratio 20.5"
    return {"summary": {"ticker": opts["ticker"], "name": None, "gaps": [{"metric": "roe", "period": "x", "reason": "not provided"}],
                        "llm": {"system": "s", "user": "DIGEST:\n" + text, "max_tokens": 700, "ids": ["F1", "F2"], "digest": text}},
            "html": "<html></html>"}


def rpc(c, method, params=None, id=1):
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}, headers=HEAD)
    assert r.status_code == 200, r.text
    body = r.text
    if body.startswith("event:"):
        body = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")][0]
    return json.loads(body)


def call(c, name, args):
    return rpc(c, "tools/call", {"name": name, "arguments": args})["result"]


def text_of(res):
    return "".join(x["text"] for x in res["content"] if x["type"] == "text")


def test_tools_are_listed_and_described_for_claude():
    with TestClient(create_app(runner)) as c:
        tools = {t["name"]: t for t in rpc(c, "tools/list")["result"]["tools"]}
        assert set(tools) == {"start_analysis", "get_analysis"}
        assert "education" in tools["start_analysis"]["description"].lower()
        assert tools["start_analysis"]["inputSchema"]["required"] == ["ticker"]


def test_start_then_get_returns_digest_rules_and_disclaimer():
    with TestClient(create_app(runner)) as c:
        started = text_of(call(c, "start_analysis", {"ticker": "tcs.ns"}))
        job = json.loads(started)["job_id"]
        out = ""
        for _ in range(100):
            out = text_of(call(c, "get_analysis", {"job_id": job}))
            if "DIGEST" in out:
                break
            time.sleep(0.02)
        assert "F1 SCORE overall 45.0/100" in out and "RULES FOR THE NARRATOR" in out
        assert "Not financial" in out and "roe" in out        # gaps are surfaced


def test_bad_ticker_and_unknown_job_are_clear_errors():
    with TestClient(create_app(runner)) as c:
        bad = call(c, "start_analysis", {"ticker": "../etc/passwd"})
        assert bad.get("isError") or "ticker" in text_of(bad).lower()
        unk = text_of(call(c, "get_analysis", {"job_id": "nope"}))
        assert "unknown" in unk.lower()


def test_pending_job_says_to_wait_not_to_guess():
    def slow(opts, progress):
        time.sleep(0.4)
        return runner(opts, progress)
    with TestClient(create_app(slow)) as c:
        job = json.loads(text_of(call(c, "start_analysis", {"ticker": "INFY.NS"})))["job_id"]
        out = text_of(call(c, "get_analysis", {"job_id": job, "wait_seconds": 0}))
        assert "running" in out.lower() and "do not" in out.lower()


def test_rest_routes_still_work_next_to_mcp():
    with TestClient(create_app(runner)) as c:
        assert c.get("/api/health").json()["ok"] is True


def test_optional_token_locks_the_connector_but_not_health(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_MCP_TOKEN", "s3cret-token")
    with TestClient(create_app(runner)) as c:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        assert c.post("/mcp", json=body, headers=HEAD).status_code == 401
        assert c.post("/mcp", json=body, headers={**HEAD, "authorization": "Bearer wrong"}).status_code == 401
        ok = c.post("/mcp", json=body, headers={**HEAD, "authorization": "Bearer s3cret-token"})
        assert ok.status_code == 200 and "start_analysis" in ok.text
        assert c.get("/api/health").status_code == 200
        r = c.post("/mcp", json=body, headers=HEAD)
        assert "s3cret-token" not in r.text and "www-authenticate" in {k.lower() for k in r.headers}


def test_without_a_token_the_connector_stays_open(monkeypatch):
    monkeypatch.delenv("INDIAFACTS_MCP_TOKEN", raising=False)
    with TestClient(create_app(runner)) as c:
        assert c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=HEAD).status_code == 200


def test_get_analysis_waits_for_the_job_instead_of_returning_instantly():
    def slow(opts, progress):
        time.sleep(0.8)
        return runner(opts, progress)
    with TestClient(create_app(slow)) as c:
        job = json.loads(text_of(call(c, "start_analysis", {"ticker": "TCS.NS"})))["job_id"]
        t0 = time.time()
        out = text_of(call(c, "get_analysis", {"job_id": job, "wait_seconds": 10}))
        assert "DIGEST" in out and 0.5 < time.time() - t0 < 5


def test_get_analysis_returns_running_after_the_wait_and_caps_it():
    def slower(opts, progress):
        time.sleep(3)
        return runner(opts, progress)
    with TestClient(create_app(slower)) as c:
        job = json.loads(text_of(call(c, "start_analysis", {"ticker": "INFY.NS"})))["job_id"]
        t0 = time.time()
        out = text_of(call(c, "get_analysis", {"job_id": job, "wait_seconds": 1}))
        assert "running" in out.lower() and 0.8 < time.time() - t0 < 2.5
        assert "again" in out.lower()
        big = call(c, "get_analysis", {"job_id": job, "wait_seconds": 9999})
        assert big.get("isError") or "wait_seconds" in text_of(big) or "running" in text_of(big).lower() or "DIGEST" in text_of(big)


def _done_job(c, name="TCS.NS"):
    job = json.loads(text_of(call(c, "start_analysis", {"ticker": name})))["job_id"]
    for _ in range(100):
        out = text_of(call(c, "get_analysis", {"job_id": job, "wait_seconds": 0}))
        if "DIGEST" in out:
            return job, out
        time.sleep(0.02)
    raise AssertionError(out)


def test_default_result_asks_for_a_structured_full_report():
    with TestClient(create_app(runner)) as c:
        _, out = _done_job(c)
        for section in ("1. Snapshot", "2. How it scores", "4. What the price implies", "8. Data gaps", "9. What would change the picture", "10. Bull case versus bear case", "11. Educational rating", "12. Recent headlines"):
            assert section in out
        assert "cite" in out.lower() and "Not financial" in out


def test_brief_detail_keeps_the_short_rules():
    with TestClient(create_app(runner)) as c:
        job, _ = _done_job(c, "INFY.NS")
        out = text_of(call(c, "get_analysis", {"job_id": job, "wait_seconds": 0, "detail": "brief"}))
        assert "at most 5 short bullet points" in out and "1. Snapshot" not in out


def test_report_link_is_added_when_a_public_url_is_configured(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_PUBLIC_URL", "https://example.test/")
    with TestClient(create_app(runner)) as c:
        job, out = _done_job(c)
        assert f"https://example.test/api/jobs/{job}/report" in out and "interactive report" in out.lower()
