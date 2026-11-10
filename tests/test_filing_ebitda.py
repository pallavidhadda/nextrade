from decimal import Decimal

from indiafacts.analysis import prefer_sources
from indiafacts.pipeline import build_factset
from tests.fakes import FakeClient
from tests.test_pipeline import NS, filing  # noqa: F401


def test_quarterly_ebitda_from_filing_has_formula_and_beats_yahoo(filing):  # noqa: F811
    fs = build_factset("RELIANCE.NS", client=FakeClient(), filing_path=filing, **NS)
    [e] = [f for f in fs.facts if f.metric == "ebitda" and f.source == "computed:filing_ebitda"]
    assert e.value == Decimal("540670000000") and e.status == "ok" and e.period_type == "Q"
    assert len(e.related_fact_ids) == 3
    assert "profit before tax + finance costs + depreciation" in e.reason
    picked = [f for f in prefer_sources([f for f in fs.facts if f.metric == "ebitda" and f.period_type == "Q"])
              if f.period_end == e.period_end]
    assert [p.source for p in picked] == ["computed:filing_ebitda"]
