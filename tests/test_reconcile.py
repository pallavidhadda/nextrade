from datetime import date
from decimal import Decimal

from indiafacts.analysis import reconcile_price, reconcile_sources
from tests.factories import fact

D = date(2026, 10, 25)


def pt(metric, value, unit="ratio", source="yahoo"):
    return fact(D, metric=metric, value=value, period_type="point", source=source)


def test_price_pe_eps_consistent():
    out = reconcile_price(pt("price", "1190.00"), pt("pe_ttm", "21.550163"), pt("eps_ttm", "55.22"))
    assert out.status == "ok"


def test_price_pe_eps_mismatch_flags_conflict_with_numbers():
    out = reconcile_price(pt("price", "1190.00"), pt("pe_ttm", "21.550163"), pt("eps_ttm", "50.00"))
    assert out.status == "conflict"
    assert "1190" in out.reason and "1077" in out.reason


def test_zero_eps_unavailable():
    out = reconcile_price(pt("price", "1190"), pt("pe_ttm", "21.5"), pt("eps_ttm", "0"))
    assert out.status == "unavailable" and "EPS" in out.reason


def test_cross_source_conflict_keeps_both_values():
    a, b = pt("revenue", "100", source="yahoo"), pt("revenue", "108", source="other")
    out = reconcile_sources(a, b)
    assert [f.status for f in out] == ["conflict", "conflict"]
    assert {f.value for f in out} == {Decimal("100"), Decimal("108")}
    assert "8.0%" in out[0].reason


def test_cross_source_within_tolerance_unchanged():
    a, b = pt("revenue", "100", source="yahoo"), pt("revenue", "103", source="other")
    out = reconcile_sources(a, b)
    assert [f.status for f in out] == ["ok", "ok"]
