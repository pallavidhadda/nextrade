import pytest

from indiafacts.cli import main
from indiafacts.universe import read_pool
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY

NSE_CSV = """Company Name,Industry,Symbol,Series,ISIN Code
Reliance Industries Ltd.,Oil Gas & Consumable Fuels,RELIANCE,EQ,INE002A01018
Bharat Petroleum Corporation Ltd.,Oil Gas & Consumable Fuels,BPCL,EQ,INE029A01011
Indian Oil Corporation Ltd.,Oil Gas & Consumable Fuels,IOC,EQ,INE242A01010
Oil & Natural Gas Corporation Ltd.,Oil Gas & Consumable Fuels,ONGC,EQ,INE213A01029
Tata Motors Ltd.,Capital Goods,TMCV,EQ,INE1TAE01010
Mahindra & Mahindra Ltd.,Automobile and Auto Components,M&M,EQ,INE101A01026
"""


def test_read_pool_parses_nse_index_csv_with_labels(tmp_path):
    p = tmp_path / "ind_nifty500list.csv"
    p.write_text(NSE_CSV, encoding="utf-8")
    pool = read_pool(p)
    assert pool.tickers[:2] == ["RELIANCE.NS", "BPCL.NS"] and "M&M.NS" in pool.tickers
    lab = pool.labels["RELIANCE.NS"]
    assert (lab["industry"], lab["isin"], lab["name"]) == ("Oil Gas & Consumable Fuels", "INE002A01018", "Reliance Industries Ltd.")
    assert pool.kind == "nse_index_csv"


def test_read_pool_still_reads_plain_ticker_files(tmp_path):
    p = tmp_path / "u.txt"
    p.write_text("# c\nRELIANCE.NS\nTCS.NS\n")
    pool = read_pool(p)
    assert pool.tickers == ["RELIANCE.NS", "TCS.NS"] and pool.labels == {} and pool.kind == "ticker_list"


def test_index_csv_with_missing_columns_is_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("Company Name,Symbol\nX,XXX\n")
    with pytest.raises(ValueError, match="Industry"):
        read_pool(p)


def test_nse_labels_drive_peer_tiers_and_isin(tmp_path, capsys):
    p = tmp_path / "ind_nifty500list.csv"
    p.write_text(NSE_CSV, encoding="utf-8")
    info = {**INFO, "sector": "Energy", "industry": "Something Else"}        # Yahoo labels must not decide the group
    code = main(["RELIANCE.NS", "--score", "--universe", str(p), "--no-prices", "--no-tej"],
                client=FakeClient(stmt=QUARTERLY, info=info), sleep=lambda s: None)
    out = capsys.readouterr().out
    peers = out.split("PEERS")[1].split("DATA QUALITY")[0]
    assert code == 0 and "BPCL.NS" in peers and "IOC.NS" in peers and "ONGC.NS" in peers
    assert "M&M.NS" not in peers and "TMCV.NS" not in peers
    assert "ISIN INE002A01018" in out.split("PROFILE")[0] or "INE002A01018" in out
