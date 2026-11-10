import json
import time
from datetime import date

from fastapi.testclient import TestClient

from indiafacts.api import BUSY_MESSAGE, create_app
from indiafacts.snapshots import SnapshotClient, failure_rate, is_fresh, main, norm, probe, run_snapshots, safe_name

TODAY = date(2026, 11, 10)


def good_runner(opts, progress):
    return {"summary": {"ticker": opts["ticker"], "retrieved_at": "2026-11-10T10:00:00", "key_facts": [{"metric": "revenue"}], "stamp": {"as_of": "2026-11-10"}},
            "html": "<html>live</html>"}


def make_fetch(entry, ticker="TCS.NS", version=None):
    from indiafacts.summary import REPORT_VERSION

    summary = {"ticker": ticker, "snap": True, "report_version": REPORT_VERSION if version is None else version}
    if version == "absent":
        summary.pop("report_version")
    files = {"index.json": {ticker: entry}, f"{safe_name(ticker)}.json": summary}

    def fetch(url):
        name = url.rsplit("/", 1)[1]
        if name.endswith(".html"):
            return b"<html>snapshot</html>"
        return json.dumps(files[name]).encode()
    return fetch


def entry(as_of, ok=True):
    return {"as_of": as_of, "ok": ok, "error": None, "generated_at": "x", "commit": "abc"}


def test_norm_and_safe_name():
    assert norm("tcs") == "TCS.NS" and norm("x.bo") == "X.BO" and safe_name("m&m") == "M_M.NS"


def test_is_fresh():
    assert is_fresh(entry("2026-11-10"), TODAY) and is_fresh(entry("2026-11-06"), TODAY)
    assert not is_fresh(entry("2026-11-05"), TODAY)
    assert is_fresh(entry("2026-11-05"), TODAY, max_age_days=5)
    assert not is_fresh(entry("2026-11-10", ok=False), TODAY) and not is_fresh(None, TODAY)
    assert not is_fresh(entry("2026-11-12"), TODAY)          # a date in the future is not trusted


def test_run_snapshots_records_failure_and_continues(tmp_path):
    def runner(opts, progress):
        if opts["ticker"] == "BAD.NS":
            raise ValueError("could not fetch any data")
        return good_runner(opts, progress)
    idx = run_snapshots(["TCS.NS", "BAD.NS", "ITC.NS"], tmp_path, runner, delay=0, sleep=lambda s: None, log=lambda m: None)
    assert idx["TCS.NS"]["ok"] and idx["ITC.NS"]["ok"]
    assert idx["BAD.NS"]["ok"] is False and "could not fetch" in idx["BAD.NS"]["error"]
    assert (tmp_path / "TCS.NS.json").exists() and (tmp_path / "TCS.NS.html").exists() and not (tmp_path / "BAD.NS.json").exists()
    assert json.loads((tmp_path / "index.json").read_text())["BAD.NS"]["ok"] is False
    assert abs(failure_rate(idx, ["TCS.NS", "BAD.NS", "ITC.NS"]) - 1 / 3) < 1e-9


def test_failure_keeps_previous_good_snapshot(tmp_path):
    run_snapshots(["TCS.NS"], tmp_path, good_runner, 0, lambda s: None, lambda m: None)

    def boom(o, p):
        raise ValueError("blocked")
    idx = run_snapshots(["TCS.NS"], tmp_path, boom, 0, lambda s: None, lambda m: None)
    assert idx["TCS.NS"]["ok"] and idx["TCS.NS"]["last_error"] == "blocked"
    assert failure_rate(idx, ["TCS.NS"]) == 1.0


def test_empty_key_facts_counts_as_failure(tmp_path):
    idx = run_snapshots(["TCS.NS"], tmp_path, lambda o, p: {"summary": {"retrieved_at": "2026-11-10"}, "html": ""}, 0, lambda s: None, lambda m: None)
    assert idx["TCS.NS"]["ok"] is False


def test_main_exit_code_threshold(tmp_path):
    def runner(opts, progress):
        if opts["ticker"] != "TCS.NS":
            raise ValueError("x")
        return good_runner(opts, progress)
    args = ["--out", str(tmp_path), "--tickers", "TCS.NS,A.NS", "--delay", "0"]
    assert main(args, runner, lambda s: None) == 1                       # 50% failed, limit 30
    assert main(args + ["--max-fail-pct", "60"], runner, lambda s: None) == 0


def test_probe_verdict():
    logs = []
    assert probe(good_runner, log=logs.append) and "WORKS" in logs[-1]
    logs.clear()

    def boom(o, p):
        raise ValueError("no data")
    assert not probe(boom, log=logs.append) and "does NOT work" in logs[-1]


def test_client_ttl_cache():
    calls = []
    f = make_fetch(entry("2026-11-10"))

    def counting(url):
        calls.append(url)
        return f(url)
    now = [1000.0]
    c = SnapshotClient("http://x/b/", counting, ttl=100, clock=lambda: now[0])
    assert c.lookup("tcs", TODAY)["as_of"] == "2026-11-10"
    n = len(calls)
    c.lookup("TCS.NS", TODAY)
    assert len(calls) == n
    now[0] += 101
    c.lookup("TCS.NS", TODAY)
    assert len(calls) > n


