from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from indiafacts.fundamentals import annual_facts, holding_facts, is_lender, ratio_facts
from indiafacts.fundamentals_view import fundamentals_rows
from indiafacts.models import Entity, FactSet, PeriodType, Status

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)
YEARS = pd.to_datetime(["2026-03-31", "2025-03-31", "2024-03-31", "2023-03-31"])


def stmts(ebitda=(200, 180, 160, 140)):
    inc = pd.DataFrame({y: v for y, v in zip(YEARS, zip((1000, 900, 800, 700), (100, 90, 80, 70), ebitda, (150, 130, 120, 100), (-20, -20, -20, -20)))},
                       index=["Total Revenue", "Net Income Common Stockholders", "EBITDA", "EBIT", "Interest Expense"]) * 1.0
    bal = pd.DataFrame({y: v for y, v in zip(YEARS, zip((300,) * 4, (100,) * 4, (500,) * 4, (900,) * 4, (400,) * 4))},
                       index=["Total Debt", "Cash Cash Equivalents And Short Term Investments", "Stockholders Equity", "Total Assets", "Current Liabilities"]) * 1.0
    cf = pd.DataFrame({y: v for y, v in zip(YEARS, zip((160,) * 4, (-60,) * 4, (100,) * 4))},
                      index=["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"]) * 1.0
    return {"income": inc, "balance": bal, "cashflow": cf}


def factset(sector="Energy", industry="Oil & Gas", mcap=2000):
    e = Entity.from_ticker("ABC.NS").model_copy(update={"sector": sector, "industry": industry})
    facts = annual_facts("ABC.NS", stmts(), sector, industry, now=NOW)
    from indiafacts.models import Fact
    facts.append(Fact.make(entity_key="ABC.NS", metric="market_cap", value=Decimal(mcap), unit="INR", period_end=NOW.date(),
                           period_type=PeriodType.point, source="yahoo", retrieved_at=NOW))
    fs = FactSet(entity=e, facts=facts, retrieved_at=NOW)
    return fs.model_copy(update={"facts": facts + ratio_facts(fs, NOW)})


def val(fs, m):
    f = [x for x in fs.facts if x.metric == m][-1]
    return f.value, f.status


def test_year_figures_keep_source_row_and_distinct_names():
    fs = factset()
    f = [x for x in fs.facts if x.metric == "fy_free_cash_flow" and x.fiscal_label == "FY26"][0]
    assert f.value == Decimal("100.0") and f.period_type == PeriodType.FY and f.source_field == "Free Cash Flow"
    assert not any(x.metric == "net_income" for x in fs.facts)              # never collides with the quarterly metric


def test_ratios_are_computed_from_the_facts():
    fs = factset()
    assert round(float(val(fs, "fy_roce")[0]), 4) == round(150 / (900 - 400), 4)
    assert round(float(val(fs, "fy_net_debt_to_ebitda")[0]), 3) == round(200 / 200, 3)
    assert round(float(val(fs, "ev")[0])) == 2200 and round(float(val(fs, "ev_ebitda")[0]), 2) == 11.0
    assert round(float(val(fs, "fy_revenue_cagr_3y")[0]), 4) == round((1000 / 700) ** (1 / 3) - 1, 4)
    assert round(float(val(fs, "fy_fcf_yield")[0]), 3) == 0.05


def test_negative_start_makes_growth_unavailable_with_reason():
    st = stmts()
    st["income"].loc["Net Income Common Stockholders", YEARS[3]] = -5.0
    e = Entity.from_ticker("ABC.NS")
    fs = FactSet(entity=e, facts=annual_facts("ABC.NS", st, "Energy", None, NOW), retrieved_at=NOW)
    out = [f for f in ratio_facts(fs, NOW) if f.metric == "fy_net_income_cagr_3y"][0]
    assert out.status == Status.unavailable and "zero or negative" in out.reason


def test_missing_cell_is_unavailable_never_filled():
    st = stmts()
    st["cashflow"].loc["Free Cash Flow", YEARS[1]] = float("nan")
    fs = FactSet(entity=Entity.from_ticker("ABC.NS"), facts=annual_facts("ABC.NS", st, "Energy", None, NOW), retrieved_at=NOW)
    f = [x for x in fs.facts if x.metric == "fy_free_cash_flow" and x.period_end.year == 2025][0]
    assert f.status == Status.unavailable and f.value is None and f.reason


def test_lender_gets_its_own_metric_set_and_honest_gaps():
    assert is_lender("Financial Services", "Banks - Private")
    fs = factset("Financial Services", "Banks - Private")
    assert val(fs, "ev_ebitda")[1] == Status.unavailable and "lender" in [x for x in fs.facts if x.metric == "ev_ebitda"][0].reason
    rows = {r["metric"]: r for r in fundamentals_rows(fs)}
    assert rows["nim"]["display"] == "not available" and "presentation" in rows["nim"]["reason"]
    assert "fy_roce" not in rows and "ev_ebitda" not in rows
    assert round(float(val(fs, "fy_equity_multiplier")[0]), 2) == 1.8


def test_holding_is_unverified_proxy():
    f = holding_facts("ABC.NS", {"heldPercentInsiders": 0.5, "heldPercentInstitutions": None}, NOW)
    assert f[0].status == Status.unverified and "shareholding pattern" in f[0].reason
    assert f[1].status == Status.unavailable


def test_view_gives_plain_readings():
    rows = {r["metric"]: r for r in fundamentals_rows(factset())}
    assert rows["fy_net_debt_to_ebitda"]["reading"] == "low" and rows["fy_fcf_yield"]["reading"] == "moderate"


def test_optional_metrics_never_lower_coverage():
    from indiafacts.scoring import MetricSpec
    import indiafacts.scoring as sc
    cfg = sc.load_score_config(strict=False)
    opt = [m.id for m in cfg.metrics if m.optional]
    assert {"ev_ebitda", "fy_roce", "fy_fcf_yield"} <= set(opt)
    assert all(not m.optional for m in cfg.metrics if m.id in ("pe_ttm", "pb", "roe"))


def test_checklist_falls_back_to_last_financial_year_and_says_so():
    from indiafacts.checklist import checklist
    fs = factset()
    res = {c.id: c for c in checklist(fs)}
    assert res["earnings_growing"].result == "pass" and "last financial year" in res["earnings_growing"].display
    assert res["revenue_growing"].result == "pass"
    assert res["interest_cover"].result == "pass"                     # 150 / 20 = 7.5 times
