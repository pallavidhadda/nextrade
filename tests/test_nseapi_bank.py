from pathlib import Path

from indiafacts.xbrl import facts_from_nse_xbrl

FX = Path(__file__).parent / "fixtures"


def test_xbrl_parser_reads_bank_filings(tmp_path):
    real = tmp_path / "INTEGRATED_FILING_BANKING_1740913_17102026054812_WEB.xml"
    real.write_bytes((FX / "nse_ifr_bank_HDFCBANK_2026Q2.xml").read_bytes())
    m = {(f.metric, f.period_type.value): f for f in facts_from_nse_xbrl(real).facts}
    assert float(m[("net_income", "Q")].value) == 207000300000.0 and float(m[("eps_diluted", "Q")].value) == 13.41
    assert float(m[("interest_expense", "Q")].value) == 506674300000.0 and ("revenue", "Q") not in m
