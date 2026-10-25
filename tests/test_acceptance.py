import re
from datetime import date

import pytest

from indiafacts.cli import main
from indiafacts.pipeline import build_factset
from indiafacts.render import DISCLAIMER
from tests.fakes import FakeClient


def run(capsys, *argv):
    code = main(list(argv), client=FakeClient(), sleep=lambda s: None)
    return code, capsys.readouterr().out


def test_a1_reliance_replay_offline(capsys):
    code, out = run(capsys, "RELIANCE.NS")
    assert code == 0
    row = next(l for l in out.splitlines() if l.startswith("| net_income"))
    assert "unav (gap)" in row                                   # Sep-25 gap shown
    assert re.search(r"net_income_ttm .*unavailable: missing quarter\(s\): 2025-09-30", out)
    assert re.search(r"price_pe_eps_check .*\[r\d+\]", out) and "conflict" not in out.split("COMPUTED CHECKS")[1].split("\n\n")[0]
    assert "basis: unknown" in out
    assert DISCLAIMER in out
    assert "net_income_ttm_vendor" in out and "unverified" in out


def test_a2_asof_before_june_filing(capsys):
    code, out = run(capsys, "RELIANCE.NS", "--as-of", "2026-08-01")
    assert code == 0
    pending = out.split("Not yet public")[1]
    assert "Q1 FY27" in pending and "deadline estimate" in pending
    row = next(l for l in out.splitlines() if l.startswith("| net_income"))
    assert "Q4 FY26" in out and "₹16,971 cr" in row


def test_invalid_ticker_exit_code(capsys):
    code = main(["../etc"], client=FakeClient())
    assert code == 2
    assert "invalid ticker" in capsys.readouterr().err


def test_build_factset_skips_price_check_when_inputs_missing():
    fs = build_factset("RELIANCE.NS", as_of=date(2026, 8, 1), client=FakeClient(), sleep=lambda s: None)
    assert not [f for f in fs.facts if f.metric == "price_pe_eps_check"]


@pytest.mark.live
def test_live_reliance(capsys):
    code = main(["RELIANCE.NS"])
    out = capsys.readouterr().out
    assert code == 0 and DISCLAIMER in out


def test_cli_filing_option(capsys, tmp_path):
    from tests.test_nsefiling import HTML

    p = tmp_path / "f.html"
    p.write_text(HTML, encoding="utf-8")
    code = main(["RELIANCE.NS", "--filing", str(p)], client=FakeClient(), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0 and "ISIN INE002A01018" in out and "net_income_source_check" in out


def test_cli_bad_filing_exit_code(capsys, tmp_path):
    p = tmp_path / "bad.html"
    p.write_text("<html><body>nope</body></html>")
    assert main(["RELIANCE.NS", "--filing", str(p)], client=FakeClient(), sleep=lambda s: None) == 2


def _pool_file(tmp_path, n=6):
    p = tmp_path / "pool.txt"
    p.write_text("\n".join(f"T{i}.NS" for i in range(n)) + "\n")
    return p


def test_cli_score_with_pool_prints_scorecard_and_checklist(capsys, tmp_path):
    code = main(["T0.NS", "--score", "--universe", str(_pool_file(tmp_path)), "--no-prices"],
                client=FakeClient(), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0 and "SCORECARD" in out and "of 6" in out and "CHECKLIST" in out
    assert "percentile" in out and DISCLAIMER in out
    assert not re.search(r"\b(buy|sell)\b", out.lower())


def test_cli_score_lists_failed_pool_members(capsys, tmp_path):
    class Flaky(FakeClient):
        pass

    p = _pool_file(tmp_path)
    p.write_text(p.read_text() + "BAD..NS\n")           # invalid ticker syntax is a hard error
    code = main(["T0.NS", "--score", "--universe", str(p), "--no-prices"], client=FakeClient(), sleep=lambda s: None)
    assert code == 2 and "invalid ticker" in capsys.readouterr().err


def test_cli_score_too_small_pool_says_so(capsys, tmp_path):
    code = main(["T0.NS", "--score", "--universe", str(_pool_file(tmp_path, 3)), "--no-prices"],
                client=FakeClient(), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0 and "universe too small" in out and "abstain" in out.lower()
