from datetime import date, datetime, timezone
from decimal import Decimal

from indiafacts.models import Fact

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)


def fact(period_end=date(2026, 6, 30), metric="net_income", value="1", period_type="Q",
         source="yahoo", status="ok", reason="", **over):
    v = None if value is None else Decimal(value)
    return Fact.make(
        entity_key="RELIANCE", metric=metric, value=v, unit="INR", period_end=period_end,
        period_type=period_type, source=source, retrieved_at=NOW, status=status,
        reason=reason, **over,
    )
