import re

from indiafacts.cli import main
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY

CSV = """Company Name,Industry,Symbol,Series,ISIN Code
Reliance Industries Ltd.,Oil Gas & Consumable Fuels,RELIANCE,EQ,INE002A01018
BPCL Ltd.,Oil Gas & Consumable Fuels,BPCL,EQ,INE000000001
IOC Ltd.,Oil Gas & Consumable Fuels,IOC,EQ,INE000000002
ONGC Ltd.,Oil Gas & Consumable Fuels,ONGC,EQ,INE000000003
GAIL Ltd.,Oil Gas & Consumable Fuels,GAIL,EQ,INE000000004
OIL Ltd.,Oil Gas & Consumable Fuels,OIL,EQ,INE000000005
HDFC Bank Ltd.,Financial Services,HDFCBANK,EQ,INE000000006
SBI Ltd.,Financial Services,SBIN,EQ,INE000000007
TCS Ltd.,Information Technology,TCS,EQ,INE000000008
"""


def run(tmp_path, capsys, *extra, target="RELIANCE.NS"):
    c = tmp_path / "ind.csv"
    c.write_text(CSV, encoding="utf-8")
    info = {**INFO, "sector": "Energy", "industry": "Refining"}
    code = main([target, "--score", "--no-prices", "--no-tej", "--no-remember", *extra, "--universe", str(c)],
                client=FakeClient(stmt=QUARTERLY, info=info), sleep=lambda s: None)
    o = capsys.readouterr()
    return code, o.out, o.err


def test_sp1_sector_pool_loads_only_the_targets_industry_group(tmp_path, capsys):
    code, out, err = run(tmp_path, capsys, "--sector-pool")
    loaded = re.findall(r"^\[\d+/(\d+)\] (\S+)", err, re.M)
    assert code == 0 and {t for _, t in loaded} == {"BPCL.NS", "IOC.NS", "ONGC.NS", "GAIL.NS", "OIL.NS"}      # the target is already in hand
    assert "NSE industry group 'Oil Gas & Consumable Fuels'" in out and "inside 6 companies" in out


def test_sp2_without_the_flag_the_whole_file_is_the_pool(tmp_path, capsys):
    code, out, err = run(tmp_path, capsys)
    assert "inside 9 companies" in out


def test_sp3_target_missing_from_the_index_file_is_a_clear_error(tmp_path, capsys):
    code, out, err = run(tmp_path, capsys, "--sector-pool", target="NOSUCH.NS")
    assert code == 2 and "not in the index file" in err


def test_sp4_sector_pool_needs_an_index_csv(tmp_path, capsys):
    p = tmp_path / "plain.txt"
    p.write_text("RELIANCE.NS\nTCS.NS\n")
    code = main(["RELIANCE.NS", "--score", "--sector-pool", "--universe", str(p), "--no-prices", "--no-tej", "--no-remember"],
                client=FakeClient(stmt=QUARTERLY, info=INFO), sleep=lambda s: None)
    assert code == 2 and "needs an NSE index CSV" in capsys.readouterr().err


def test_sp5_small_group_still_lists_peers_but_says_the_score_pool_is_small(tmp_path, capsys):
    c = tmp_path / "ind.csv"
    c.write_text(CSV, encoding="utf-8")
    info = {**INFO, "sector": "Energy", "industry": "Refining"}
    code = main(["HDFCBANK.NS", "--score", "--sector-pool", "--universe", str(c), "--no-prices", "--no-tej", "--no-remember"],
                client=FakeClient(stmt=QUARTERLY, info=info), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0 and "inside 2 companies" in out and "universe too small" in out
