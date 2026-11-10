from datetime import date

from indiafacts.completeness import attention_items, data_notes
from indiafacts.render import one_per_metric
from tests.factories import fact

END = date(2026, 6, 30)


def test_gap_filled_by_another_source_is_not_missing():
    items = attention_items([
        fact(END, "ebitda", None, source="yahoo", status="gap", reason="period not returned"),
        fact(END, "ebitda", "5", source="computed:filing_ebitda"),
        fact(date(2026, 3, 31), "revenue", None, source="yahoo", status="gap", reason="period not returned"),
    ])
    assert [(f.metric, f.period_end) for f in items] == [("revenue", date(2026, 3, 31))]
    assert data_notes(items) == "Data notes: 1 figures missing"


def test_data_notes_split_omits_zero_parts():
    items = [fact(END, "a", None, status="gap", reason="r"),
             fact(END, "b", "1", status="conflict", reason="r"), fact(END, "c", "1", status="unverified", reason="r"),
             fact(END, "d", "1", status="unverified", reason="r")]
    assert data_notes(items) == ("Data notes: 1 figures missing, 1 figures where sources disagree, "
                                 "2 vendor figures not checked against filings")
    assert data_notes([]) == "Data notes: nothing flagged"


def test_overview_shows_one_value_per_metric_consolidated_first():
    pt = dict(period_type="point")
    a = fact(END, "total_assets", "2275", source="nse_xbrl", basis="consolidated", **pt)
    b = fact(END, "total_assets", "2178", source="nse_xbrl", basis="standalone", **pt)
    c = fact(date(2026, 3, 31), "total_assets", "2039", source="nse_xbrl", basis="consolidated", **pt)
    assert one_per_metric([b, c, a]) == [a]
