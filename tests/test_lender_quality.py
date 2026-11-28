"""Lender asset quality from the official filing: gross and net NPA, CET1, net interest income; lender checklist."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from indiafacts import nseapi
from indiafacts.checklist import checklist
from indiafacts.fundamentals import ratio_facts
from indiafacts.models import Entity, FactSet, PeriodType
from indiafacts.xbrl import facts_from_nse_xbrl
from tests.test_nseapi import FakeNse

FX = Path(__file__).parent / "fixtures"
CONS = (FX / "nse_ifr_bank_HDFCBANK_2026Q2.xml").read_bytes()


def standalone_bytes() -> bytes:
    b = CONS.replace(b">Consolidated<", b">Standalone<")
    for concept, v in ((b"PercentageOfGrossNpa", b"0.0111"), (b"PercentageOfNpa", b"0.0037"), (b"CET1Ratio", b"0.1887")):
        b = b.replace(b'<in-capmkt:' + concept + b' contextRef="OneD" decimals="INF" unitRef="pure">0<',
                      b'<in-capmkt:' + concept + b' contextRef="OneD" decimals="INF" unitRef="pure">' + v + b'<')
    return b


def parse(tmp_path, body: bytes, name="INTEGRATED_FILING_BANKING_1740913_17102026054812_WEB.xml"):
    p = tmp_path / name
    p.write_bytes(body)
    return {f.metric: f for f in facts_from_nse_xbrl(p).facts if f.period_type in (PeriodType.point, PeriodType.Q)}


def test_standalone_bank_filing_gives_asset_quality(tmp_path):
    m = parse(tmp_path, standalone_bytes())
    assert float(m["gross_npa_ratio"].value) == pytest.approx(0.0111)
    assert float(m["net_npa_ratio"].value) == pytest.approx(0.0037)
    assert float(m["cet1_ratio"].value) == pytest.approx(0.1887)
    assert m["gross_npa_ratio"].period_end == date(2026, 9, 30) and m["gross_npa_ratio"].basis.value == "standalone"


def test_consolidated_zeros_are_not_figures(tmp_path):
    """Consolidated bank filings carry 0 in the NPA and CET1 fields; 0 there means 'not reported', never a clean book."""
    m = parse(tmp_path, CONS)
    assert "gross_npa_ratio" not in m and "net_npa_ratio" not in m and "cet1_ratio" not in m


def test_net_interest_income_and_its_ratio_to_assets(tmp_path):
    m = parse(tmp_path, CONS)
    nii = 951316300000 - 506674300000
    assert float(m["net_interest_income"].value) == nii
    assert float(m["nii_to_assets"].value) == pytest.approx(nii * 4 / 51658415800000, abs=1e-6)
    assert "annualised" in m["nii_to_assets"].source_field


BANK_LIST = {"data": [
    {"qe_Date": "30-SEP-2026", "consolidated": "Consolidated", "broadcast_Date": "17-Oct-2026 05:48:12", "audited": "Un-Audited",
     "xbrl": "https://nsearchives.nseindia.in/corporate/xbrl/INTEGRATED_FILING_BANKING_1740913_17102026054812_WEB.xml"},
    {"qe_Date": "30-SEP-2026", "consolidated": "Standalone", "broadcast_Date": "17-Oct-2026 05:48:06", "audited": "Un-Audited",
     "xbrl": "https://nsearchives.nseindia.in/corporate/xbrl/INTEGRATED_FILING_BANKING_1740912_17102026054806_WEB.xml"},
]}


@pytest.fixture
def bank_api(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIAFACTS_NSE_API", "1")
    op = FakeNse({"integrated-filing-results": json.dumps(BANK_LIST).encode(), "corporates-financial-results": b"[]",
                  "INTEGRATED_FILING_BANKING_1740913": CONS, "INTEGRATED_FILING_BANKING_1740912": standalone_bytes()})
    return nseapi.NseApi(opener=op, cache=tmp_path, sleep=lambda s: None, clock=lambda: 1000.0)


def test_bank_results_add_asset_quality_from_the_standalone_filing(bank_api):
    parsed, notes = bank_api.quarterly_filings("HDFCBANK")
    bases = [fs.facts[0].basis.value for fs in parsed]
    assert bases.count("consolidated") == 1 and bases.count("standalone") == 1
    extra = [fs for fs in parsed if fs.facts[0].basis.value == "standalone"][0]
    assert {f.metric for f in extra.facts} == {"gross_npa_ratio", "net_npa_ratio", "cet1_ratio"}
    assert any("standalone" in n and "asset quality" in n for n in notes)


def test_non_bank_results_fetch_no_standalone_file(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIAFACTS_NSE_API", "1")
    op = FakeNse()
    a = nseapi.NseApi(opener=op, cache=tmp_path, sleep=lambda s: None, clock=lambda: 1000.0)
    parsed, _ = a.quarterly_filings("RELIANCE")
    assert parsed and all(fs.facts[0].basis.value == "consolidated" for fs in parsed)


def _lender_fs(extra_facts=()) -> FactSet:
    ent = Entity.from_ticker("HDFCBANK.NS").model_copy(update={"sector": "Financial Services", "industry": "Banks - Regional"})
    return FactSet(entity=ent, facts=list(extra_facts), retrieved_at=datetime(2026, 11, 16, tzinfo=timezone.utc))


def test_lender_checklist_drops_debt_and_interest_cover_and_adds_bad_loans(tmp_path):
    facts = list(parse(tmp_path, standalone_bytes()).values())
    ids = {r.id: r for r in checklist(_lender_fs(facts))}
    assert "debt_moderate" not in ids and "interest_cover" not in ids
    assert ids["bad_loans_low"].result == "pass" and ids["bad_loans_low"].group == "Balance sheet"


def test_non_lender_checklist_unchanged():
    fs = FactSet(entity=Entity.from_ticker("TCS.NS"), facts=[], retrieved_at=datetime(2026, 11, 16, tzinfo=timezone.utc))
    ids = [r.id for r in checklist(fs)]
    assert "debt_moderate" in ids and "interest_cover" in ids and "bad_loans_low" not in ids


def test_ratio_facts_do_not_blank_filed_asset_quality(tmp_path):
    from tests.factories import fact

    filed = list(parse(tmp_path, standalone_bytes()).values())
    fy = [fact(date(2026, 3, 31), "fy_net_income", "100", "FY"), fact(date(2026, 3, 31), "fy_equity", "1000", "FY"),
          fact(date(2026, 3, 31), "fy_total_assets", "10000", "FY")]
    out = {f.metric: f for f in ratio_facts(_lender_fs(filed + fy))}
    assert "gross_npa_ratio" not in out and "nii_to_assets" not in out      # filed figures stand; no "not in free data" stub
    assert out["fy_equity_multiplier"].value is not None


def test_ratio_facts_stub_when_no_filing(tmp_path):
    from tests.factories import fact

    fy = [fact(date(2026, 3, 31), "fy_net_income", "100", "FY"), fact(date(2026, 3, 31), "fy_equity", "1000", "FY")]
    out = {f.metric: f for f in ratio_facts(_lender_fs(fy))}
    assert out["gross_npa_ratio"].value is None and "filing" in out["gross_npa_ratio"].reason


def test_bad_loans_phrasing(tmp_path):
    from indiafacts.checklist import point_text, watch_text

    facts = list(parse(tmp_path, standalone_bytes()).values())
    r = [x for x in checklist(_lender_fs(facts)) if x.id == "bad_loans_low"][0]
    assert r.display == "1.1%" and point_text(r) == "Gross bad loans are 1.1% of loans, under 3%."
    assert "below 3%" in watch_text(r)
