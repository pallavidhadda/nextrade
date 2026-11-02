from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from indiafacts.xbrl import facts_from_nse_xbrl

ROOT = Path(__file__).resolve().parents[1]
NS = ('xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
      'xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin" xmlns:link="http://www.xbrl.org/2003/linkbase" '
      'xmlns:xlink="http://www.w3.org/1999/xlink"')


def ctx(cid, start=None, end=None, instant=None, dim=None):
    per = f"<xbrli:instant>{instant}</xbrli:instant>" if instant else f"<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>"
    scen = f'<xbrli:scenario><xbrldi:explicitMember dimension="in-bse-fin:SegAxis">in-bse-fin:{dim}</xbrldi:explicitMember></xbrli:scenario>' if dim else ""
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/NSESymbol">ABC</xbrli:identifier>'
            f'</xbrli:entity><xbrli:period>{per}</xbrli:period>{scen}</xbrli:context>')


def fact(name, c, v, unit=None):
    u = f' unitRef="{unit}"' if unit else ""
    return f'<in-bse-fin:{name} contextRef="{c}"{u}>{v}</in-bse-fin:{name}>'


def doc(extra="", nature="Consolidated", audited="Audited", doctype=""):
    body = "".join([
        ctx("OneD", "2024-01-01", "2024-03-31"), ctx("FourD", "2024-01-01", "2024-03-31"), ctx("OneI", instant="2024-03-31"),
        ctx("OneSeg01D", "2024-01-01", "2024-03-31", dim="Seg1Member"),
        fact("ScripCode", "OneD", "500001"), fact("Symbol", "OneD", "ABC"), fact("NameOfTheCompany", "OneD", "ABC Ltd"),
        fact("NatureOfReportStandaloneConsolidated", "OneD", nature), fact("WhetherResultsAreAuditedOrUnaudited", "OneD", audited),
        fact("LevelOfRoundingUsedInFinancialStatements", "OneD", "Crores"), fact("DescriptionOfPresentationCurrency", "OneD", "INR"),
        fact("RevenueFromOperations", "OneD", "1000000000000.00", "INR"), fact("RevenueFromOperations", "FourD", "4000000000000.00", "INR"),
        fact("ProfitLossForPeriod", "OneD", "100000000000.00", "INR"), fact("ProfitOrLossAttributableToOwnersOfParent", "OneD", "90000000000.00", "INR"),
        fact("FinanceCosts", "OneD", "20000000000.00", "INR"),
        fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "OneD", "12.50"),
        fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "FourD", "49.00"),
        fact("CashFlowsFromUsedInOperatingActivities", "FourD", "700000000000.00", "INR"),
        fact("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "FourD", "500000000000.00", "INR"),
        fact("Assets", "OneI", "9000000000000.00", "INR"), fact("Equity", "OneI", "5000000000000.00", "INR"),
        fact("RevenueFromOperations", "OneSeg01D", "123.00", "INR"),             # dimensional: must be ignored
        extra])
    return f'<?xml version="1.0" encoding="UTF-8"?>{doctype}<xbrli:xbrl {NS}>{body}</xbrli:xbrl>'


