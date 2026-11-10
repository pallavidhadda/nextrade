import hashlib
from datetime import date

from indiafacts import stamp
from indiafacts.stamp import app_commit, params_hash, report_stamp


def test_params_hash_covers_names_and_contents_sorted(tmp_path):
    (tmp_path / "b.json").write_text("{}")
    (tmp_path / "a.json").write_text('{"x":1}')
    (tmp_path / "ignored.txt").write_text("zzz")
    expect = hashlib.sha256(b"a.json\0" + b'{"x":1}' + b"\0" + b"b.json\0{}\0").hexdigest()[:12]
    assert params_hash(tmp_path) == expect
    (tmp_path / "a.json").write_text('{"x":2}')
    assert params_hash(tmp_path) != expect
    assert len(params_hash()) == 12                                    # the real data folder


def test_stamp_with_fixed_inputs_is_stable_and_complete(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    s = report_stamp("RELIANCE.NS", date(2026, 10, 26), ["TCS.NS", "RELIANCE.NS"], data_dir=tmp_path, commit="abc1234")
    again = report_stamp("RELIANCE.NS", date(2026, 10, 26), ["RELIANCE.NS", "TCS.NS"], data_dir=tmp_path, commit="abc1234")
    assert s == again and s["pool_size"] == 2 and s["pool_members"] == ["RELIANCE.NS", "TCS.NS"]
    assert s["as_of"] == "2026-10-26" and s["commit"] == "abc1234" and s["llm_model"] is None and len(s["report_id"]) == 10
    assert s["report_id"] == hashlib.sha256(f"RELIANCE.NS|2026-10-26|{s['params_hash']}|abc1234".encode()).hexdigest()[:10]
    assert report_stamp("TCS.NS", date(2026, 10, 26), data_dir=tmp_path, commit="abc1234")["report_id"] != s["report_id"]
    assert report_stamp("RELIANCE.NS", date(2026, 10, 26), data_dir=tmp_path, commit="def5678")["report_id"] != s["report_id"]
    assert report_stamp("RELIANCE.NS", date(2026, 10, 26), llm_model="m", data_dir=tmp_path, commit="x")["llm_model"] == "m"


def test_commit_from_env_then_git_then_unknown(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "9f8e7d6c5b4a3")
    assert app_commit() == "9f8e7d6c5b4a"
    monkeypatch.setenv("GIT_COMMIT", "1234567")
    assert app_commit() == "1234567"
    monkeypatch.delenv("GIT_COMMIT")
    monkeypatch.delenv("RENDER_GIT_COMMIT")

    def boom(*a, **k):
        raise FileNotFoundError("no git")

    monkeypatch.setattr(stamp.subprocess, "run", boom)
    assert app_commit() == "unknown"


def test_json_summary_carries_stamp(tmp_path, capsys):
    import json

    from tests.test_explain_cli import run

    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    d = json.loads(out.read_text())
    assert code == 0 and d["stamp"]["ticker"] == "RELIANCE.NS" and d["stamp"]["pool_size"] >= 2
    assert "RELIANCE.NS" in d["stamp"]["pool_members"] and len(d["stamp"]["params_hash"]) == 12
