import json
from datetime import date

import pandas as pd
import pytest

from indiafacts.yahoo import METRIC_MAP, RETRY_COUNT, fetch_facts
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY


NO_SLEEP = dict(sleep=lambda s: None)


def test_empty_response_retried_then_unresolved():
    c = FakeClient(stmt=None, info={})
    fs = fetch_facts("TATAMOTORS.NS", client=c, **NO_SLEEP)
    assert c.calls == RETRY_COUNT == 3
    assert fs.entity.resolution == "unresolved"
    assert "ticker may have changed" in fs.entity.resolution_reason
    assert fs.facts == []


def test_transient_failure_then_success():
    c = FakeClient(fail_first=1)
    fs = fetch_facts("RELIANCE.NS", client=c, **NO_SLEEP)
    assert c.calls == 2
    assert fs.entity.resolution == "resolved"
    assert fs.by_metric("net_income")


def test_basis_is_unknown():
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP)
    assert {f.basis for f in fs.facts} == {"unknown"}


def test_statement_facts_have_period_unit_source():
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP)
    ni = {f.period_end: f for f in fs.by_metric("net_income")}
    assert len(ni) == 5 and date(2025, 9, 30) not in ni
    jun26 = ni[date(2026, 6, 30)]
    assert str(jun26.value) == "209460000000.0" or float(jun26.value) == 209460000000.0
    assert jun26.unit == "INR" and jun26.source == "yahoo"
    assert jun26.fiscal_label == "Q1 FY27" and jun26.period_type == "Q"
    eps = fs.by_metric("eps_diluted")[0]
    assert eps.unit == "INR_per_share"


def test_missing_overview_field_becomes_unavailable_fact():
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP)
    [roe] = fs.by_metric("roe")
    assert roe.status == "unavailable" and roe.value is None
    assert "not provided by Yahoo" in roe.reason


def test_vendor_ttm_is_unverified():
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP)
    [ttm] = fs.by_metric("net_income_ttm_vendor")
    assert ttm.status == "unverified" and ttm.period_type == "TTM"


def test_nan_cell_becomes_unavailable_not_number():
    stmt = QUARTERLY.copy()
    stmt.loc["EBITDA", pd.Timestamp("2025-12-31")] = float("nan")
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(stmt=stmt), **NO_SLEEP)
    dec = [f for f in fs.by_metric("ebitda") if f.period_end == date(2025, 12, 31)]
    assert len(dec) == 1 and dec[0].status == "unavailable" and dec[0].value is None


def test_non_inr_reporting_currency_is_flagged():
    info = {**INFO, "financialCurrency": "USD"}
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(info=info), **NO_SLEEP)
    assert all(f.status != "ok" for f in fs.by_metric("net_income"))
    assert "USD" in fs.by_metric("net_income")[0].reason


def test_ticker_normalisation():
    a = fetch_facts(" reliance.ns ", client=FakeClient(), **NO_SLEEP).entity
    b = fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP).entity
    assert a.ticker == b.ticker == "RELIANCE.NS"
    bo = fetch_facts("reliance.bo", client=FakeClient(), **NO_SLEEP).entity
    assert bo.ticker == "RELIANCE.BO"


@pytest.mark.parametrize("bad", ["../etc/passwd", "REL IANCE.NS", "", "A;B"])
def test_invalid_ticker_rejected(bad):
    with pytest.raises(ValueError):
        fetch_facts(bad, client=FakeClient(), **NO_SLEEP)


def test_as_of_moves_unpublished_periods_out(monkeypatch):
    fs = fetch_facts("RELIANCE.NS", as_of=date(2026, 8, 1), client=FakeClient(), **NO_SLEEP)
    assert date(2026, 6, 30) not in {f.period_end for f in fs.facts if f.period_type == "Q"}
    assert date(2026, 6, 30) in {f.period_end for f in fs.not_yet_public}


def test_no_secrets_in_facts(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "SECRET123")
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP)
    assert "SECRET123" not in fs.model_dump_json()
    json.loads(fs.model_dump_json())


def test_metric_map_covers_spec_metrics():
    assert set(METRIC_MAP.values()) >= {"net_income", "ebitda", "interest_expense", "eps_diluted"}
