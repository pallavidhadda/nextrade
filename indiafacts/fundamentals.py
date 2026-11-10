"""Annual statements (income, balance sheet, cash flow) from Yahoo, and the ratios computed from them.

Fills the gaps the quarterly feed leaves: year figures, free cash flow, net debt, EV/EBITDA, capital returns,
multi-year growth. Every figure keeps its source row. Lenders (banks, NBFCs) get a different, honest metric set:
debt is their raw material, so EBITDA, EV and cash flow are marked not applicable instead of being computed badly.
Metric names carry a `fy_` prefix so a year figure can never be mistaken for a quarter.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd

from indiafacts.availability import available_from
from indiafacts.calendar import fiscal_label
from indiafacts.models import AvailabilityKind, Fact, FactSet, PeriodType, Status

SOURCE = "yahoo"
COMPUTED = "computed:fundamentals"

# metric -> (statement, Yahoo row candidates in order of preference)
ROWS = {
    "fy_revenue": ("income", ("Total Revenue", "Operating Revenue")),
    "fy_net_income": ("income", ("Net Income Common Stockholders", "Net Income")),
    "fy_ebitda": ("income", ("EBITDA", "Normalized EBITDA")),
    "fy_ebit": ("income", ("EBIT", "Operating Income")),
    "fy_interest_expense": ("income", ("Interest Expense",)),
    "fy_total_debt": ("balance", ("Total Debt",)),
    "fy_cash": ("balance", ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents")),
    "fy_equity": ("balance", ("Stockholders Equity", "Common Stock Equity")),
    "fy_total_assets": ("balance", ("Total Assets",)),
    "fy_current_liabilities": ("balance", ("Current Liabilities",)),
    "fy_operating_cash_flow": ("cashflow", ("Operating Cash Flow",)),
    "fy_capex": ("cashflow", ("Capital Expenditure",)),
    "fy_free_cash_flow": ("cashflow", ("Free Cash Flow",)),
}
LENDER_WORDS = ("bank", "financial", "nbfc", "credit", "insurance", "lending", "capital markets")
LENDER_NOT_APPLICABLE = ("fy_ebitda", "fy_ebit", "fy_current_liabilities", "fy_free_cash_flow",
                         "fy_operating_cash_flow", "fy_capex")
LENDER_REASON = "not meaningful for a lender: debt, deposits and interest are its raw material"
HOLDING_NOTES = {
    "insider_holding": "Yahoo's 'insiders' figure is the nearest free proxy for promoter holding in India; confirm against the "
                       "exchange's shareholding pattern, which is the official source",
    "institutional_holding": "Yahoo's institutional share is a vendor estimate; confirm against the exchange's shareholding pattern",
}


def is_lender(sector: str | None, industry: str | None) -> bool:
    text = f"{sector or ''} {industry or ''}".lower()
    return any(w in text for w in LENDER_WORDS)


def _num(x) -> Decimal | None:
    if x is None:
        return None
    try:
        if pd.isna(x) or (isinstance(x, float) and not math.isfinite(x)):
            return None
        return Decimal(str(x))
    except Exception:
        return None


def _pick(stmt: pd.DataFrame | None, names: tuple[str, ...], col) -> tuple[Decimal | None, str]:
    if stmt is None or stmt.empty:
        return None, ""
    for n in names:
        if n in stmt.index:
            return _num(stmt.at[n, col]), n
    return None, ""


def _has_values(statements: dict[str, pd.DataFrame | None], col) -> bool:
    """True when Yahoo has at least one value in this year's column for a row we read."""
    for st_name, names in {(v[0], v[1]) for v in ROWS.values()}:
        stmt = statements.get(st_name)
        if stmt is None or col not in stmt.columns:
            continue
        if any(n in stmt.index and _num(stmt.at[n, col]) is not None for n in names):
            return True
    return False


