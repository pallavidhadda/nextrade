from indiafacts.debate import Debate, Point, Stance
from indiafacts.narrative import case_prose, theme


def deb():
    return Debate(bull=[Point("Quality scores 77 of 100 against the comparison pool", "score:quality"),
                        Point("Free cash flow is 5.3% of the market value, a solid cash return", "health:fy_fcf_yield"),
                        Point("Return on capital employed is 54.9%, a strong return on the money in the business", "health:fy_roce")],
                  bear=[Point("Momentum scores only 17 of 100 against the comparison pool", "score:momentum"),
                        Point("Check failed: Price is higher than a year ago (-17.0%, needs > 0%)", "check:positive_1y_return")],
                  stance=Stance("Hold", "Medium", "x"))


def test_prose_names_the_strongest_theme_and_keeps_each_figure():
    p = case_prose(deb())
    assert "cash flow and the balance sheet" in p.favour and "54.9%" in p.favour and p.strongest_for == "cash flow and the balance sheet"
    assert "the recent price trend" in p.against and "17" in p.against
    assert "3 points in favour and 2 against" in p.weighing and "Hold" in p.weighing and "not a prediction" in p.weighing


def test_empty_sides_and_no_rating_are_handled():
    d = Debate(bull=[], bear=deb().bear, stance=Stance("Underweight", "Low", "x"))
    assert "nothing stands out" in case_prose(d).favour
    assert case_prose(Debate()).weighing == "" and case_prose(None).favour == ""
    assert theme("unknown:key") == "other evidence"


def test_check_wording_reads_as_a_fragment():
    from indiafacts.narrative import clean
    assert clean("Check passed: Profit is higher than a year earlier (+1.4%)") == "Profit is higher than a year earlier (+1.4%)"
    assert clean("Check failed: Price is higher than a year ago (-17.0%, needs > 0%)") == '"Price is higher than a year ago" did not hold (-17.0%, needs > 0%)'