def write(tmp_path, text, name="INDAS_100_200_22042024074028.xml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def by_metric(fs, metric, ptype=None):
    return [f for f in fs.facts if f.metric == metric and (ptype is None or f.period_type == ptype)]


def test_x1_quarter_facts_are_ok_in_rupees_with_provenance(tmp_path):
    fs = facts_from_nse_xbrl(write(tmp_path, doc()))
    rev = by_metric(fs, "revenue", "Q")[0]
    assert rev.value == Decimal("1000000000000") and rev.unit == "INR" and rev.status == "ok"
    assert rev.period_start == date(2024, 1, 1) and rev.period_end == date(2024, 3, 31) and rev.fiscal_label == "Q4 FY24"
    assert rev.source == "nse_xbrl" and rev.basis == "consolidated" and rev.audit_status == "audited"
    assert rev.available_from == date(2024, 4, 22) and rev.availability_kind == "filed"
    assert "in-bse-fin:RevenueFromOperations" in rev.evidence and "OneD" in rev.evidence
    assert fs.entity.nse_symbol.value == "ABC" and fs.entity.bse_code.value == "500001" and fs.entity.name == "ABC Ltd"
    assert fs.entity.isin.value is None and "not in" in fs.entity.isin.reason


def test_x2_net_income_is_owners_share_and_total_is_kept_apart(tmp_path):
    fs = facts_from_nse_xbrl(write(tmp_path, doc()))
    assert by_metric(fs, "net_income", "Q")[0].value == Decimal("90000000000")
    assert by_metric(fs, "net_income_total", "Q")[0].value == Decimal("100000000000")
    assert by_metric(fs, "interest_expense", "Q")[0].value == Decimal("20000000000")
    assert by_metric(fs, "eps_basic", "Q")[0].value == Decimal("12.50") and by_metric(fs, "eps_basic", "Q")[0].unit == "INR_per_share"


def test_x3_standalone_uses_profit_for_period_as_net_income(tmp_path):
    text = doc(nature="Standalone").replace(fact("ProfitOrLossAttributableToOwnersOfParent", "OneD", "90000000000.00", "INR"), "")
    fs = facts_from_nse_xbrl(write(tmp_path, text))
    assert by_metric(fs, "net_income", "Q")[0].value == Decimal("100000000000")
    assert by_metric(fs, "net_income", "Q")[0].basis == "standalone"


def test_x4_year_values_are_unverified_because_the_file_repeats_quarter_dates(tmp_path):
    fs = facts_from_nse_xbrl(write(tmp_path, doc()))
    y = by_metric(fs, "revenue", "FY")[0]
    assert y.status == "unverified" and "FourD" in y.reason and y.value == Decimal("4000000000000")
    assert y.period_start == date(2023, 4, 1) and y.period_end == date(2024, 3, 31) and y.fiscal_label == "FY24"


def test_x5_cash_flow_and_balance_sheet_are_read_and_dimensional_values_ignored(tmp_path):
    fs = facts_from_nse_xbrl(write(tmp_path, doc()))
    assert by_metric(fs, "operating_cash_flow")[0].value == Decimal("700000000000")
    assert by_metric(fs, "capex_ppe")[0].value == Decimal("500000000000")
    assert by_metric(fs, "total_assets")[0].value == Decimal("9000000000000") and by_metric(fs, "total_assets")[0].period_type == "point"
    assert all(f.value != Decimal("123") for f in fs.facts)


def test_x6_filing_meta_and_id_are_recorded(tmp_path):
    fs = facts_from_nse_xbrl(write(tmp_path, doc()))
    m = fs.filings[0]
    assert m.source_type == "nse_xbrl_instance" and m.basis == "consolidated" and m.audit_status == "audited"
    assert m.filing_date == date(2024, 4, 22) and m.period_end == date(2024, 3, 31) and m.rounding == "Crores"
    assert all(f.filing_id == m.filing_id for f in fs.facts)


def test_x7_unsafe_or_wrong_files_are_refused(tmp_path):
    with pytest.raises(ValueError, match="DOCTYPE"):
        facts_from_nse_xbrl(write(tmp_path, doc(doctype='<!DOCTYPE x [<!ENTITY a "b">]>')))
    with pytest.raises(ValueError, match="not an NSE XBRL"):
        facts_from_nse_xbrl(write(tmp_path, "<root/>"))
    with pytest.raises(ValueError, match="currency"):
        facts_from_nse_xbrl(write(tmp_path, doc().replace(">INR<", ">USD<")))


@pytest.mark.skipif(not list((ROOT / "samples").glob("INDAS_104634_*.xml")), reason="real NSE sample not present (git-ignored)")
def test_x8_real_reliance_consolidated_file():
    p = next((ROOT / "samples").glob("INDAS_104634_*.xml"))
    fs = facts_from_nse_xbrl(p)
    rev_q = by_metric(fs, "revenue", "Q")[0]
    assert rev_q.value == Decimal("2407150000000") and rev_q.basis == "consolidated"
    assert by_metric(fs, "eps_basic", "FY")[0].value == Decimal("102.90")
    assert by_metric(fs, "total_assets")[0].value > 0


def test_x9_cli_accepts_an_xbrl_file_and_reports_its_source(tmp_path, capsys):
    from indiafacts.cli import main
    from tests.fakes import FakeClient
    from tests.fixtures.reliance_quarterly import INFO, QUARTERLY

    p = write(tmp_path, doc())
    code = main(["ABC.NS", "--filing", str(p), "--no-tej", "--no-prices", "--no-remember"],
                client=FakeClient(stmt=QUARTERLY, info=INFO), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0 and "nse_xbrl" in out and "INDAS_100_200_22042024074028.xml" in out
