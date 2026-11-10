from indiafacts.checklist import checklist, grouped, summarize
from tests.test_checklist import fs


def test_grouped_counts_and_summary_unchanged():
    r = checklist(fs(net_income=-1, debt_to_equity=None, interest_service_coverage_ratio=None))
    g = {x["group"]: x for x in grouped(r)}
    assert list(g) == ["Fundamentals", "Balance sheet", "Price trend"]            # no valuation check exists
    assert g["Fundamentals"]["text"] == "3 of 4 passed, 0 unavailable"
    assert g["Balance sheet"]["text"] == "0 of 2 passed, 2 unavailable"
    assert sum(x["total"] for x in g.values()) == 9
    assert summarize(r) == "6/7 passed, 2 unavailable"
