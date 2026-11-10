import pandas as pd

from indiafacts.fundamentals import annual_facts
from indiafacts.models import Status
from tests.test_fundamentals import NOW, YEARS, stmts


def test_column_without_any_read_row_is_dropped_with_one_notice():
    st = stmts()
    old = pd.Timestamp("2022-03-31")
    for df in st.values():
        df[old] = float("nan")                                   # Yahoo lists the year with no values
        df.loc["Some Other Row", :] = 1.0                        # rows we do not read may be filled
    notes: list[str] = []
    facts = annual_facts("ABC.NS", st, "Energy", None, NOW, notices=notes)
    assert not any(f.period_end == old.date() for f in facts)
    assert notes == ["Yahoo lists the year ending 2022-03-31 without figures; annual history starts at FY23"]


def test_partly_filled_column_keeps_per_row_gaps():
    st = stmts()
    st["income"].loc["EBITDA", YEARS[1]] = float("nan")
    notes: list[str] = []
    facts = annual_facts("ABC.NS", st, "Energy", None, NOW, notices=notes)
    assert notes == []
    f = [x for x in facts if x.metric == "fy_ebitda" and x.period_end.year == 2025][0]
    assert f.status == Status.unavailable
