import json

from tests.test_explain_cli import run


def test_json_flag_writes_summary(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    assert code == 0
    d = json.loads(out.read_text())
    assert d["ticker"] == "RELIANCE.NS" and d["name"]
    assert "Not financial" in d["disclaimer"]
    assert d["score"]["rank"] and d["score"]["n"] >= 2 and 0 <= d["score"]["overall"] <= 100
    assert ".txt" not in (d["score"]["pool"] or "") and ".csv" not in (d["score"]["pool"] or "")
    assert len(d["checklist"]) == 9 and {"label", "result", "display"} <= set(d["checklist"][0])
    assert d["gaps"] and all("metric" in g and "reason" in g for g in d["gaps"])
    assert d["explanation"]["summary"] and d["explanation"]["claims"]
    assert isinstance(d["notices"], list) and "factors" in d["score"]


def test_json_without_score_has_null_score(tmp_path, capsys):
    out = tmp_path / "s.json"
    from indiafacts.cli import main
    from tests.fakes import FakeClient
    from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
    from tests.test_htmlreport import SYMS, prices_for
    code = main(["RELIANCE.NS", "--no-tej", "--no-remember", "--json", str(out)], client=FakeClient(stmt=QUARTERLY, info=INFO),
                sleep=lambda s: None, price_client=prices_for(SYMS))
    assert code == 0
    d = json.loads(out.read_text())
    assert d["score"] is None and d["checklist"] == []


def test_summary_carries_prompt_for_browser_side_llm(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    d = json.loads(out.read_text())
    assert d["llm"]["user"].startswith("DIGEST:") and "JSON" in d["llm"]["system"]
    assert d["llm"]["max_tokens"] == 700 and d["llm"]["ids"] and d["llm"]["ids"][0].startswith("F")
    assert "KEY" not in json.dumps(d).upper().replace("KEY_FACTS", "")


def test_pool_size_limits_the_comparison_pool(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--pool-size", "2", "--json", str(out))
    d = json.loads(out.read_text())
    assert code == 0 and d["score"]["n"] <= 3
