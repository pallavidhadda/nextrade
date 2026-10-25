from datetime import date
from decimal import Decimal

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
    checks = [f for f in fs.facts if f.metric in ("net_income_source_check", "interest_expense_source_check")]
    assert {f.metric for f in checks} == {"net_income_source_check", "interest_expense_source_check"}
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


def test_ebitda_derived_from_filing(filing):
    fs = build_factset("RELIANCE.NS", client=FakeClient(), filing_path=filing, **NS)
    [d] = [f for f in fs.facts if f.metric == "ebitda_derived"]
    assert d.value == Decimal("540670000000") and d.source == "computed" and d.status == "ok"   # PBT + finance costs + depreciation
    assert len(d.related_fact_ids) == 3


def test_yahoo_ebitda_that_equals_ebit_is_flagged_and_demoted(filing):
    fs = build_factset("RELIANCE.NS", client=FakeClient(), filing_path=filing, **NS)
    [chk] = [f for f in fs.facts if f.metric == "ebitda_derived_source_check"]
    assert chk.status == "conflict" and "EBIT" in chk.reason
    yahoo = [f for f in fs.facts if f.source == "yahoo" and f.metric == "ebitda" and f.period_type == "Q"]
    assert yahoo and all(f.status == "unverified" and "EBIT" in f.reason for f in yahoo if f.value is not None)


def test_plausible_yahoo_ebitda_not_demoted(filing):
    stmt = QUARTERLY.copy()
    stmt.loc["EBITDA", stmt.columns[0]] = 540000000000.0
    fs = build_factset("RELIANCE.NS", client=FakeClient(stmt=stmt, info=INFO), filing_path=filing, **NS)
    [chk] = [f for f in fs.facts if f.metric == "ebitda_derived_source_check"]
    assert chk.status == "ok"
    assert all(f.status == "ok" for f in fs.facts if f.source == "yahoo" and f.metric == "ebitda" and f.value is not None)


def test_no_depreciation_in_filing_means_no_derived_ebitda(tmp_path):
    p = tmp_path / "f.html"
    p.write_text(HTML.replace("Depreciation, depletion and amortisation expense", "Something else"), encoding="utf-8")
    fs = build_factset("RELIANCE.NS", client=FakeClient(), filing_path=p, **NS)
    assert not [f for f in fs.facts if f.metric.startswith("ebitda_derived")]


def test_revenue_yoy_and_latest_quarter_net_margin_are_computed():
    fs = build_factset("RELIANCE.NS", client=FakeClient(), **NS)
    [g] = [f for f in fs.facts if f.metric == "revenue_yoy"]
    assert g.status == "ok" and float(g.value) == pytest.approx(3.09 / 2.44 - 1)
    [m] = [f for f in fs.facts if f.metric == "net_margin_q"]
    assert m.status == "ok" and float(m.value) == pytest.approx(209460000000 / 3.09e12) and len(m.related_fact_ids) == 2


def test_net_margin_unavailable_when_revenue_missing():
    stmt = QUARTERLY.drop(index="Total Revenue")
    fs = build_factset("RELIANCE.NS", client=FakeClient(stmt=stmt, info=INFO), **NS)
    [m] = [f for f in fs.facts if f.metric == "net_margin_q"]
    assert m.status == "unavailable" and "revenue" in m.reason
