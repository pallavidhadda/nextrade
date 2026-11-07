from datetime import date

import pytest

from indiafacts.flows import history, lines, parse, summary

CSV = b'''"Participant wise Open Interest (no. of contracts) in Equity Derivatives as on Nov 06, 2026",,,
Client Type,Future Index Long,Future Index Short,Future Stock Long
Client,180828,97047,1
DII,54004,18468,1
FII,48656,149072,1
Pro,29551,48452,1
TOTAL,313039,313039,1
'''


class R:
    def __init__(self, b): self.b = b
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self, n=-1): return self.b


def test_parse_computes_net_and_long_share():
    d = parse(CSV, date(2026, 11, 6))
    assert d.net["FII"] == 48656 - 149072 and d.long_share["FII"] == pytest.approx(48656 / (48656 + 149072))
    assert "TOTAL" not in d.net


def test_history_skips_missing_days_and_caches(tmp_path):
    calls = []

    def op(req, timeout):
        calls.append(req.full_url)
        if "05112026" in req.full_url or "06112026" in req.full_url:
            return R(CSV)
        raise OSError("404")
    days = history(date(2026, 11, 6), sessions=2, opener=op, cache_dir=tmp_path)
    assert [d.day for d in days] == [date(2026, 11, 6), date(2026, 11, 5)]
    n = len(calls)
    history(date(2026, 11, 6), sessions=2, opener=op, cache_dir=tmp_path)
    assert len(calls) == n                                               # second run reads the cache


def test_summary_and_lines_are_plain_and_labelled_market_wide():
    d = parse(CSV, date(2026, 11, 6))
    s = summary([d])
    fii = [r for r in s["rows"] if r["participant"] == "FII"][0]
    assert fii["stance"] == "net short"
    text = "\n".join(lines(s))
    assert "whole market" in text and "not the cash-market" in text
    assert "could not be read" in "\n".join(lines(None))
