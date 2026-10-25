from datetime import date
from decimal import Decimal

from indiafacts.analysis import add_gaps, detect_gaps, growth_yoy, resolve_duplicates, ttm
from indiafacts.yahoo import fetch_facts
from tests.factories import fact
from tests.fakes import FakeClient

NO_SLEEP = dict(sleep=lambda s: None)
Q = [date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]


def quarters(values, ends=Q):
    return [fact(e, value=v) for e, v in zip(ends, values)]


def test_fixture_q_has_exactly_one_gap():
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP)
    gaps = detect_gaps(fs.facts, "net_income")
    assert [g.period_end for g in gaps] == [date(2025, 9, 30)]
    assert gaps[0].status == "gap" and gaps[0].value is None and "yahoo" in gaps[0].reason


def test_ttm_unavailable_when_quarter_missing():
    fs = fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP)
    out = ttm(fs.facts, "net_income", date(2026, 6, 30))
    assert out.status == "unavailable" and out.value is None
    assert "2025-09-30" in out.reason


def test_ttm_sums_four_consecutive_quarters():
    facts = quarters(["10", "20", "30", "40"], ends=Q[1:])
    out = ttm(facts, "net_income", date(2026, 6, 30))
    assert out.status == "ok" and out.value == Decimal("100") and out.period_type == "TTM"
    assert len(out.related_fact_ids) == 4


def test_ttm_fewer_than_four_quarters():
    out = ttm(quarters(["1", "2", "3"], ends=Q[2:]), "net_income", date(2026, 6, 30))
    assert out.status == "unavailable" and "fewer than 4 quarters returned" in out.reason


def test_negative_values_flow_through_ttm():
    out = ttm(quarters(["-10", "20", "-30", "5"], ends=Q[1:]), "net_income", date(2026, 6, 30))
    assert out.value == Decimal("-15")


def test_growth_yoy_and_negative_base():
    facts = quarters(["100", "0", "0", "0", "150"])
    assert growth_yoy(facts, "net_income", date(2026, 6, 30)).value == Decimal("0.5")
    neg = quarters(["-100", "0", "0", "0", "150"])
    out = growth_yoy(neg, "net_income", date(2026, 6, 30))
    assert out.status == "unavailable" and "base not positive" in out.reason


def test_duplicate_period_columns_conflict():
    dup = [fact(Q[4], value="10"), fact(Q[4], value="12")]
    [out] = resolve_duplicates(dup)
    assert out.status == "conflict" and "10" in out.reason and "12" in out.reason
    same = resolve_duplicates([fact(Q[4], value="10"), fact(Q[4], value="10")])
    assert len(same) == 1 and same[0].status == "ok"


def test_add_gaps_appends_gap_facts_to_factset():
    fs = add_gaps(fetch_facts("RELIANCE.NS", client=FakeClient(), **NO_SLEEP))
    gaps = [f for f in fs.facts if f.status == "gap"]
    assert {g.metric for g in gaps} >= {"net_income", "ebitda"}
    assert all(g.period_end == date(2025, 9, 30) for g in gaps)
