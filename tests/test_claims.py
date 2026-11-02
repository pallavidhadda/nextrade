from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from indiafacts.claims import check_claim, to_base_units
from indiafacts.models import Entity, Fact, FactSet

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def fs_of(*rows):
    facts = []
    for metric, value, unit, source, label, ptype, status in rows:
        end = date(2026, 9, 30) if ptype == "Q" else date(2026, 11, 2)
        facts.append(Fact.make(entity_key="ABC.NS", metric=metric, value=None if value is None else Decimal(str(value)), unit=unit, period_end=end,
                               period_type=ptype, fiscal_label=label, source=source, source_field="f", retrieved_at=NOW, status=status,
                               reason="" if status == "ok" else "why", evidence="doc | row"))
    return FactSet(entity=Entity.from_ticker("ABC.NS"), facts=facts, retrieved_at=NOW)


FS = fs_of(("net_income", 138840000000, "INR", "yahoo", "Q2 FY27", "Q", "ok"),
           ("net_income", 138830000000, "INR", "nse_xbrl", "Q2 FY27", "Q", "ok"),
           ("eps_ttm", 142.66, "INR_per_share", "yahoo", None, "point", "ok"),
           ("pe_ttm", 17.54, "ratio", "yahoo", None, "point", "ok"),
           ("roe", 0.52, "ratio", "yahoo", None, "point", "ok"),
           ("revenue", 731880000000, "INR", "yahoo", "Q2 FY27", "Q", "unverified"))


def test_c1_unit_conversion():
    assert to_base_units(13884, "crore") == Decimal("138840000000")
    assert to_base_units(1.5, "lakh_crore") == Decimal("1500000000000")
    assert to_base_units(52, "percent") == Decimal("0.52")
    assert to_base_units(17.5, "ratio") == Decimal("17.5")


def test_c2_matching_claim_is_supported_with_sources_listed():
    r = check_claim(FS, "net profit", 13884, "crore", "Q2 FY27")
    assert r.verdict == "supported" and {m.source for m in r.matches} == {"yahoo", "nse_xbrl"} and r.matches[0].fact_id


def test_c3_wrong_claim_is_contradicted_with_the_actual_value_and_gap():
    r = check_claim(FS, "eps", 59.69, "per_share")
    assert r.verdict == "contradicted" and r.closest.value == Decimal("142.66") and abs(r.difference_pct) > 50


def test_c4_tolerance_is_respected_and_stated():
    near = check_claim(FS, "pe", 17.6, "ratio")
    assert near.verdict == "supported" and near.tolerance_pct == 1.0 and abs(near.difference_pct) < 1
    assert check_claim(FS, "pe", 19.0, "ratio").verdict == "contradicted"


def test_c5_percent_claims_compare_with_fractions():
    assert check_claim(FS, "roe", 52, "percent").verdict == "supported"


def test_c6_unverified_only_figures_are_not_called_supported():
    r = check_claim(FS, "revenue", 73188, "crore", "Q2 FY27")
    assert r.verdict == "supported_unverified" and "unverified" in r.explanation.lower()


def test_c7_unknown_metric_period_or_missing_unit_is_unverifiable_not_guessed():
    assert check_claim(FS, "dividend yield", 1.0, "percent").verdict == "unverifiable"
    r = check_claim(FS, "net profit", 13884, "crore", "Q1 FY19")
    assert r.verdict == "unverifiable" and "Q2 FY27" in r.explanation
    r2 = check_claim(FS, "net profit", 13884, None)
    assert r2.verdict == "unverifiable" and "unit" in r2.explanation.lower()


def test_c8_text_has_no_opinion_words():
    for r in (check_claim(FS, "eps", 59.69, "per_share"), check_claim(FS, "pe", 17.6, "ratio")):
        assert not any(w in r.explanation.lower() for w in ("buy", "sell", "should", "recommend"))


def test_c9_amounts_read_in_crore_and_period_hint_is_given_for_undated_claims():
    r = check_claim(FS, "net profit", 15000, "crore", "Q2 FY27")
    assert "₹15,000 cr" in r.explanation and "₹13,884 cr" in r.explanation
    e = check_claim(FS, "eps", 59.69, "per_share")
    assert "give the period" in e.explanation.lower()
