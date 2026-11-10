from datetime import date, datetime, timezone
from decimal import Decimal

from indiafacts.htmlreport import _Ctx, _ratio_cards
from indiafacts.models import Fact

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def q(metric, d, v):
    return Fact.make(entity_key="X.NS", metric=metric, value=None if v is None else Decimal(str(v)), unit="INR", period_end=d,
                     period_type="Q", source="nse", retrieved_at=NOW, status="ok" if v is not None else "unavailable", reason="" if v is not None else "none")


def test_margin_and_yoy_only_where_both_quarters_exist():
    facts = [q("revenue", date(2025, 6, 30), 1000), q("net_income", date(2025, 6, 30), 100),
             q("revenue", date(2025, 9, 30), 1000), q("net_income", date(2025, 9, 30), None),
             q("revenue", date(2026, 6, 30), 1200), q("net_income", date(2026, 6, 30), 180)]
    ctx = _Ctx()
    html = _ratio_cards(facts, ctx)
    assert "10.0%" in html and "15.0%" in html             # margins 100/1000 and 180/1200
    assert "+20.0%" in html and "+80.0%" in html           # YoY revenue 1200/1000, profit 180/100
    assert html.count("gap") >= 3                          # Sep-25 margin has no profit; Sep-25 has no prior year; etc.
