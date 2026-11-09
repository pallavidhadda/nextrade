import json

from tests.test_explain_cli import run


def test_summary_carries_compact_facts_within_size_cap(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    assert code == 0
    d = json.loads(out.read_text())
    assert d["facts_total"] >= len(d["facts"]) > 10 and len(d["facts"]) <= 800
    f = d["facts"][0]
    assert set(f) == {"fact_id", "metric", "value", "unit", "period_end", "period_type", "basis", "source", "status", "reason", "evidence"}
    facts_bytes = len(json.dumps(d["facts"]))
    print("SIZE", len(d["facts"]), facts_bytes, len(out.read_text()))
    assert facts_bytes < 400_000
