import json
import copy
from pathlib import Path

from indiafacts import drift, marketlens, snapshots
from indiafacts.stamp import report_stamp
from datetime import date

FIX = Path(__file__).parent / "fixtures"


def fixture_ml(n=12):
    """12 real-shaped rows (the Petroleum Products fixture), as a marketlens.json body."""
    d = json.loads((FIX / "marketlens_petroleum_products.json").read_text(encoding="utf-8"))
    rows = {r["id"]: {**r, "_sectorId": "petroleum"} for r in d["data"]}
    return {"fetched_at": "2026-11-10T12:00:00+00:00", "problems": [], "rows": rows}


def sev(report, check, field=None, severity=None):
    return [c for c in report["checks"] if c["check"] == check and (field is None or c["field"] == field)
            and (severity is None or c["severity"] == severity)]


def test_fixture_passes_schema_without_breaking():
    rep = drift.build_report(fixture_ml(), None)
    assert rep["status"] != "breaking", rep["checks"]
    assert not sev(rep, "required_field") and not sev(rep, "range", severity="breaking")


def test_nse_api_fixtures_pass_and_missing_field_breaks():
    resp = {}
    for f in FIX.glob("nse_*_RELIANCE.json"):
        resp[f.stem.removeprefix("nse_").rsplit("_", 1)[0]] = json.loads(f.read_text(encoding="utf-8"))
    assert len(resp) == 4
    assert drift.build_report(nse_api=resp)["status"] == "ok"
    broken = copy.deepcopy(resp)
    for r in broken["corporates-financial-results"]:
        r.pop("xbrl")
    rep = drift.build_report(nse_api=broken)
    assert rep["status"] == "breaking" and sev(rep, "required_field", "xbrl")


def test_beta_equal_one_is_a_placeholder_and_disabled():
    ml = fixture_ml()
    assert all(r["beta"] == 1 for r in ml["rows"].values())
    schema = drift.load_schema()
    schema["marketlens"]["expected_placeholders"] = []
    rep = drift.build_report(ml, None, schema=schema)
    assert sev(rep, "placeholder", "beta", "warning") and "marketlens.beta" in rep["disabled_fields"]
    assert rep["status"] == "warning"
    # with the shipped schema beta is a known placeholder: still disabled, info only
    rep2 = drift.build_report(ml, None)
    assert "marketlens.beta" in rep2["disabled_fields"] and sev(rep2, "placeholder", "beta", "info")


def test_placeholder_field_is_skipped_by_score_metrics(tmp_path, monkeypatch):
    row = next(iter(fixture_ml()["rows"].values()))
    assert "pb" in marketlens.score_metrics_for(row)
    report = tmp_path / "drift_report.json"
    report.write_text(json.dumps({"status": "warning", "checks": [], "disabled_fields": ["marketlens.pbRatio", "pool_metrics.roe"]}))
    monkeypatch.setenv("INDIAFACTS_DRIFT_REPORT", str(report))
    got = marketlens.score_metrics_for(row)
    assert "pb" not in got and "pe_ttm" in got
    assert not any(f.metric == "pb" for f in marketlens.facts_for("RELIANCE", row))
    monkeypatch.delenv("INDIAFACTS_DRIFT_REPORT")
    assert "pb" in marketlens.score_metrics_for(row)


def test_doubled_unit_is_breaking():
    today, yday = fixture_ml(), fixture_ml()
    for r in today["rows"].values():
        r["peRatio"] = r["peRatio"] * 100
    rep = drift.build_report(today, yday)
    assert rep["status"] == "breaking"
    assert sev(rep, "unit_change", "peRatio", "breaking")


def test_missing_required_field_is_breaking():
    ml = fixture_ml()
    for r in ml["rows"].values():
        del r["pbRatio"]
    rep = drift.build_report(ml, None)
    assert rep["status"] == "breaking" and sev(rep, "required_field", "pbRatio", "breaking")


def test_row_count_drop_is_breaking_per_sector():
    yday = fixture_ml()
    extra = {f"X{i}": {**next(iter(yday["rows"].values())), "id": f"X{i}"} for i in range(12)}
    yday["rows"].update(extra)                                           # 24 rows yesterday, 12 today
    rep = drift.build_report(fixture_ml(), yday)
    assert sev(rep, "row_count", "all sectors", "breaking") and sev(rep, "row_count", "sector Petroleum Products", "breaking")
    assert drift.breaking_sources(rep) == ["marketlens"]


def test_anchor_mismatch_is_breaking():
    ml = fixture_ml()
    cap = ml["rows"]["RELIANCE"]["marketCap"]
    ok = drift.build_report(ml, None, anchors={"RELIANCE": cap * 1.03})
    assert not sev(ok, "anchor", severity="breaking")
    bad = drift.build_report(ml, None, anchors={"RELIANCE": cap * 1.5, "TCS": 1e13})
    anchors = sev(bad, "anchor", severity="breaking")
    assert {c["field"] for c in anchors} == {"RELIANCE", "TCS"} and bad["status"] == "breaking"


