import re
from datetime import date
from decimal import Decimal

import pytest

from indiafacts.brain import Brain
from indiafacts.cli import main
from indiafacts.nsefiling import facts_from_nse_filing, merge_filings
from indiafacts.render import render
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
from tests.test_filing_versions import PRIOR_YEAR, REVISED
from tests.test_nsefiling import HTML, row


@pytest.fixture
def page(tmp_path):
    p = tmp_path / "orig.html"
    p.write_text(HTML, encoding="utf-8")
    return p


def test_fm1_filing_metadata_is_captured(page):
    fs = facts_from_nse_filing(page)
    [m] = fs.filings
    assert (m.document, m.filing_date, m.period_end, m.basis, m.audit_status, m.rounding, m.currency) == (
        "orig.html", date(2026, 7, 17), date(2026, 6, 30), "consolidated", "unaudited", "Lakhs", "INR")
    assert m.board_meeting_date == date(2026, 7, 17) and len(m.filing_id) == 16 and m.source_type == "nse_rendered_page"
    assert m.revision_note == "not stated on the page"


def test_fm2_every_figure_keeps_the_original_reported_number_unit_and_filing(page):
    fs = facts_from_nse_filing(page)
    ni = next(f for f in fs.facts if f.metric == "net_income")
    assert ni.reported_value == Decimal("2094600.00") and ni.reported_unit == "INR Lakhs" and ni.value == Decimal("209460000000.00")
    assert ni.audit_status == "unaudited" and ni.filing_id == fs.filings[0].filing_id and ni.concept == ""
    eps = next(f for f in fs.facts if f.metric == "eps_diluted")
    assert eps.reported_value == Decimal("15.48") and eps.reported_unit == "INR per share"
    seg = next(f for f in fs.facts if f.metric == "segment_revenue_retail")
    assert seg.dimension == "Retail" and seg.reported_value == Decimal("9040900.00")


def test_fm3_a_revision_remark_on_the_page_is_captured_verbatim(tmp_path):
    extra = HTML.replace("<table>", "<table>" + row("Whether the submission is a revision or correction", "Yes - revised for classification of other income"), 1)
    p = tmp_path / "rev.html"
    p.write_text(extra, encoding="utf-8")
    assert "revised for classification of other income" in facts_from_nse_filing(p).filings[0].revision_note


def test_fm4_merge_keeps_every_filing_record_in_filing_date_order(tmp_path):
    paths = []
    for name, body in (("a", HTML), ("b", REVISED), ("c", PRIOR_YEAR)):
        p = tmp_path / f"{name}.html"
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    merged, _ = merge_filings([facts_from_nse_filing(p) for p in paths])
    assert [m.document for m in merged.filings] == ["c.html", "a.html", "b.html"]
    assert [m.filing_date for m in merged.filings] == [date(2025, 7, 18), date(2026, 7, 17), date(2026, 9, 5)]


def test_fm5_brain_persists_filing_records(page, tmp_path):
    from datetime import datetime, timezone

    fs = facts_from_nse_filing(page)
    b = Brain(tmp_path / "b.db")
    b.record_run(fs, None, None, datetime(2026, 10, 1, tzinfo=timezone.utc))
    rows = b.filings("RELIANCE.NS")
    assert len(rows) == 1 and rows[0]["document"] == "orig.html" and rows[0]["audit_status"] == "unaudited"
    b.record_run(fs, None, None, datetime(2026, 10, 2, tzinfo=timezone.utc))
    assert len(b.filings("RELIANCE.NS")) == 1                      # same filing, stored once


def test_fm6_report_lists_the_filings_used(page, capsys, tmp_path):
    code = main(["RELIANCE.NS", "--no-prices", "--no-tej", "--no-remember", "--filing", str(page)],
                client=FakeClient(stmt=QUARTERLY, info=INFO), sleep=lambda s: None)
    out = capsys.readouterr().out
    block = out.split("FILINGS USED")[1].split("\n\n")[0]
    assert code == 0 and "orig.html" in block and "2026-07-17" in block and "unaudited" in block and "consolidated" in block
    assert "revision: not stated on the page" in block
