"""A project-defined 9-point pass/fail checklist (NOT the Piotroski F-score). Missing data is 'unavailable', never 'fail'."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel

from decimal import Decimal

from indiafacts.models import Fact, FactSet, Status
from indiafacts.units import format_inr


@dataclass(frozen=True)
class Check:
    id: str
    label: str
    metric: str
    test: Callable[[float], bool]
    threshold: str
    kind: str = "num"            # inr | pct | num
    fallback: str = ""           # annual metric used when the quarterly one is unavailable (labelled as such)


CHECKS = [
    Check("profitable_latest_quarter", "Latest quarter profit is positive", "net_income", lambda v: v > 0, "> 0", "inr"),
    Check("positive_eps_ttm", "Trailing earnings per share is positive", "eps_ttm", lambda v: v > 0, "> 0", "inr"),
    Check("earnings_growing", "Profit is higher than a year earlier", "net_income_yoy", lambda v: v > 0, "> 0%", "pct", "fy_net_income_yoy"),
    Check("revenue_growing", "Revenue is higher than a year earlier", "revenue_yoy", lambda v: v > 0, "> 0%", "pct", "fy_revenue_yoy"),
    Check("interest_cover", "Profit covers interest costs at least 3 times", "interest_service_coverage_ratio",
          lambda v: v >= 3, ">= 3", "num", "fy_interest_cover"),
    Check("debt_moderate", "Debt is below equity (debt-to-equity under 1)", "debt_to_equity", lambda v: v < 1, "< 1"),
    Check("positive_1y_return", "Price is higher than a year ago", "return_1y", lambda v: v > 0, "> 0%", "pct"),
    Check("beats_nifty_1y", "Price did better than the Nifty 50 over a year", "relative_return_1y", lambda v: v > 0, "> 0%", "pct"),
    Check("near_52w_high", "Price is within 25% of its 52-week high", "pct_from_52w_high", lambda v: v >= -0.25, ">= -25%", "pct"),
]


class CheckResult(BaseModel):
    id: str
    label: str
    result: str                     # pass | fail | unavailable
    value: float | None = None
    threshold: str = ""
    display: str = ""
    fact_ids: list[str] = []
    reason: str = ""


def _latest(fs: FactSet, metric: str) -> Fact | None:
    c = [f for f in fs.facts if f.metric == metric and f.status == Status.ok and f.value is not None]
    return max(c, key=lambda f: (f.period_end, f.retrieved_at)) if c else None


def checklist(fs: FactSet) -> list[CheckResult]:
    out = []
    for c in CHECKS:
        f = _latest(fs, c.metric)
        annual = False
        if f is None and c.fallback:
            f = _latest(fs, c.fallback)
            annual = f is not None
        if f is None:
            out.append(CheckResult(id=c.id, label=c.label, result="unavailable", threshold=c.threshold,
                                   fact_ids=[], reason=f"no data for {c.metric}"))
            continue
        v = float(f.value)
        shown = (format_inr(Decimal(str(f.value))) if c.kind == "inr" else f"{v:+.1%}" if c.kind == "pct" else f"{v:.2f}")
        out.append(CheckResult(id=c.id, label=c.label, result="pass" if c.test(v) else "fail", value=v,
                               threshold=c.threshold, display=shown + (" (last financial year)" if annual else ""),
                               fact_ids=[f.fact_id]))
    return out


def summarize(results: list[CheckResult]) -> str:
    known = [r for r in results if r.result != "unavailable"]
    passed = sum(1 for r in known if r.result == "pass")
    na = len(results) - len(known)
    return f"{passed}/{len(known)} passed" + (f", {na} unavailable" if na else "")
