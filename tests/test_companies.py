import json

import pytest

from indiafacts.companies import ALIASES, DATA, resolve, search


def top(q):
    return [m.symbol for m in search(q)][:3]


@pytest.mark.parametrize("typed,expected", [
    ("infosis", "INFY"), ("infosys", "INFY"), ("Infy", "INFY"), ("relaince", "RELIANCE"), ("hdfc bnk", "HDFCBANK"),
    ("tata consultancy", "TCS"), ("asian paint", "ASIANPAINT"), ("icici", "ICICIBANK"), ("bajaj fin", "BAJFINANCE"),
    ("sbi", "SBIN"), ("zomato", "ETERNAL"), ("larsen", "LT"), ("hindustan unilever", "HINDUNILVR"), ("maruthi", "MARUTI"),
])
def test_typos_and_brand_names_find_the_company(typed, expected):
    assert expected in top(typed), (typed, top(typed))


def test_aliases_point_at_real_symbols():
    symbols = {c["s"] for c in json.loads(DATA.read_text())}
    assert all(v in symbols or v in ("RELIANCE", "TCS") for v in ALIASES.values())


def test_resolve_runs_exact_inputs_and_asks_about_typos():
    assert resolve("TCS.NS") == ("TCS.NS", [])
    assert resolve("tcs")[0] == "TCS.NS"
    assert resolve("Infosys Ltd.")[0] == "INFY.NS"
    t, sugg = resolve("INFOSIS")
    assert t is None and sugg[0].symbol == "INFY"
    assert resolve("")[0] is None


def test_unknown_bare_symbol_outside_the_list_is_allowed_through_and_nonsense_is_not():
    assert resolve("ZZZQ")[0] == "ZZZQ.NS"
    assert resolve("???") == (None, [])
