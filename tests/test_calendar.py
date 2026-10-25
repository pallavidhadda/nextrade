from datetime import date

from indiafacts.calendar import expected_quarter_ends, fiscal_label


def test_fiscal_labels():
    assert fiscal_label(date(2026, 6, 30), "Q") == "Q1 FY27"
    assert fiscal_label(date(2026, 3, 31), "Q") == "Q4 FY26"
    assert fiscal_label(date(2026, 3, 31), "FY") == "FY26"
    assert fiscal_label(date(2025, 12, 31), "Q") == "Q3 FY26"
    assert fiscal_label(date(2025, 9, 30), "Q") == "Q2 FY26"


def test_expected_quarter_ends_spans_gap():
    ends = expected_quarter_ends(date(2025, 3, 31), date(2026, 6, 30))
    assert len(ends) == 6
    assert date(2025, 9, 30) in ends
    assert ends == sorted(ends)
