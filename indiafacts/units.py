from __future__ import annotations

from decimal import Decimal

CRORE = Decimal(10) ** 7
LAKH_CRORE = Decimal(10) ** 12


def format_inr(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    mag = abs(value)
    if mag >= LAKH_CRORE:
        return f"{sign}₹{mag / LAKH_CRORE:,.2f} lakh cr"
    if mag >= CRORE:
        return f"{sign}₹{(mag / CRORE).quantize(Decimal(1)):,} cr"
    return f"{sign}₹{mag:,.2f}"
