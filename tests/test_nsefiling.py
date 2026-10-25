"""NSE 'IndAS Details' filing parser. Offline tests use a synthetic page with the real page's structure;
the real-file test reads samples/ (git-ignored, NSE redistribution terms unknown) and skips if absent."""
from datetime import date
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path

import pytest

from indiafacts.nsefiling import facts_from_nse_filing

URL = "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_175608_17072026195004_iXBRL_WEB.html"


def row(*cells):
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


HTML = "<html><body><table>" + "".join([
    row("Scrip Code", "500325"), row("NSE Symbol", "RELIANCE"), row("ISIN", "INE002A01018"),
    row("Name of company", "RELIANCE INDUSTRIES LIMITED"),
    row("Date of board meeting when results were approved", "17-07-2026"),
    row("Description of presentation currency", "INR"), row("Level of rounding used in financial results", "Lakhs"),
    row("Reporting Type", "Quarterly"), row("Reporting Quarter", "First quarter"),
    row("Nature of report standalone or consolidated", "Consolidated"),
    row("Whether results are audited or unaudited for the quarter ended", "Unaudited"),
    row("Particulars", "3 months/ 6 months ended (dd-mm-yyyy)", "Year to date figures for current period ended (dd-mm-yyyy)"),
    row("A", "Date of start of reporting period", "01-04-2026", "01-04-2026"),
    row("B", "Date of end of reporting period", "30-06-2026", "30-06-2026"),
    row("1", "Income"),
    row("Revenue from operations", "3,11,85,000.00", "3,11,85,000.00"),
    row("(c)", "Changes in inventories of finished goods, work-in-progress and stock-in-trade", "(1,32,600.00)", "(1,32,600.00)"),
    row("(e)", "Finance costs", "8,33,700.00", "8,33,700.00"),
    row("(f)", "Depreciation, depletion and amortisation expense", "15,10,000.00", "15,10,000.00"),
    row("5", "Total profit before tax", "30,63,000.00", "30,63,000.00"),
    row("17", "Other comprehensive income net of taxes", "3,26,700.00", "3,26,700.00"),
    row("Profit or loss, attributable to owners of parent", "20,94,600.00", "20,94,600.00"),
    row("Diluted earnings (loss) per share from continuing and discontinued operations", "15.48", "15.48"),
    row("24", "Debt equity ratio", "0.400", "0.400"),
    row("Segment Revenue (Income)"),
    row("3", "Retail", "90,40,900.00", "90,40,900.00"),
    row("Total Segment Revenue", "3,76,61,400.00", "3,76,61,400.00"),
    row("Revenue from operations", "3,40,25,700.00", "3,40,25,700.00"),
    row("Segment Result"),
    row("3", "Retail", "4,52,900.00", "4,52,900.00"),
]) + "</table></body></html>"


@pytest.fixture
def html_path(tmp_path):
    p = tmp_path / "filing.html"
    p.write_text(HTML, encoding="utf-8")
    return p


def by(fs, metric):
    return [f for f in fs.facts if f.metric == metric]


def test_identity_from_filing(html_path):
    e = facts_from_nse_filing(html_path).entity
    assert (e.ticker, e.nse_symbol.value, e.bse_code.value, e.isin.value) == (
        "RELIANCE.NS", "RELIANCE", "500325", "INE002A01018")
    assert e.name == "RELIANCE INDUSTRIES LIMITED" and e.isin.status == "ok"


def test_period_basis_and_label(html_path):
    f = by(facts_from_nse_filing(html_path), "revenue")[0]
    assert (f.period_end, f.period_start, f.period_type) == (date(2026, 6, 30), date(2026, 4, 1), "Q")
    assert f.fiscal_label == "Q1 FY27" and f.basis == "consolidated" and f.source == "nse_filing"


def test_lakh_scaling_and_indian_grouping(html_path):
    fs = facts_from_nse_filing(html_path)
    assert by(fs, "revenue")[0].value == Decimal("3118500000000")
    assert by(fs, "net_income")[0].value == Decimal("209460000000")
    assert by(fs, "interest_expense")[0].value == Decimal("83370000000")
    assert by(fs, "profit_before_tax")[0].value == Decimal("306300000000")


def test_parenthesised_negative(html_path):
    assert by(facts_from_nse_filing(html_path), "change_in_inventories")[0].value == Decimal("-13260000000")


def test_ratios_and_eps_not_scaled(html_path):
    fs = facts_from_nse_filing(html_path)
    assert by(fs, "eps_diluted")[0].value == Decimal("15.48") and by(fs, "eps_diluted")[0].unit == "INR_per_share"
    assert by(fs, "debt_equity_ratio")[0].value == Decimal("0.400") and by(fs, "debt_equity_ratio")[0].unit == "ratio"


def test_filing_date_from_board_meeting_when_no_url(html_path):
    f = by(facts_from_nse_filing(html_path), "revenue")[0]
    assert f.available_from == date(2026, 7, 17) and f.availability_kind == "filed"


def test_segments_use_segment_section_not_pl_row(html_path):
    fs = facts_from_nse_filing(html_path)
    assert by(fs, "segment_revenue_retail")[0].value == Decimal("904090000000")
    assert by(fs, "segment_result_retail")[0].value == Decimal("45290000000")
    assert len(by(fs, "revenue")) == 1  # segment-table "Revenue from operations" is not the P&L line


def test_missing_label_gives_no_fact_not_a_crash(html_path):
    assert by(facts_from_nse_filing(html_path), "ebitda") == []


def test_mhtml_container_and_url_timestamp(tmp_path):
    msg = EmailMessage()
    msg["Subject"] = "IndAS Details"
    msg["Snapshot-Content-Location"] = URL
    msg.set_content("x")
    msg.add_alternative(HTML, subtype="html")
    p = tmp_path / "IndAS Details.mhtml"
    p.write_bytes(bytes(msg))
    f = by(facts_from_nse_filing(p), "revenue")[0]
    assert f.available_from == date(2026, 7, 17)


def test_garbage_file_raises_value_error(tmp_path):
    p = tmp_path / "x.html"
    p.write_text("<html><body>nothing here</body></html>")
    with pytest.raises(ValueError):
        facts_from_nse_filing(p)


_found = sorted((Path(__file__).resolve().parents[1] / "samples").glob("IndAS Details.*"))
REAL = _found[0] if _found else Path("/nonexistent")


@pytest.mark.skipif(not REAL.exists(), reason="real NSE sample not present")
def test_real_reliance_q1_fy27_matches_yahoo_exactly():
    fs = facts_from_nse_filing(REAL)
    assert by(fs, "net_income")[0].value == Decimal("209460000000")      # Yahoo: 209460000000.0
    assert by(fs, "interest_expense")[0].value == Decimal("83370000000")  # Yahoo: 83370000000.0
    assert by(fs, "eps_diluted")[0].value == Decimal("15.48")
    assert by(fs, "revenue")[0].value == Decimal("3118500000000")
    assert fs.entity.isin.value == "INE002A01018"
