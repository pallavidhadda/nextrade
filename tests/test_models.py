from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from indiafacts.models import Entity, Fact

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)


def make(**over):
    base = dict(
        entity_key="RELIANCE", metric="net_income", value=Decimal("1"), unit="INR",
        period_end=date(2026, 6, 30), period_type="Q", source="yahoo",
        retrieved_at=NOW, status="ok",
    )
    base.update(over)
    return Fact.make(**base)


def test_non_ok_fact_requires_reason():
    with pytest.raises(ValidationError):
        make(status="gap", value=None, reason="")


def test_unavailable_fact_has_null_value():
    with pytest.raises(ValidationError):
        make(status="unavailable", value=Decimal("5"), reason="not provided")
    ok = make(status="unavailable", value=None, reason="not provided")
    assert ok.value is None


def test_fact_id_is_stable():
    assert make().fact_id == make().fact_id
    assert make().fact_id != make(source="nse_ixbrl").fact_id


def test_entity_identifiers_default_unavailable():
    e = Entity.from_ticker(" reliance.ns ")
    assert e.nse_symbol.value == "RELIANCE"
    assert e.isin.status == "unavailable"
    assert e.isin.reason
    assert e.bse_code.status == "unavailable"
    assert e.resolution == "resolved"
