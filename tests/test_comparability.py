from datetime import date
from decimal import Decimal

import pytest

from indiafacts.analysis import comparability_check, growth_yoy
from indiafacts.checklist import checklist
from indiafacts.models import FactSet, Entity
from tests.factories import NOW, fact

CUR_END, BASE_END = date(2026, 6, 30), date(2025, 6, 30)


def pair(cur_over=None, base_over=None, cur_v="150", base_v="100", metric="revenue"):
    common = dict(source="yahoo", evidence="yfinance row 'Total Revenue'", basis="unknown")
    c = fact(CUR_END, metric=metric, value=cur_v, **{**common, **(cur_over or {})})
    b = fact(BASE_END, metric=metric, value=base_v, **{**common, **(base_over or {})})
    return c, b


def test_cg1_same_source_unknown_basis_passes_with_notes():
    c, b = pair()
    issues, notes = comparability_check(c, b)
    assert issues == [] and any("basis not stated" in n for n in notes) and any("restatement status unknown" in n for n in notes)
    g = growth_yoy([c, b], "revenue", CUR_END)
    assert g.status == "ok" and g.value == Decimal("0.5") and "restatement status unknown" in g.reason


def test_cg2_filing_against_yahoo_is_unverified_with_reasons():
    c, b = pair(cur_over=dict(source="nse_filing", basis="consolidated"))
    issues, _ = comparability_check(c, b)
    assert any("sources differ" in i for i in issues) and any("basis" in i for i in issues)
    g = growth_yoy([c, b], "revenue", CUR_END)
    assert g.status == "unverified" and g.value == Decimal("0.5") and "sources differ" in g.reason


def test_cg3_consolidated_against_standalone_is_an_issue():
    c, b = pair(cur_over=dict(basis="consolidated"), base_over=dict(basis="standalone"))
    assert any("basis differs" in i for i in comparability_check(c, b)[0])


def test_cg4_periods_must_be_about_a_year_apart_and_same_type():
    c, b = pair()
    odd = fact(date(2025, 12, 31), metric="revenue", value="100", source="yahoo", evidence="e", basis="unknown")
    assert any("periods not comparable" in i for i in comparability_check(c, odd)[0])
    fy = fact(BASE_END, metric="revenue", value="100", source="yahoo", evidence="e", basis="unknown", period_type="FY")
    assert any("periods not comparable" in i for i in comparability_check(c, fy)[0])


def test_cg5_units_and_metrics_must_match():
    c, b = pair()
    other_unit = fact(BASE_END, metric="revenue", value="100", unit="USD", source="yahoo", evidence="e", basis="unknown")
    assert any("units differ" in i for i in comparability_check(c, other_unit)[0])
    other_metric = fact(BASE_END, metric="ebitda", value="100", source="yahoo", evidence="e", basis="unknown")
    assert any("different metrics" in i for i in comparability_check(c, other_metric)[0])


def test_cg6_restated_yes_is_an_issue_unknown_is_only_a_note():
    c, b = pair(base_over=dict(restated="yes"))
    assert any("restated" in i for i in comparability_check(c, b)[0])
    c, b = pair(base_over=dict(restated="no"), cur_over=dict(restated="no"))
    issues, notes = comparability_check(c, b)
    assert issues == [] and not any("restatement" in n for n in notes)


def test_cg7_missing_evidence_is_an_issue():
    c, b = pair(base_over=dict(evidence=""))
    assert any("evidence" in i for i in comparability_check(c, b)[0])


def test_cg8_unverified_growth_does_not_pass_the_checklist():
    c, b = pair(cur_over=dict(source="nse_filing", basis="consolidated"))
    g = growth_yoy([c, b], "revenue", CUR_END).with_(metric="revenue_yoy")
    fs = FactSet(entity=Entity.from_ticker("X.NS"), facts=[g], retrieved_at=NOW)
    r = {x.id: x for x in checklist(fs)}["revenue_growing"]
    assert r.result == "unavailable"
