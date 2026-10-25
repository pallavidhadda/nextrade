from datetime import date
from decimal import Decimal

from indiafacts.checklist import CHECKS, checklist, summarize
from tests.test_scoring import AS_OF, NOW, mkfs

GOOD = {"net_income_q": None}
VALUES = {"net_income": 5e10, "eps_ttm": 50, "net_income_yoy": 0.1, "revenue_yoy": 0.05,
          "interest_service_coverage_ratio": 4.0, "debt_to_equity": 0.5, "return_1y": 0.1,
          "relative_return_1y": 0.02, "pct_from_52w_high": -0.1}


def fs(**over):
    v = {**VALUES, **over}
    return mkfs("X.NS", {k: x for k, x in v.items() if x is not None})


def results(**over):
    return {c.id: c for c in checklist(fs(**over))}


def test_nine_checks_all_pass_on_a_healthy_company():
    r = checklist(fs())
    assert len(r) == len(CHECKS) == 9 and all(c.result == "pass" for c in r)
    assert summarize(r) == "9/9 passed"


def test_each_check_can_fail():
    bad = dict(net_income=-1, eps_ttm=-2, net_income_yoy=-0.1, revenue_yoy=-0.1, interest_service_coverage_ratio=1.0,
               debt_to_equity=2.0, return_1y=-0.2, relative_return_1y=-0.1, pct_from_52w_high=-0.6)
    r = checklist(fs(**bad))
    assert all(c.result == "fail" for c in r) and summarize(r) == "0/9 passed"


def test_missing_data_is_unavailable_not_fail():
    r = results(interest_service_coverage_ratio=None, return_1y=None)
    assert r["interest_cover"].result == "unavailable" and "no data" in r["interest_cover"].reason
    assert r["positive_1y_return"].result == "unavailable"
    assert summarize(list(r.values())) == "7/7 passed, 2 unavailable"


def test_thresholds_are_exclusive_where_stated():
    assert results(net_income=0)["profitable_latest_quarter"].result == "fail"
    assert results(debt_to_equity=1.0)["debt_moderate"].result == "fail"
    assert results(interest_service_coverage_ratio=3.0)["interest_cover"].result == "pass"
    assert results(pct_from_52w_high=-0.25)["near_52w_high"].result == "pass"


def test_provenance_and_neutral_wording():
    for c in checklist(fs()):
        assert c.fact_ids and c.label
        assert not any(w in c.label.lower() for w in ("buy", "sell", "should"))


def test_unverified_or_unavailable_input_facts_are_ignored():
    f = mkfs("X.NS", {k: v for k, v in VALUES.items() if k != "net_income"})
    r = {c.id: c for c in checklist(f)}
    assert r["profitable_latest_quarter"].result == "unavailable"


def test_values_are_displayed_readably():
    r = {c.id: c for c in checklist(fs())}
    assert r["profitable_latest_quarter"].display == "₹5,000 cr"
    assert r["earnings_growing"].display == "+10.0%"
    assert r["debt_moderate"].display == "0.50"
    assert r["near_52w_high"].display == "-10.0%"
    assert {c.id: c for c in checklist(fs(net_income=None))}["profitable_latest_quarter"].display == ""
