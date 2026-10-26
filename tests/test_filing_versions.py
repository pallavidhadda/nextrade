import re
from datetime import date
from decimal import Decimal

import pytest

from indiafacts.cli import main
from indiafacts.pipeline import build_factset
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
from tests.test_nsefiling import HTML

NS = dict(sleep=lambda s: None)
ORIGINAL = HTML
REVISED = HTML.replace("20,94,600.00", "19,00,000.00").replace("17-07-2026", "05-09-2026")        # profit restated, refiled in Sept
PRIOR_YEAR = (HTML.replace("30-06-2026", "30-06-2025").replace("01-04-2026", "01-04-2025")
              .replace("17-07-2026", "18-07-2025").replace("20,94,600.00", "26,99,400.00").replace("3,11,85,000.00", "2,44,00,000.00"))


@pytest.fixture
def files(tmp_path):
    out = {}
    for name, body in (("orig", ORIGINAL), ("rev", REVISED), ("prior", PRIOR_YEAR)):
        p = tmp_path / f"{name}.html"
        p.write_text(body, encoding="utf-8")
        out[name] = p
    return out


def build(paths, **kw):
    return build_factset("RELIANCE.NS", client=FakeClient(stmt=QUARTERLY, info=INFO), filing_path=paths, **NS, **kw)


def of(fs, metric, period=date(2026, 6, 30), source="nse_filing"):
    return [f for f in fs.facts if f.metric == metric and f.period_end == period and f.source == source]


def test_rs1_revised_filing_wins_old_version_is_kept_and_cited(files):
    fs = build([files["orig"], files["rev"]])
    [new] = of(fs, "net_income")
    assert new.value == Decimal("190000000000") and new.restated == "yes" and new.status == "ok"
    [old] = of(fs, "net_income", source="nse_filing_superseded")
    assert old.value == Decimal("209460000000") and old.status == "stale" and "2026-09-05" in old.reason
    note = next(n for n in fs.notices if n.startswith("restatement:"))
    assert "net_income" in note and "2026-07-17" in note and "2026-09-05" in note and "209460000000" in note and "190000000000" in note


def test_rs2_unchanged_metrics_are_not_marked_restated_and_identical_filings_are_quiet(files):
    fs = build([files["orig"], files["rev"]])
    assert of(fs, "eps_diluted")[0].restated == "unknown" and of(fs, "interest_expense")[0].restated == "unknown"
    same = build([files["orig"], files["orig"]])
    assert not [n for n in same.notices if n.startswith("restatement:")] and len(of(same, "net_income")) == 1


def test_rs3_two_periods_make_growth_verifiable_on_one_basis(files):
    fs = build([files["orig"], files["prior"]])
    g = [f for f in fs.facts if f.metric == "net_income_yoy"][0]
    assert g.status == "ok" and "sources differ" not in g.reason and abs(float(g.value) - (20946 / 26994 - 1)) < 1e-6
    r = [f for f in fs.facts if f.metric == "revenue_yoy"][0]
    assert r.status == "ok" and abs(float(r.value) - (31185000 / 24400000 - 1)) < 1e-6


def test_rs4_a_restated_figure_makes_growth_unverified(files):
    fs = build([files["rev"], files["prior"]])
    g = [f for f in fs.facts if f.metric == "net_income_yoy"][0]
    assert g.status == "ok" or "restated" in g.reason          # revised only (no original supplied): nothing to compare, no flag
    both = build([files["orig"], files["rev"], files["prior"]])
    g2 = [f for f in both.facts if f.metric == "net_income_yoy"][0]
    assert g2.status == "unverified" and "restated" in g2.reason


def test_rs5_filings_for_another_company_are_rejected(files, tmp_path):
    other = tmp_path / "other.html"
    other.write_text(HTML.replace("RELIANCE", "TCS"), encoding="utf-8")
    with pytest.raises(ValueError, match="filing is for"):
        build([files["orig"], other])


def test_rs6_cli_accepts_filing_twice_and_prints_the_restatement(files, capsys):
    code = main(["RELIANCE.NS", "--no-prices", "--no-tej", "--no-remember", "--filing", str(files["orig"]), "--filing", str(files["rev"])],
                client=FakeClient(stmt=QUARTERLY, info=INFO), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0 and "restatement: net_income" in out and "190000000000" in out


def test_rs7_filings_dir_loads_every_saved_page_for_the_company_and_skips_the_rest(files, tmp_path, capsys):
    d = tmp_path / "filings"
    d.mkdir()
    for k in ("orig", "rev", "prior"):
        (d / f"{k}.html").write_text(files[k].read_text(encoding="utf-8"), encoding="utf-8")
    (d / "tcs.html").write_text(HTML.replace("RELIANCE", "TCS"), encoding="utf-8")
    (d / "notes.html").write_text("<html><body>not a results page</body></html>", encoding="utf-8")
    (d / "readme.txt").write_text("ignored")
    code = main(["RELIANCE.NS", "--no-prices", "--no-tej", "--no-remember", "--filings-dir", str(d)],
                client=FakeClient(stmt=QUARTERLY, info=INFO), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0 and "restatement: net_income" in out
    assert "skipped filing tcs.html" in out and "skipped filing notes.html" in out and "readme.txt" not in out
    assert "net_income_yoy" in out


def test_rs8_empty_or_missing_filings_dir_is_a_clear_message(tmp_path, capsys):
    code = main(["RELIANCE.NS", "--no-prices", "--no-tej", "--no-remember", "--filings-dir", str(tmp_path / "nope")],
                client=FakeClient(stmt=QUARTERLY, info=INFO), sleep=lambda s: None)
    assert code == 2 and "filings folder not found" in capsys.readouterr().err
