from datetime import date

from indiafacts.availability import available_from, filter_as_of, with_availability
from tests.factories import fact

JUN26, MAR26 = date(2026, 6, 30), date(2026, 3, 31)


def test_deadline_estimates():
    assert available_from(JUN26, "Q") == date(2026, 8, 14)
    assert available_from(MAR26, "Q") == date(2026, 5, 30)
    assert available_from(MAR26, "FY") == date(2026, 5, 30)


def test_with_availability_marks_deadline_estimate():
    [f] = with_availability([fact(JUN26)])
    assert f.available_from == date(2026, 8, 14)
    assert f.availability_kind == "deadline_estimate"


def test_as_of_filter_splits_public_and_not_yet_public():
    facts = with_availability([fact(JUN26), fact(MAR26)])
    public, pending = filter_as_of(facts, date(2026, 8, 1))
    assert [f.period_end for f in public] == [MAR26]
    assert [f.period_end for f in pending] == [JUN26]


def test_real_filing_date_overrides_deadline():
    [f] = with_availability([fact(JUN26)], filing_dates={JUN26: date(2026, 7, 18)})
    assert f.available_from == date(2026, 7, 18)
    assert f.availability_kind == "filed"


def test_boundary_inclusive():
    facts = with_availability([fact(JUN26)])
    public, pending = filter_as_of(facts, date(2026, 8, 14))
    assert len(public) == 1 and pending == []


def test_as_of_before_all_periods_returns_empty_not_error():
    facts = with_availability([fact(JUN26), fact(MAR26)])
    public, pending = filter_as_of(facts, date(2020, 1, 1))
    assert public == [] and len(pending) == 2
