import json
import re
from pathlib import Path

from indiafacts.cli import main
from indiafacts.digest import BANNED_WORDS
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
from tests.test_htmlreport import NSE_CSV, SYMS, prices_for
from tests.test_nsefiling import HTML as FILING_HTML

ROOT = Path(__file__).resolve().parents[1]


def run(tmp_path, capsys, *extra):
    c = tmp_path / "ind.csv"
    c.write_text(NSE_CSV, encoding="utf-8")
    f = tmp_path / "f.html"
    f.write_text(FILING_HTML, encoding="utf-8")
    code = main(["RELIANCE.NS", "--score", "--universe", str(c), "--filing", str(f), "--no-tej", "--no-remember", *extra],
                client=FakeClient(stmt=QUARTERLY, info={**INFO, "industry": "Refining"}), sleep=lambda s: None,
                price_client=prices_for(SYMS))
    o = capsys.readouterr()
    return code, o.out, o.err


def test_dg1_digest_flag_prints_only_the_digest_and_the_narration_rules(tmp_path, capsys):
    code, out, err = run(tmp_path, capsys, "--digest")
    assert code == 0 and out.startswith("DIGEST for RELIANCE.NS")
    assert re.search(r"^F1 ", out, re.M) and "GAP" in out and "RULES FOR THE NARRATOR" in out
    assert "never advise" in out.lower() and "copy" in out.lower() and "cite" in out.lower()
    assert "QUARTERLY" not in out and "SOURCES" not in out and "EXPLANATION" not in out        # not the long report
    assert len(out) < 9000


def test_dg2_digest_with_html_still_writes_the_report(tmp_path, capsys):
    page = tmp_path / "r.html"
    code, out, err = run(tmp_path, capsys, "--digest", "--html", str(page))
    assert code == 0 and page.exists() and "wrote" in out


def test_dg3_plugin_manifest_and_commands_are_present_and_sane():
    m = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert m["name"] == "indiafacts" and m["version"] and m["description"]
    for name in ("analyze", "changes"):
        text = (ROOT / "commands" / f"{name}.md").read_text(encoding="utf-8")
        head = text.split("---")[1]
        assert "description:" in head and "$ARGUMENTS" in text
        assert "CLAUDE_PLUGIN_ROOT" in text and "indiafacts" in text
    analyze = (ROOT / "commands" / "analyze.md").read_text(encoding="utf-8")
    assert "--digest" in analyze and "not financial" in analyze.lower() and "narrator rules" in analyze.lower()
    blob = " ".join(p.read_text(encoding="utf-8") for p in (ROOT / "commands").glob("*.md")).lower()
    assert not any(re.search(rf"\b{re.escape(w)}\b", blob.replace("never advise buying, selling", "")) for w in ("buy", "sell"))


def test_dg4_no_secrets_in_plugin_files():
    for p in list((ROOT / "commands").glob("*.md")) + [ROOT / ".claude-plugin" / "plugin.json"]:
        t = p.read_text(encoding="utf-8")
        assert "API_KEY=" not in t and "AIza" not in t and "sk-" not in t


def test_dg5_changes_only_prints_just_the_changes_block(tmp_path, capsys):
    run(tmp_path, capsys)                                              # first run, remembered
    from tests.fakes import FakeClient as FC

    c = tmp_path / "ind.csv"
    code = main(["RELIANCE.NS", "--changes-only", "--no-prices", "--no-tej"], client=FC(stmt=QUARTERLY, info=INFO), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0 and ("WHAT CHANGED" in out or "first run" in out or "no changes" in out)
    assert "QUARTERLY" not in out and "DATA QUALITY" not in out and len(out) < 3000
