from datetime import date

import pytest

from indiafacts.pipeline import build_factset
from indiafacts.render import render
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
from tests.test_nsefiling import HTML

NS = dict(sleep=lambda s: None)


@pytest.fixture
def filing(tmp_path):
    p = tmp_path / "f.html"
    p.write_text(HTML, encoding="utf-8")
    return p


def test_filing_identity_replaces_unavailable_identifiers(filing):
    fs = build_factset("RELIANCE.NS", client=FakeClient(), filing_path=filing, **NS)
    assert fs.entity.isin.value == "INE002A01018" and fs.entity.bse_code.value == "500325"
    assert "ISIN INE002A01018" in render(fs)


def test_matching_sources_pass_cross_check(filing):
    fs = build_factset("RELIANCE.NS", client=FakeClient(), filing_path=filing, **NS)
    checks = [f for f in fs.facts if f.metric.endswith("_source_check")]
    assert {f.metric for f in checks} >= {"net_income_source_check", "interest_expense_source_check"}
    assert all(f.status == "ok" for f in checks)


def test_disagreeing_sources_flagged(filing):
    stmt = QUARTERLY.copy()
    stmt.loc["Net Income Common Stockholders", stmt.columns[0]] = 150000000000.0
    fs = build_factset("RELIANCE.NS", client=FakeClient(stmt=stmt, info=INFO), filing_path=filing, **NS)
    [chk] = [f for f in fs.facts if f.metric == "net_income_source_check"]
    assert chk.status == "conflict"


def test_filing_date_makes_yahoo_period_public_early(filing):
    early = date(2026, 7, 20)
    without = build_factset("RELIANCE.NS", as_of=early, client=FakeClient(), **NS)
    assert any(f.period_end == date(2026, 6, 30) for f in without.not_yet_public)   # deadline estimate: 14 Aug
    with_f = build_factset("RELIANCE.NS", as_of=early, client=FakeClient(), filing_path=filing, **NS)
    yahoo_jun = [f for f in with_f.facts if f.source == "yahoo" and f.period_end == date(2026, 6, 30)]
    assert yahoo_jun and all(f.availability_kind == "filed" for f in yahoo_jun)
    assert not any(f.period_end == date(2026, 6, 30) for f in with_f.not_yet_public)


def test_table_prefers_filing_and_shows_consolidated(filing):
    out = render(build_factset("RELIANCE.NS", client=FakeClient(), filing_path=filing, **NS))
    jun = [l for l in out.splitlines() if l.startswith("r") and "net_income | Q1 FY27" in l]
    assert jun and "nse_filing" in jun[0]
    assert "consolidated" in out.splitlines()[0]


def test_filing_for_other_company_rejected(filing):
    with pytest.raises(ValueError):
        build_factset("TCS.NS", client=FakeClient(), filing_path=filing, **NS)
