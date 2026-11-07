"""Plain-English rows for the business-health block. One builder feeds the terminal, HTML, JSON and digest views.

Each row: label, display value, reading (a short word, never advice), status and the fact ids behind it.
Readings use fixed thresholds from `READING`; they describe the number, they do not recommend anything.
"""
from __future__ import annotations

from decimal import Decimal

from indiafacts.fundamentals import is_lender
from indiafacts.models import FactSet, PeriodType, Status
from indiafacts.units import format_inr

# metric -> (label, kind, [(upper bound, reading)], plain meaning)
NONLENDER = [
    ("fy_revenue", "Sales, last financial year", "inr", None, "Total sales in the latest full year."),
    ("fy_revenue_cagr_3y", "Sales growth, 3-year yearly average", "pct", [(0.0, "shrinking"), (0.08, "slow"), (0.18, "healthy"), (9, "fast")],
     "How fast sales grew each year over three years."),
    ("fy_net_income", "Profit, last financial year", "inr", None, "Profit left for shareholders in the latest full year."),
    ("fy_net_income_cagr_3y", "Profit growth, 3-year yearly average", "pct", [(0.0, "shrinking"), (0.08, "slow"), (0.18, "healthy"), (9, "fast")],
     "How fast profit grew each year over three years."),
    ("fy_free_cash_flow", "Free cash flow, last financial year", "inr", None, "Cash left after running costs and capital spending."),
    ("fy_fcf_margin", "Free cash flow as share of sales", "pct", [(0.0, "negative"), (0.05, "thin"), (0.12, "healthy"), (9, "strong")],
     "Rupees of free cash from each 100 of sales."),
    ("fy_roce", "Return on capital employed", "pct", [(0.0, "negative"), (0.10, "low"), (0.18, "decent"), (9, "high")],
     "Operating profit earned on the money tied up in the business."),
    ("fy_net_debt_to_ebitda", "Net debt vs yearly operating earnings", "x", [(0.0, "net cash"), (1.5, "low"), (3.0, "moderate"), (99, "high")],
     "Years of operating earnings needed to repay net debt."),
    ("fy_interest_cover", "Operating profit vs interest cost", "x", [(1.5, "thin"), (3.0, "adequate"), (99, "comfortable")],
     "How many times operating profit covers interest."),
    ("ev_ebitda", "Enterprise value vs operating earnings (EV/EBITDA)", "x", None,
     "What the whole business costs against a year of operating earnings. Compare with peers, not alone."),
    ("fy_fcf_yield", "Free cash flow yield", "pct", [(0.0, "negative"), (0.02, "low"), (0.05, "moderate"), (9, "high")],
     "Free cash flow as a share of today's market value."),
    ("insider_holding", "Promoter or insider holding (vendor proxy)", "pct", None,
     "Share held by insiders. Confirm in the exchange shareholding pattern."),
    ("institutional_holding", "Institutional holding (vendor proxy)", "pct", None, "Share held by funds and institutions."),
]
LENDER = [
    ("roe", "Return on equity", "pct", [(0.0, "negative"), (0.10, "low"), (0.15, "decent"), (9, "high")], "Profit earned on shareholders' money."),
    ("roa", "Return on assets", "pct", [(0.0, "negative"), (0.008, "low"), (0.015, "decent"), (9, "high")], "Profit earned on everything the lender holds."),
    ("pb", "Price to book value", "x", None, "Market value against the accounting value of equity."),
    ("fy_equity_multiplier", "Assets per rupee of equity", "x", None,
     "How much the lender has borrowed against its own money."),
    ("nim", "Net interest margin", "pct", None, "Spread the lender earns on its loans."),
    ("gross_npa_ratio", "Gross bad loans", "pct", None, "Share of loans that stopped paying."),
    ("fy_net_income_cagr_3y", "Profit growth, 3-year yearly average", "pct", [(0.0, "shrinking"), (0.08, "slow"), (0.18, "healthy"), (9, "fast")],
     "How fast profit grew each year over three years."),
    ("insider_holding", "Promoter or insider holding (vendor proxy)", "pct", None, "Confirm in the exchange shareholding pattern."),
]


def _latest(fs: FactSet, metric: str):
    c = [f for f in fs.facts if f.metric == metric and f.period_type in (PeriodType.FY, PeriodType.point)]
    ok = [f for f in c if f.value is not None and f.status in (Status.ok, Status.unverified)]
    if ok:
        return max(ok, key=lambda f: (f.period_end, f.retrieved_at))
    return max(c, key=lambda f: (f.period_end, f.retrieved_at)) if c else None


def _show(kind: str, v: Decimal) -> str:
    return format_inr(v) if kind == "inr" else f"{float(v):.1%}" if kind == "pct" else f"{float(v):.1f}x"


def _reading(bands, v: float) -> str:
    if not bands:
        return ""
    if bands[0][1] == "net cash" and v < 0:
        return "net cash"
    for ub, word in bands:
        if v <= ub:
            return word
    return bands[-1][1]


def fundamentals_rows(fs: FactSet) -> list[dict]:
    spec = LENDER if is_lender(fs.entity.sector, fs.entity.industry) else NONLENDER
    rows = []
    for metric, label, kind, bands, meaning in spec:
        f = _latest(fs, metric)
        if f is None:
            rows.append(dict(metric=metric, label=label, display="not available", reading="", status="unavailable",
                             meaning=meaning, reason="no data returned", fact_ids=[], period=""))
            continue
        if f.value is None:
            rows.append(dict(metric=metric, label=label, display="not available", reading="", status=f.status.value,
                             meaning=meaning, reason=f.reason, fact_ids=[f.fact_id], period=""))
            continue
        v = f.value
        rows.append(dict(metric=metric, label=label, display=_show(kind, v), reading=_reading(bands, float(v)),
                         status=f.status.value, meaning=meaning, reason=f.reason, fact_ids=[f.fact_id],
                         period=f.fiscal_label or "latest"))
    return rows


def fundamentals_lines(fs: FactSet) -> list[str]:
    rows = fundamentals_rows(fs)
    lender = is_lender(fs.entity.sector, fs.entity.industry)
    out = ["", "BUSINESS HEALTH (annual statements" + ("; lender metric set" if lender else "") + ")"]
    for r in rows:
        tail = f" [{r['reading']}]" if r["reading"] else ""
        note = f" - {r['reason']}" if r["status"] != "ok" and r["reason"] else ""
        per = f" ({r['period']})" if r["period"] and r["period"] != "latest" else ""
        out.append(f"  {r['label']}: {r['display']}{per}{tail}{note}")
    return out
