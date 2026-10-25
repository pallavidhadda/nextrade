import pytest

from indiafacts.cli import main
from indiafacts.pipeline import AmbiguousSymbol, build_factset
from indiafacts.render import render
from tests.fakes import FakeClient
from tests.test_securitymaster import CSV

NS = dict(sleep=lambda s: None)


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "symbolchange.csv"
    p.write_text(CSV, encoding="utf-8")
    return p


def test_renamed_symbol_fetches_new_ticker_with_notice(csv_path):
    fs = build_factset("ZOMATO.NS", client=FakeClient(), symbol_changes=csv_path, **NS)
    assert fs.entity.ticker == "ETERNAL.NS"
    assert any("ZOMATO is now ETERNAL" in n for n in fs.notices)
    assert "NOTICES" in render(fs) and "ZOMATO is now ETERNAL" in render(fs)


def test_split_makes_no_vendor_call_and_lists_successors(csv_path):
    c = FakeClient()
    with pytest.raises(AmbiguousSymbol) as e:
        build_factset("TATAMOTORS.NS", client=c, symbol_changes=csv_path, **NS)
    assert c.calls == 0 and e.value.resolution.symbols == ["TMPV", "TMCV"]


def test_cli_split_exit_code_3_lists_successors(csv_path, capsys):
    code = main(["TATAMOTORS.NS", "--symbol-changes", str(csv_path)], client=FakeClient(), sleep=lambda s: None)
    err = capsys.readouterr().err
    assert code == 3 and "TMPV" in err and "TMCV" in err


def test_direct_symbol_unchanged(csv_path):
    fs = build_factset("ETERNAL.NS", client=FakeClient(), symbol_changes=csv_path, **NS)
    assert fs.entity.ticker == "ETERNAL.NS" and fs.notices == []


def test_never_changed_symbol_needs_no_notice_when_list_loaded(csv_path):
    fs = build_factset("RELIANCE.NS", client=FakeClient(), symbol_changes=csv_path, **NS)
    assert fs.notices == []


def test_no_list_loaded_is_said_plainly(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))          # no ~/.indiafacts/symbolchange.csv
    fs = build_factset("RELIANCE.NS", client=FakeClient(), **NS)
    assert any("symbol-change list not loaded" in n for n in fs.notices)


def test_empty_vendor_with_list_loaded_gives_explicit_reason(csv_path):
    fs = build_factset("NOSUCH.NS", client=FakeClient(stmt=None, info={}), symbol_changes=csv_path, **NS)
    assert fs.entity.resolution == "unresolved"
    assert "not in security master" in fs.entity.resolution_reason and "not found at Yahoo" in fs.entity.resolution_reason