def test_snapshot_from_older_code_is_not_served():
    """A snapshot built before the current report version (or with no version) falls through to a fresh analysis."""
    from indiafacts.summary import REPORT_VERSION

    today = date.today().isoformat()
    assert SnapshotClient("http://x", make_fetch(entry(today))).lookup("TCS.NS") is not None
    assert SnapshotClient("http://x", make_fetch(entry(today), version=REPORT_VERSION - 1)).lookup("TCS.NS") is None
    assert SnapshotClient("http://x", make_fetch(entry(today), version="absent")).lookup("TCS.NS") is None


def test_client_never_raises():
    def boom(url):
        raise OSError("down")
    assert SnapshotClient("http://x", boom).lookup("TCS.NS") is None


def live_runner(opts, progress):
    return {"summary": {"ticker": opts["ticker"]}, "html": "<html>live</html>"}


def wait(c, job_id):
    for _ in range(100):
        r = c.get(f"/api/jobs/{job_id}").json()
        if r["status"] in ("done", "error"):
            return r
        time.sleep(0.02)
    raise AssertionError(r)


def client_for(as_of, runner=live_runner):
    return TestClient(create_app(runner, snapshots=SnapshotClient("http://x", make_fetch(entry(as_of)), ttl=100)))


def test_api_serves_fresh_snapshot():
    today = date.today().isoformat()
    c = client_for(today)
    r = c.post("/api/analyze", json={"ticker": "TCS.NS"})
    assert r.status_code == 202 and r.json()["served_from"] == "snapshot"
    j = wait(c, r.json()["job_id"])
    assert j["status"] == "done" and j["summary"]["served_from"] == "snapshot" and j["summary"]["snapshot_as_of"] == today
    assert j["summary"]["snap"] is True and j["served_from"] == "snapshot"
    assert "snapshot" in c.get(f"/api/jobs/{r.json()['job_id']}/report").text


def test_api_refresh_bypasses_snapshot():
    c = client_for(date.today().isoformat())
    for r in (c.post("/api/analyze", json={"ticker": "TCS.NS", "refresh": True}), c.post("/api/analyze?refresh=true", json={"ticker": "TCS.NS"})):
        assert r.json()["served_from"] == "live"
        j = wait(c, r.json()["job_id"])
        assert j["summary"]["served_from"] == "live" and "snap" not in j["summary"]


def test_api_custom_profile_runs_live():
    """Snapshots use the default profile; a user who set horizon or risk must not get the default-profile result."""
    c = client_for(date.today().isoformat())
    for body in ({"ticker": "TCS.NS", "horizon": "1-3y"}, {"ticker": "TCS.NS", "risk_tolerance": "low"}):
        r = c.post("/api/analyze", json=body)
        assert r.json()["served_from"] == "live"
        assert wait(c, r.json()["job_id"])["summary"]["served_from"] == "live"


def test_api_stale_snapshot_falls_through_to_live():
    c = client_for("2020-01-01")
    r = c.post("/api/analyze", json={"ticker": "TCS.NS"})
    assert r.json()["served_from"] == "live"
    assert wait(c, r.json()["job_id"])["summary"]["served_from"] == "live"


def test_api_without_snapshot_config_is_live(monkeypatch):
    monkeypatch.delenv("INDIAFACTS_SNAPSHOT_BASE", raising=False)
    c = TestClient(create_app(live_runner))
    assert c.post("/api/analyze", json={"ticker": "TCS.NS"}).json()["served_from"] == "live"


def test_busy_message():
    def slow(opts, progress):
        time.sleep(0.5)
        return live_runner(opts, progress)
    c = TestClient(create_app(slow, max_running=1, snapshots=None))
    assert c.post("/api/analyze", json={"ticker": "TCS.NS"}).status_code == 202
    r = c.post("/api/analyze", json={"ticker": "ITC.NS"})
    assert r.status_code == 429 and r.json()["detail"] == BUSY_MESSAGE


def test_failed_entry_carries_runner_error_detail_without_home_paths(tmp_path):
    from indiafacts.runner import error_detail

    def runner(opts, progress):
        e = ValueError("analysis failed")
        e.detail = error_detail(['File "/Users/bob/x/y.py", line 3', "TypeError: bad format"], 1)
        raise e
    idx = run_snapshots(["TMPV.NS"], tmp_path, runner, delay=0, sleep=lambda s: None, log=lambda m: None)
    err = idx["TMPV.NS"]["error"]
    assert "TypeError: bad format" in err and "/Users/bob" not in err and len(err) <= 300
    assert error_detail([], 2) == "no output (exit 2)"


def test_tej500_universe_is_a_union_after_nifty_and_falls_back_on_failure():
    from indiafacts.snapshots import load_tickers
    base = load_tickers()
    wide = load_tickers(universe="tej500", tej_loader=lambda: ["RELIANCE.NS", "KEC.NS", "ZOMATO.NS"])
    assert wide[:len(base)] == base and wide[len(base):] == ["KEC.NS", "ZOMATO.NS"] and len(set(wide)) == len(wide)
    msgs = []
    def boom():
        raise OSError("offline")
    assert load_tickers(universe="tej500", tej_loader=boom, log=msgs.append) == base and "unavailable" in msgs[0]
