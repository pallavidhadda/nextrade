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
        out = text_of(call(c, "get_analysis", {"job_id": job}))
        assert "running" in out.lower() and "do not" in out.lower()


def test_rest_routes_still_work_next_to_mcp():
    with TestClient(create_app(runner)) as c:
        assert c.get("/api/health").json()["ok"] is True
