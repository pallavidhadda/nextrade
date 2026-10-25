from __future__ import annotations

from datetime import date

_QUARTER_ENDS = {6: 1, 9: 2, 12: 3, 3: 4}  # month of quarter end -> fiscal quarter number
_DAY = {3: 31, 6: 30, 9: 30, 12: 31}


def fiscal_year(period_end: date) -> int:
    """India FY runs 1 Apr to 31 Mar and is named by the year it ends."""
    return period_end.year + 1 if period_end.month >= 4 else period_end.year


def fiscal_label(period_end: date, period_type: str) -> str:
    fy = f"FY{fiscal_year(period_end) % 100:02d}"
    if str(period_type) == "Q":
        return f"Q{_QUARTER_ENDS[period_end.month]} {fy}"
    return fy


def expected_quarter_ends(first: date, last: date) -> list[date]:
    ends = []
    for year in range(first.year, last.year + 1):
        for month in (3, 6, 9, 12):
            d = date(year, month, _DAY[month])
            if first <= d <= last:
                ends.append(d)
    return ends
