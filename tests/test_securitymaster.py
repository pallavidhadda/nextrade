import json
from datetime import date
from pathlib import Path

import pytest

from indiafacts.securitymaster import load_curated, load_symbol_changes, resolve_symbol

CSV = """NAME OF THE COMPANY,OLD SYMBOL,NEW SYMBOL,EFFECTIVE DATE
ETERNAL LIMITED,ZOMATO,ETERNAL,09-APR-2025
Tata Motors Limited,TELCO,TATAMOTORS,26-DEC-2003
Tata Motors Passenger Vehicles Limited,TATAMOTORS,TMPV,24-OCT-2025
Old Co,REUSED,OTHERNAME,01-JAN-2010
New Co,SOMETHING,REUSED,01-JAN-2018
Self Map Co,SELFMAP,SELFMAP,01-JAN-2020
,BLANKNAME,BLANKNEW,05-MAY-2021
Bad Date Co,BADDATE,NEWBAD,not-a-date
"""


@pytest.fixture
def changes(tmp_path):
    p = tmp_path / "symbolchange.csv"
    p.write_text(CSV, encoding="utf-8")
    return load_symbol_changes(p)


def curated_json(tmp_path, **over):
    entry = dict(old_symbol="TATAMOTORS", successors=["TMPV", "TMCV"], change_type="demerger",
                 effective_date="2025-10-01", source_urls=["https://example.org/circular"],
                 reviewed_on="2026-10-26", review_by="2027-04-26", notes="test")
    entry.update(over)
    p = tmp_path / "sm.json"
    p.write_text(json.dumps({"entries": [entry]}))
    return p


TODAY = date(2026, 10, 26)


@pytest.fixture
def curated(tmp_path):
    return load_curated(curated_json(tmp_path), today=TODAY)


def test_loader_skips_bad_date_and_self_map_and_keeps_blank_name(changes):
    olds = {c.old for c in changes}
    assert "BADDATE" not in olds and "SELFMAP" not in olds and "BLANKNAME" in olds
    assert changes.skipped == 2


def test_rename_redirects_with_notice(changes, curated):
    r = resolve_symbol("zomato.ns", changes, curated)
    assert r.kind == "renamed" and r.symbols == ["ETERNAL"]
    assert "2025-04-09" in r.notice and "ZOMATO" in r.notice and "ETERNAL" in r.notice


def test_demerger_returns_both_successors_and_never_picks(changes, curated):
    r = resolve_symbol(" TATAMOTORS ", changes, curated)
    assert r.kind == "split" and r.symbols == ["TMPV", "TMCV"]
    assert "demerger" in r.notice


def test_chain_through_curated_split(changes, curated):
    r = resolve_symbol("TELCO", changes, curated)
    assert r.kind == "split" and r.symbols == ["TMPV", "TMCV"] and len(r.chain) == 1


def test_chain_without_curated_follows_to_end(changes):
    r = resolve_symbol("TELCO", changes, [])
    assert r.kind == "renamed" and r.symbols == ["TMPV"] and len(r.chain) == 2


def test_active_symbol_is_direct(changes, curated):
    assert resolve_symbol("ETERNAL", changes, curated).kind == "direct"
    assert resolve_symbol("TMPV.NS", changes, curated).symbols == ["TMPV"]


def test_reused_symbol_is_direct_not_redirected(changes, curated):
    assert resolve_symbol("REUSED", changes, curated).kind == "direct"


def test_unknown_symbol_message(changes, curated):
    r = resolve_symbol("NOSUCH", changes, curated)
    assert r.kind == "unknown" and r.symbols == ["NOSUCH"] and "not in security master" in r.notice


def test_unknown_when_no_csv_loaded_says_so(curated):
    r = resolve_symbol("NOSUCH", None, curated)
    assert "symbol-change list not loaded" in r.notice


def test_cycle_rejected_at_load(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("NAME OF THE COMPANY,OLD SYMBOL,NEW SYMBOL,EFFECTIVE DATE\nA,AAA,BBB,01-JAN-2010\nB,BBB,AAA,01-JAN-2015\n")
    with pytest.raises(ValueError, match="circular"):
        load_symbol_changes(p)


def test_curated_requires_source_and_future_review(tmp_path):
    with pytest.raises(ValueError, match="source"):
        load_curated(curated_json(tmp_path, source_urls=[]), today=TODAY)
    with pytest.raises(ValueError, match="review"):
        load_curated(curated_json(tmp_path, review_by="2026-01-01"), today=TODAY)


def test_shipped_curated_table_is_valid_and_current():
    entries = load_curated()      # real file, real today: fails once review_by passes
    assert any(e.old_symbol == "TATAMOTORS" and set(e.successors) == {"TMPV", "TMCV"} for e in entries)
