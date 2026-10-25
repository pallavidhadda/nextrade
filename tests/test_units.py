from decimal import Decimal

from indiafacts.units import format_inr


def test_format_inr():
    assert format_inr(Decimal("209460000000")) == "₹20,946 cr"
    assert format_inr(Decimal("16103642234880")) == "₹16.10 lakh cr"
    assert format_inr(Decimal("-83370000000")) == "-₹8,337 cr"


def test_format_inr_small_values():
    assert format_inr(Decimal("15.48")) == "₹15.48"
