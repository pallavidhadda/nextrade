from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from indiafacts.models import Entity, Fact, FactSet
from indiafacts.valuation import (applicable_methods, implied_growth, load_valuation_params, present_value, valuation_facts)

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
ASOF = date(2026, 10, 31)
BANNED = ("buy", "sell", "undervalued", "overvalued", "target", "cheap", "expensive")


def mk(ticker="ABC.NS", sector="Energy", industry="Refining", **vals):
    facts = []
    for m, (v, unit, status) in {k: (x if isinstance(x, tuple) else (x, "ratio", "ok")) for k, x in vals.items()}.items():
        facts.append(Fact.make(entity_key=ticker, metric=m, value=None if v is None else Decimal(str(v)), unit=unit, period_end=ASOF,
                               period_type="point", source="yahoo", retrieved_at=NOW, status=status,
                               reason="" if status == "ok" else "n/a"))
    e = Entity.from_ticker(ticker).model_copy(update={"sector": sector, "industry": industry})
    return FactSet(entity=e, facts=facts, retrieved_at=NOW)


def test_v1_growing_perpetuity_closed_form():
    eps, r, g = 10.0, 0.12, 0.05
    price = eps * (1 + g) / (r - g)
    assert implied_growth(price, eps, r, years=10, terminal=g) == pytest.approx(g, abs=1e-6)


def test_v2_higher_price_implies_higher_growth_and_pv_roundtrip():
    lo = implied_growth(100, 5, 0.12, 10, 0.05)
    hi = implied_growth(300, 5, 0.12, 10, 0.05)
    assert lo < hi
    assert present_value(5, hi, 0.12, 10, 0.05) == pytest.approx(300, rel=1e-6)


def test_v3_unsolvable_prices_return_none():
    assert implied_growth(1e9, 5, 0.12, 10, 0.05) is None
    assert implied_growth(0.0001, 5, 0.12, 10, 0.05) is None


def test_v4_higher_discount_rate_needs_more_growth():
    assert implied_growth(200, 5, 0.10, 10, 0.05) < implied_growth(200, 5, 0.14, 10, 0.05)


def test_v5_reverse_dcf_grid_for_non_financial():
    fs = mk(price=(1000, "INR", "ok"), eps_ttm=(40, "INR_per_share", "ok"))
    out = [f for f in valuation_facts(fs, today=ASOF) if f.metric.startswith("implied_growth")]
    assert len(out) == 6 and all(f.status == "ok" and f.unit == "percent" for f in out)
    assert all("assumption" in (f.source_field or "") for f in out)
    assert {f.source for f in out} == {"computed:valuation"}


def test_v6_negative_eps_withholds_with_reason():
    fs = mk(price=(1000, "INR", "ok"), eps_ttm=(-3, "INR_per_share", "ok"))
    out = [f for f in valuation_facts(fs, today=ASOF) if f.metric.startswith("implied_growth")]
    assert out and all(f.status == "unavailable" and "not positive" in f.reason for f in out)


def test_v7_unverified_or_missing_inputs_withhold():
    fs = mk(price=(1000, "INR", "ok"), eps_ttm=(40, "INR_per_share", "unverified"))
    out = [f for f in valuation_facts(fs, today=ASOF) if f.metric.startswith("implied_growth")]
    assert out and all(f.status == "unavailable" for f in out)
    fs = mk(price=(1000, "INR", "ok"))
    assert all(f.status == "unavailable" for f in valuation_facts(fs, today=ASOF) if f.metric.startswith("implied_growth"))


def test_v8_banks_use_book_value_methods_not_earnings_dcf():
    fs = mk("BANK.NS", sector="Financial Services", industry="Private Sector Bank",
            price=(1500, "INR", "ok"), eps_ttm=(80, "INR_per_share", "ok"), roe=0.17, pb=2.8)
    assert applicable_methods(fs.entity) == ["justified_pb"]
    out = valuation_facts(fs, today=ASOF)
    assert not [f for f in out if f.metric.startswith("implied_growth") and f.status == "ok"]
    lo = next(f for f in out if f.metric == "justified_pb_low")
    hi = next(f for f in out if f.metric == "justified_pb_high")
    assert 0 < float(lo.value) < float(hi.value) and lo.status == hi.status == "ok"


def test_v9_bank_without_roe_is_unavailable_not_guessed():
    fs = mk("BANK.NS", sector="Financial Services", industry="Public Sector Bank", price=(100, "INR", "ok"), pb=1.1)
    out = [f for f in valuation_facts(fs, today=ASOF) if f.metric.startswith("justified_pb")]
    assert out and all(f.status == "unavailable" and "ROE" in f.reason for f in out)


def test_v10_params_have_review_dates_and_strict_overdue_fails():
    p = load_valuation_params(today=ASOF)
    assert p["discount_rates"] and p["horizons"] and "terminal_growth" in p
    with pytest.raises(ValueError):
        load_valuation_params(today=date(2030, 1, 1), strict=True)
    assert load_valuation_params(today=date(2030, 1, 1), strict=False)["overdue"] is True


def test_v11_no_opinion_words_in_any_output_text():
    fs = mk(price=(1000, "INR", "ok"), eps_ttm=(40, "INR_per_share", "ok"))
    for f in valuation_facts(fs, today=ASOF):
        text = f"{f.reason} {f.source_field}".lower()
        assert not any(w in text for w in BANNED)
