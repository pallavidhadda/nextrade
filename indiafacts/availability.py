from __future__ import annotations

from datetime import date, timedelta

from indiafacts.models import AvailabilityKind, Fact

QUARTERLY_LAG_DAYS = 45  # Q1-Q3, SEBI LODR Reg 33 (secondary sources; verify)
ANNUAL_LAG_DAYS = 60     # Q4 and FY


def available_from(period_end: date, period_type: str) -> date:
    is_year_end = str(period_type) == "FY" or period_end.month == 3
    return period_end + timedelta(days=ANNUAL_LAG_DAYS if is_year_end else QUARTERLY_LAG_DAYS)


def with_availability(facts: list[Fact], filing_dates: dict[date, date] | None = None) -> list[Fact]:
    filing_dates = filing_dates or {}
    out = []
    for f in facts:
        if f.period_end in filing_dates:
            out.append(f.with_(available_from=filing_dates[f.period_end],
                               availability_kind=AvailabilityKind.filed))
        else:
            out.append(f.with_(available_from=available_from(f.period_end, f.period_type),
                               availability_kind=AvailabilityKind.deadline_estimate))
    return out


def filter_as_of(facts: list[Fact], as_of: date) -> tuple[list[Fact], list[Fact]]:
    public = [f for f in facts if f.available_from is None or f.available_from <= as_of]
    pending = [f for f in facts if f.available_from is not None and f.available_from > as_of]
    return public, pending
