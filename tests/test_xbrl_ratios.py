from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from indiafacts.models import PeriodType
from indiafacts.xbrl import facts_from_nse_xbrl

FIX = Path(__file__).parent / "fixtures" / "nse_ifr_cons_RELIANCE_2026Q2.xml"


def _q(fs, metric):
    return [f for f in fs.facts if f.metric == metric and f.period_type == PeriodType.Q][0]


def test_filing_ratios_are_the_published_figures_not_hundredths():
    fs = facts_from_nse_xbrl(FIX, datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert _q(fs, "debt_equity_ratio").value == Decimal("0.41")                   # file stores 0.0041; results page shows 0.41
    assert _q(fs, "debt_service_coverage_ratio").value == Decimal("3.52")
    assert _q(fs, "interest_service_coverage_ratio").value == Decimal("5.55")
    assert _q(fs, "debt_equity_ratio").reported_value == Decimal("0.0041")        # the raw file value stays visible


def test_eps_and_money_are_not_rescaled():
    fs = facts_from_nse_xbrl(FIX, datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert _q(fs, "finance_costs" if False else "interest_expense").value == Decimal("84810000000")
    assert _q(fs, "eps_diluted").unit == "INR_per_share" and abs(_q(fs, "eps_diluted").value) < 100


def _variant(tmp_path, repl):
    text = FIX.read_text(encoding="utf-8")
    for a, b in repl:
        assert a in text, a
        text = text.replace(a, b)
    out = tmp_path / FIX.name
    out.write_text(text, encoding="utf-8")
    return out


def test_filer_storing_debt_equity_as_published_is_not_scaled(tmp_path):
    p = _variant(tmp_path, [("0.0041</in-capmkt:DebtEquityRatio>", "1.80</in-capmkt:DebtEquityRatio>")])
    fs = facts_from_nse_xbrl(p, datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert _q(fs, "debt_equity_ratio").value == Decimal("1.80")                    # raw 1.80 is already the published figure
    assert _q(fs, "interest_service_coverage_ratio").value == Decimal("5.55")      # coverage ratios still follow the hundredths rule


def test_zero_coverage_ratio_is_not_a_figure(tmp_path):
    p = _variant(tmp_path, [("0.0555</in-capmkt:InterestServiceCoverageRatio>", "0</in-capmkt:InterestServiceCoverageRatio>")])
    fs = facts_from_nse_xbrl(p, datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert [f.value for f in fs.facts if f.metric == "interest_service_coverage_ratio" and f.period_type == PeriodType.Q] == []
