import json

import pytest

from indiafacts.fiidii import import_file, lines, load, parse_file, summary

JSON = [{"category": "DII **", "date": "06-Nov-2026", "buyValue": "12,345.50", "sellValue": "9,000.25", "netValue": "3,345.25"},
        {"category": "FII/FPI *", "date": "06-Nov-2026", "buyValue": "8000", "sellValue": "10000", "netValue": "-2000"}]

LONG_CSV = """FII/DII Trading Activity (Rs. Crores)
Category,Date,Buy Value(Rs Crores),Sell Value(Rs Crores),Net Value(Rs Crores)
DII,05-Nov-2026,"11,000.00","10,000.00","1,000.00"
FII/FPI,05-Nov-2026,9000,9500,-500
"""

WIDE_CSV = """Date,FII Buy,FII Sell,FII Net,DII Buy,DII Sell,DII Net
04-Nov-2026,7000,8000,-1000,9000,7500,1500
03-Nov-2026,7000,6000,1000,9000,9500,-500
"""


def save(tmp, name, text):
    p = tmp / name
    p.write_text(text if isinstance(text, str) else json.dumps(text))
    return p


def test_json_from_the_nse_page_is_read():
    rows = parse_file_from(JSON)
    assert {(r.category, r.net) for r in rows} == {("DII", 3345.25), ("FII", -2000.0)}


def parse_file_from(data, tmp=None, suffix=".json"):
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    return parse_file(save(d, "x" + suffix, data))


def test_long_csv_with_title_line_and_thousand_separators():
    rows = parse_file_from(LONG_CSV, suffix=".csv")
    assert {(r.category, r.buy, r.net) for r in rows} == {("DII", 11000.0, 1000.0), ("FII", 9000.0, -500.0)}


def test_wide_csv_layout():
    rows = parse_file_from(WIDE_CSV, suffix=".csv")
    assert len(rows) == 4 and {r.category for r in rows} == {"FII", "DII"}


def test_missing_net_is_computed_and_garbage_is_refused(tmp_path):
    p = save(tmp_path, "a.json", [{"category": "FII", "date": "2026-11-02", "buy": 100, "sell": 40}])
    assert parse_file(p)[0].net == 60
    with pytest.raises(ValueError):
        parse_file(save(tmp_path, "b.csv", "hello,world\n1,2\n"))
    with pytest.raises(ValueError):
        parse_file(save(tmp_path, "c.json", [{"x": 1}]))


def test_import_merges_without_duplicates_and_builds_summary(tmp_path):
    store = tmp_path / "s.csv"
    a = save(tmp_path, "w.csv", WIDE_CSV)
    assert import_file(a, store) == (4, 0)
    assert import_file(a, store) == (0, 4)
    assert import_file(save(tmp_path, "j.json", JSON), store)[0] == 2
    assert len(load(store)) == 6
    s = summary(store=store)
    fii = [r for r in s["rows"] if r["category"] == "FII"][0]
    assert fii["last_net"] == -2000.0 and fii["streak_word"] == "net selling" and fii["window_net"] == -2000.0 + -1000.0 + 1000.0
    text = "\n".join(lines(s))
    assert "from files you saved from NSE" in text and "not one stock" not in text.lower() or "Whole market" in text


def test_combined_shows_cash_even_when_the_derivatives_file_is_unreachable(tmp_path, monkeypatch):
    from indiafacts import flows
    monkeypatch.setenv("INDIAFACTS_FIIDII_STORE", str(tmp_path / "f.csv"))
    import_file(save(tmp_path, "w.csv", WIDE_CSV))
    c = flows.combined(days=[])
    assert c is not None and c["rows"] == [] and c["cash"]["rows"]
    text = "\n".join(flows.lines(c))
    assert "CASH-MARKET FII/DII" in text and "net" in text
    assert flows.combined(days=[]) is not None
    monkeypatch.setenv("INDIAFACTS_FIIDII_STORE", str(tmp_path / "none.csv"))
    assert flows.combined(days=[]) is None