def test_pool_metrics_checks():
    def store(pe):
        return {"meta": {}, "metrics": {f"T{i}.NS": {"pe_ttm": {"value": pe + i}, "pb": {"value": 2.0 + i / 10}, "return_1y": {"value": 0.1 + i / 100},
                                                    "volatility_1y": {"value": 0.3}} for i in range(10)}}
    assert drift.build_report(pool=store(20), pool_prev=store(21))["status"] == "warning"       # volatility_1y is one repeated value
    rep = drift.build_report(pool=store(20), pool_prev=store(21))
    assert "pool_metrics.volatility_1y" in rep["disabled_fields"]
    stripped = drift.strip_disabled_pool(store(20), rep["disabled_fields"])
    assert all("volatility_1y" not in m for m in stripped["metrics"].values())
    assert drift.build_report(pool=store(2000), pool_prev=store(21))["status"] == "breaking"      # out of range and a unit jump


def isolate_env(monkeypatch):
    """drift_gate sets process env vars; register them with monkeypatch so they are restored after the test."""
    for k in ("INDIAFACTS_DRIFT_REPORT", "INDIAFACTS_MARKETLENS", "INDIAFACTS_POOL_METRICS_URL"):
        monkeypatch.setenv(k, "1")
    monkeypatch.delenv("INDIAFACTS_DRIFT_REPORT")


def gate_setup(tmp_path, bad_today):
    out, prev = tmp_path / "out", tmp_path / "prev"
    out.mkdir(), prev.mkdir()
    (prev / "marketlens.json").write_text(json.dumps(fixture_ml()))
    today = fixture_ml()
    if bad_today:
        for r in today["rows"].values():
            r["marketCap"] = r["marketCap"] * 1000                      # a unit change
    (out / "marketlens.json").write_text(json.dumps(today))
    return out, prev


def test_breaking_keeps_yesterdays_files(tmp_path, monkeypatch):
    isolate_env(monkeypatch)
    out, prev = gate_setup(tmp_path, True)
    yesterday = (prev / "marketlens.json").read_text()
    rep = snapshots.drift_gate(out, prev, log=lambda *a: None)
    assert rep["status"] == "breaking"
    assert (out / "marketlens.json").read_text() == yesterday
    saved = json.loads((out / "drift_report.json").read_text())
    assert saved["status"] == "breaking" and saved["checks"]
    meta = json.loads((out / "index.json").read_text())["_meta"]
    assert meta["drift_status"] == "breaking" and meta["drift_breaking"] == ["marketlens"]


def test_breaking_without_yesterday_publishes_no_file(tmp_path, monkeypatch):
    isolate_env(monkeypatch)
    out, prev = gate_setup(tmp_path, True)
    (prev / "marketlens.json").unlink()
    ml = json.loads((out / "marketlens.json").read_text())
    for r in ml["rows"].values():
        del r["peRatio"]
    (out / "marketlens.json").write_text(json.dumps(ml))
    assert snapshots.drift_gate(out, prev, log=lambda *a: None)["status"] == "breaking"
    assert not (out / "marketlens.json").exists() and (out / "drift_report.json").exists()


def test_ok_publishes_todays_file_and_warning_sets_hook(tmp_path, monkeypatch):
    isolate_env(monkeypatch)
    out, prev = gate_setup(tmp_path, False)
    today = (out / "marketlens.json").read_text()
    rep = snapshots.drift_gate(out, prev, log=lambda *a: None)
    assert rep["status"] != "breaking" and (out / "marketlens.json").read_text() == today
    import os
    assert os.environ["INDIAFACTS_DRIFT_REPORT"].endswith("drift_report.json")
    assert "beta" in marketlens.disabled_fields()


def test_issue_plan_title_body_and_dedupe():
    ml = fixture_ml()
    for r in ml["rows"].values():
        del r["pbRatio"]
    rep = drift.build_report(ml, None)
    plan = drift.issue_plan(rep, "https://example/run/1")
    assert [t for t, _ in plan] == ["Source drift: marketlens"]
    body = plan[0][1]
    assert "pbRatio" in body and "required_field" in body and "https://example/run/1" in body and "kept" in body
    assert drift.issue_plan(drift.build_report(fixture_ml(), None)) == []

    logs, calls = [], []
    drift.run_issues(rep, dry_run=True, log=logs.append, run=lambda *a, **k: calls.append(a))
    assert calls == [] and "Source drift: marketlens" in logs[0]

    class R:
        def __init__(self, out=""): self.stdout, self.returncode = out, 0

    def fake(cmd, **kw):
        calls.append(cmd)
        return R(json.dumps([{"number": 7, "title": "Source drift: marketlens"}]) if cmd[:3] == ["gh", "issue", "list"] else "")

    drift.run_issues(rep, run=fake, log=lambda *a: None)
    assert calls[-1][:4] == ["gh", "issue", "comment", "7"]


def test_stamp_carries_drift_status_and_policy_hash(tmp_path, monkeypatch):
    (tmp_path / "source_policy.json").write_text("{}")
    monkeypatch.delenv("INDIAFACTS_DRIFT_REPORT", raising=False)
    s = report_stamp("TCS.NS", date(2026, 11, 10), data_dir=tmp_path, commit="x")
    assert s["drift_status"] == "unknown" and len(s["source_policy"]) == 12
    rep = tmp_path / "drift_report.json"
    rep.write_text(json.dumps({"status": "warning"}))
    monkeypatch.setenv("INDIAFACTS_DRIFT_REPORT", str(rep))
    assert report_stamp("TCS.NS", date(2026, 11, 10), data_dir=tmp_path, commit="x")["drift_status"] == "warning"
