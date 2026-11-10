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
    group: str = ""


F, B, T = "Fundamentals", "Balance sheet", "Price trend"
CHECKS = [
    Check("profitable_latest_quarter", "Latest quarter profit is positive", "net_income", lambda v: v > 0, "> 0", "inr", group=F),
    Check("positive_eps_ttm", "Trailing earnings per share is positive", "eps_ttm", lambda v: v > 0, "> 0", "inr", group=F),
    Check("earnings_growing", "Profit is higher than a year earlier", "net_income_yoy", lambda v: v > 0, "> 0%", "pct", "fy_net_income_yoy", F),
    Check("revenue_growing", "Revenue is higher than a year earlier", "revenue_yoy", lambda v: v > 0, "> 0%", "pct", "fy_revenue_yoy", F),
    Check("interest_cover", "Profit covers interest costs at least 3 times", "interest_service_coverage_ratio",
          lambda v: v >= 3, ">= 3", "num", "fy_interest_cover", B),
    Check("debt_moderate", "Debt is below equity (debt-to-equity under 1)", "debt_to_equity", lambda v: v < 1, "< 1", group=B),
    Check("positive_1y_return", "Price is higher than a year ago", "return_1y", lambda v: v > 0, "> 0%", "pct", group=T),
    Check("beats_nifty_1y", "Price did better than the Nifty 50 over a year", "relative_return_1y", lambda v: v > 0, "> 0%", "pct", group=T),
    Check("near_52w_high", "Price is within 25% of its 52-week high", "pct_from_52w_high", lambda v: v >= -0.25, ">= -25%", "pct", group=T),
]
# No existing check is a valuation test, so the Valuation group is empty and not shown (no check is invented to fill it).
GROUP_ORDER = ("Fundamentals", "Balance sheet", "Valuation", "Price trend")


class CheckResult(BaseModel):
    id: str
    group: str = ""
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
            out.append(CheckResult(id=c.id, group=c.group, label=c.label, result="unavailable", threshold=c.threshold,
                                   fact_ids=[], reason=f"no data for {c.metric}"))
            continue
        v = float(f.value)
        shown = (format_inr(Decimal(str(f.value))) if c.kind == "inr" else f"{v:+.1%}" if c.kind == "pct" else f"{v:.2f}")
        out.append(CheckResult(id=c.id, group=c.group, label=c.label, result="pass" if c.test(v) else "fail", value=v,
                               threshold=c.threshold, display=shown + (" (last financial year)" if annual else ""),
                               fact_ids=[f.fact_id]))
    return out


def group_text(rs: list[CheckResult]) -> str:
    unav = sum(1 for r in rs if r.result == "unavailable")
    return f"{sum(1 for r in rs if r.result == 'pass')} of {len(rs)} passed, {unav} unavailable"


def grouped(results: list[CheckResult]) -> list[dict]:
    """Per-group counts. Each check counts once and equally; no weights. A group with no check is left out."""
    out = []
    for g in GROUP_ORDER:
        rs = [r for r in results if r.group == g]
        if rs:
            out.append({"group": g, "passed": sum(1 for r in rs if r.result == "pass"), "total": len(rs),
                        "unavailable": sum(1 for r in rs if r.result == "unavailable"), "text": group_text(rs),
                        "checks": [r.id for r in rs]})
    return out


def summarize(results: list[CheckResult]) -> str:
    known = [r for r in results if r.result != "unavailable"]
    passed = sum(1 for r in known if r.result == "pass")
    na = len(results) - len(known)
    return f"{passed}/{len(known)} passed" + (f", {na} unavailable" if na else "")


# ---------------------------------------------------------------------------------------------------------------------------
# Plain-English phrasing of a checklist result, for the bull/bear points and the "what to monitor" list.
# Keys (check ids) are unchanged; text falls back to the check's label when an id has no phrasing.
# ---------------------------------------------------------------------------------------------------------------------------
def _pp(v: float) -> str:
    return f"{abs(v) * 100:.1f}"


def _span(r: CheckResult) -> str:
    return " in the last financial year" if "last financial year" in (r.display or "") else " compared with a year earlier"


def point_text(r: CheckResult) -> str:
    """One plain sentence saying what a passed or failed check means; direction-aware."""
    v, ok = r.value, r.result == "pass"
    if v is None:
        return r.label
    if r.id in ("earnings_growing", "revenue_growing"):
        what = "Profit" if r.id == "earnings_growing" else "Sales"
        return f"{what} grew {v:.0%}{_span(r)}." if ok else f"{what} fell {abs(v):.0%}{_span(r)}." if v < 0 else f"{what} did not grow{_span(r)}."
    if r.id == "interest_cover":
        return f"Profit covers interest costs {v:.1f} times over." if ok else f"Profit covers interest costs only {v:.1f} times; 3 or more is more comfortable."
    if r.id == "debt_moderate":
        return (f"Debt is lower than shareholders' equity (debt-to-equity {v:.2f})." if ok
                else f"Debt is as large as or larger than shareholders' equity (debt-to-equity {v:.2f}).")
    if r.id == "positive_1y_return":
        return f"The share price is {v:.1%} higher than a year ago." if ok else f"The share price is {abs(v):.1%} lower than a year ago." if v < 0 else "The share price is unchanged from a year ago."
    if r.id == "beats_nifty_1y":
        return (f"Over the past year the share did {_pp(v)} percentage points better than the Nifty 50." if ok
                else f"Over the past year the share did {_pp(v)} percentage points worse than the Nifty 50.")
    if r.id == "near_52w_high":
        return "The share price is close to its 52-week high." if ok else f"The share price is {abs(v):.0%} below its 52-week high."
    return r.label


def watch_text(r: CheckResult) -> str:
    """A forward-looking item for a failed check: what to watch for, with where it stands now."""
    v = r.value
    if v is None:
        return r.label
    if r.id in ("earnings_growing", "revenue_growing"):
        what, verb = ("profit", "is") if r.id == "earnings_growing" else ("sales", "are")
        return (f"Whether {what} rise{'s' if verb == 'is' else ''} above the level of a year earlier ({what} {verb} {abs(v):.0%} lower now)." if v < 0
                else f"Whether {what} start{'s' if verb == 'is' else ''} to grow compared with a year earlier.")
    if r.id == "interest_cover":
        return f"Whether profit covers interest costs at least 3 times (it is {v:.1f} times now)."
    if r.id == "debt_moderate":
        return f"Whether debt comes down below shareholders' equity (debt-to-equity is {v:.2f} now)."
    if r.id == "positive_1y_return":
        return f"Whether the price climbs back above where it was a year ago (it is {abs(v):.1%} lower now)."
    if r.id == "beats_nifty_1y":
        return f"Whether the share starts doing better than the Nifty 50 (it is {_pp(v)} percentage points behind over a year)."
    if r.id == "near_52w_high":
        return f"Whether the price gets back within 25% of its 52-week high (it is {abs(v):.0%} below it now)."
    return f"{r.label} (now {r.display})."
