import random
import re
from datetime import date, timedelta

import pytest

from indiafacts.analysis import add_gaps
from indiafacts.render import DISCLAIMER, render, render_table
from indiafacts.yahoo import fetch_facts
from tests.factories import NOW, fact
from tests.fakes import FakeClient

NO_SLEEP = dict(sleep=lambda s: None)


def reliance(as_of=None):
    return add_gaps(fetch_facts("RELIANCE.NS", as_of=as_of, client=FakeClient(), **NO_SLEEP))


def test_render_rejects_bare_numbers():
    with pytest.raises(TypeError):
        render_table([1.5, 2.5])


def test_disclaimer_present():
    assert DISCLAIMER in render(reliance())


def test_basis_unknown_printed():
    assert "basis: unknown" in render(reliance())


def test_sep25_gap_shown_as_unav():
    out = render(reliance())
    assert "Q2 FY26" in out
    row = next(l for l in out.splitlines() if l.startswith("| net_income"))
    assert "unav" in row


def test_amounts_rendered_in_crore_with_ref():
    out = render(reliance())
    assert "₹20,946 cr" in out and re.search(r"₹20,946 cr \[r\d+\]", out)


def test_unavailable_overview_listed_under_could_not_check():
    out = render(reliance())
    section = out.split("Could not check")[1].split("\n\n")[0]
    assert "roe" in section and "not provided by Yahoo" in section


def test_not_yet_public_listed():
    out = render(reliance(as_of=date(2026, 8, 1)), as_of=date(2026, 8, 1))
    section = out.split("Not yet public")[1]
    assert "Q1 FY27" in section and "2026-08-14" in section and "deadline estimate" in section


def test_every_table_number_has_a_ref_in_index():
    rng = random.Random(7)
    facts = []
    for i in range(60):
        end = date(2024, 3, 31) + timedelta(days=91 * rng.randint(0, 8))
        end = date(end.year, ((end.month - 1) // 3 + 1) * 3, 30 if end.month in (4, 5, 6, 9, 10, 11) else 31)
        metric = rng.choice(["net_income", "ebitda", "interest_expense"])
        if rng.random() < 0.25:
            facts.append(fact(end, metric=metric, value=None, status="unavailable", reason="x"))
        else:
            facts.append(fact(end, metric=metric, value=str(rng.randint(-10**11, 10**12))))
    table = render_table(facts)
    index_ids = set(re.findall(r"^(r\d+) =", table, re.M))
    cells = [c.strip() for l in table.splitlines() if l.startswith("|") for c in l.strip("|").split("|")[1:]]
    for c in cells:
        if re.search(r"\d", c) and not c.startswith("Q"):
            m = re.search(r"\[(r\d+)\]$", c)
            assert m and m.group(1) in index_ids, c