def annual_facts(ticker: str, statements: dict[str, pd.DataFrame | None], sector: str | None = None,
                 industry: str | None = None, now: datetime | None = None, max_years: int = 5,
                 notices: list[str] | None = None) -> list[Fact]:
    """Year figures from Yahoo's annual statements. Empty cells become unavailable facts with a reason."""
    now = now or datetime.now(timezone.utc)
    lender = is_lender(sector, industry)
    out: list[Fact] = []
    cols = []
    for s in statements.values():
        if s is not None and not s.empty:
            cols = list(s.columns)[:max_years]
            break
    kept = [c for c in cols if _has_values(statements, c)]
    for col in cols:
        if col in kept or notices is None:
            continue
        later = [c for c in kept if pd.Timestamp(c) > pd.Timestamp(col)]
        nxt = min(later, key=pd.Timestamp) if later else (max(kept, key=pd.Timestamp) if kept else None)
        start = f"; annual history starts at {fiscal_label(pd.Timestamp(nxt).date(), 'FY')}" if nxt is not None else ""
        notices.append(f"Yahoo lists the year ending {pd.Timestamp(col).date()} without figures{start}")
    for col in kept:
        end = pd.Timestamp(col).date()
        for metric, (st_name, names) in ROWS.items():
            stmt = statements.get(st_name)
            common = dict(entity_key=ticker, metric=metric, unit="INR", period_end=end, period_type=PeriodType.FY,
                          fiscal_label=fiscal_label(end, "FY"), source=SOURCE, retrieved_at=now,
                          available_from=available_from(end, "FY"), availability_kind=AvailabilityKind.deadline_estimate)
            if lender and metric in LENDER_NOT_APPLICABLE:
                out.append(Fact.make(value=None, status=Status.unavailable, reason=LENDER_REASON,
                                     source_field="n/a", **common))
                continue
            if stmt is None or col not in stmt.columns:
                out.append(Fact.make(value=None, status=Status.unavailable,
                                     reason=f"Yahoo returned no annual {st_name} statement", source_field="n/a", **common))
                continue
            v, row = _pick(stmt, names, col)
            if v is None:
                out.append(Fact.make(value=None, status=Status.unavailable,
                                     reason=f"Yahoo has no '{names[0]}' for the year ending {end}",
                                     source_field=names[0], **common))
            else:
                out.append(Fact.make(value=v, status=Status.ok, source_field=row,
                                     evidence=f"yfinance Ticker.{ {'income': 'income_stmt', 'balance': 'balance_sheet', 'cashflow': 'cashflow'}[st_name] } row '{row}', column {end}",
                                     **common))
    return out


def holding_facts(ticker: str, info: dict, now: datetime | None = None) -> list[Fact]:
    """Ownership proxies. Marked unverified: they are vendor approximations, not the exchange shareholding pattern."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    out = []
    for key, metric in (("heldPercentInsiders", "insider_holding"), ("heldPercentInstitutions", "institutional_holding")):
        v = _num(info.get(key))
        common = dict(entity_key=ticker, metric=metric, unit="ratio", period_end=today, period_type=PeriodType.point,
                      source=SOURCE, source_field=key, retrieved_at=now, available_from=today,
                      evidence=f"yfinance Ticker.info['{key}']")
        if v is None:
            out.append(Fact.make(value=None, status=Status.unavailable, reason="not provided by Yahoo", **common))
        else:
            out.append(Fact.make(value=v, status=Status.unverified, reason=HOLDING_NOTES[metric], **common))
    return out


# ---- computed ratios -----------------------------------------------------------------------------------------

def _fy(fs_facts: list[Fact], metric: str) -> list[Fact]:
    return sorted([f for f in fs_facts if f.metric == metric and f.period_type == PeriodType.FY
                   and f.status == Status.ok and f.value is not None], key=lambda f: f.period_end)


def _point(fs_facts: list[Fact], metric: str) -> Fact | None:
    c = [f for f in fs_facts if f.metric == metric and f.period_type == PeriodType.point
         and f.status == Status.ok and f.value is not None]
    return max(c, key=lambda f: f.period_end) if c else None


def _make(key, metric, value, unit, end, related, now, reason="", field=""):
    ok = value is not None
    return Fact.make(entity_key=key, metric=metric, value=Decimal(str(round(value, 6))) if ok else None, unit=unit,
                     period_end=end, period_type=PeriodType.point, source=COMPUTED, source_field=field or metric,
                     retrieved_at=now, status=Status.ok if ok else Status.unavailable,
                     reason="" if ok else reason, related_fact_ids=related)


def _cagr(series: list[Fact], years: int) -> tuple[float | None, list[str], str]:
    if len(series) < years + 1:
        return None, [], f"needs {years + 1} annual figures, have {len(series)}"
    a, b = series[-years - 1], series[-1]
    if (b.period_end.year - a.period_end.year) != years:
        return None, [a.fact_id, b.fact_id], "annual figures are not consecutive years"
    va, vb = float(a.value), float(b.value)
    if va <= 0 or vb <= 0:
        return None, [a.fact_id, b.fact_id], "growth rate is not meaningful when a year's figure is zero or negative"
    return (vb / va) ** (1 / years) - 1, [a.fact_id, b.fact_id], ""


def ratio_facts(fs: FactSet, now: datetime | None = None) -> list[Fact]:
    """Computed from the annual facts already in `fs`. Returns new facts only."""
    now = now or fs.retrieved_at
    key = fs.entity.ticker
    facts = fs.facts
    lender = is_lender(fs.entity.sector, fs.entity.industry)
    out: list[Fact] = []
    fy_ends = sorted({f.period_end for f in facts if f.period_type == PeriodType.FY and f.metric.startswith("fy_")})
    if not fy_ends:
        return out
    latest = fy_ends[-1]

    def at(metric: str) -> Fact | None:
        c = [f for f in _fy(facts, metric) if f.period_end == latest]
        return c[0] if c else None

    for metric, base in (("fy_revenue_cagr_3y", "fy_revenue"), ("fy_net_income_cagr_3y", "fy_net_income")):
        g, rel, why = _cagr(_fy(facts, base), 3)
        out.append(_make(key, metric, g, "ratio", latest, rel, now, why))

    for metric, base in (("fy_net_income_yoy", "fy_net_income"), ("fy_revenue_yoy", "fy_revenue")):
        ser = _fy(facts, base)
        if len(ser) >= 2 and ser[-1].period_end.year - ser[-2].period_end.year == 1 and float(ser[-2].value) > 0:
            out.append(_make(key, metric, float(ser[-1].value) / float(ser[-2].value) - 1, "ratio", latest,
                             [ser[-2].fact_id, ser[-1].fact_id], now, field="last two financial years"))
        else:
            out.append(_make(key, metric, None, "ratio", latest, [f.fact_id for f in ser[-2:]], now,
                             "needs two consecutive annual figures with a positive earlier year"))

    ni, rev, eq = at("fy_net_income"), at("fy_revenue"), at("fy_equity")
    assets = at("fy_total_assets")
    if lender:
        out.append(_make(key, "fy_equity_multiplier",
                         float(assets.value) / float(eq.value) if assets and eq and float(eq.value) > 0 else None,
                         "ratio", latest, [f.fact_id for f in (assets, eq) if f], now, "assets or equity unavailable"))
        for m, why in (("nim", "net interest margin is not in free data; read it in the company's results presentation"),
                       ("gross_npa_ratio", "gross NPA ratio is not in free data; read it in the company's results presentation")):
            out.append(_make(key, m, None, "ratio", latest, [], now, why))
        for m in ("fy_roce", "fy_net_debt_to_ebitda", "fy_interest_cover", "fy_fcf_margin", "fy_fcf_yield", "ev", "ev_ebitda"):
            out.append(_make(key, m, None, "ratio", latest, [], now, LENDER_REASON))
        return out

    ebit, ebitda, intr = at("fy_ebit"), at("fy_ebitda"), at("fy_interest_expense")
    debt, cash, cl = at("fy_total_debt"), at("fy_cash"), at("fy_current_liabilities")
    fcf = at("fy_free_cash_flow")

    capital = float(assets.value) - float(cl.value) if assets and cl else None
    out.append(_make(key, "fy_roce", float(ebit.value) / capital if ebit and capital and capital > 0 else None, "ratio", latest,
                     [f.fact_id for f in (ebit, assets, cl) if f], now, "EBIT, assets or current liabilities unavailable"))
    out.append(_make(key, "fy_interest_cover",
                     float(ebit.value) / abs(float(intr.value)) if ebit and intr and float(intr.value) != 0 else None, "ratio", latest,
                     [f.fact_id for f in (ebit, intr) if f], now, "EBIT or interest unavailable, or no interest cost"))
    net_debt = float(debt.value) - float(cash.value) if debt and cash else None
    out.append(_make(key, "fy_net_debt", net_debt, "INR", latest, [f.fact_id for f in (debt, cash) if f], now,
                     "debt or cash unavailable"))
    out.append(_make(key, "fy_net_debt_to_ebitda",
                     net_debt / float(ebitda.value) if net_debt is not None and ebitda and float(ebitda.value) > 0 else None,
                     "ratio", latest, [f.fact_id for f in (debt, cash, ebitda) if f], now,
                     "net debt or a positive EBITDA unavailable"))
    out.append(_make(key, "fy_fcf_margin",
                     float(fcf.value) / float(rev.value) if fcf and rev and float(rev.value) > 0 else None, "ratio", latest,
                     [f.fact_id for f in (fcf, rev) if f], now, "free cash flow or revenue unavailable"))

    mcap = _point(facts, "market_cap")
    related = [f.fact_id for f in (mcap, debt, cash, ebitda) if f]
    ev = float(mcap.value) + net_debt if mcap and net_debt is not None else None
    out.append(_make(key, "ev", ev, "INR", latest, related, now,
                     "market value, debt or cash unavailable (enterprise value = market value + debt - cash)"))
    out.append(_make(key, "ev_ebitda", ev / float(ebitda.value) if ev is not None and ebitda and float(ebitda.value) > 0 else None,
                     "ratio", latest, related, now,
                     "needs enterprise value and a positive last-year EBITDA; uses the last full financial year, not trailing quarters"))
    out.append(_make(key, "fy_fcf_yield",
                     float(fcf.value) / float(mcap.value) if fcf and mcap and float(mcap.value) > 0 else None, "ratio", latest,
                     [f.fact_id for f in (fcf, mcap) if f], now, "free cash flow or market value unavailable"))
    return out
