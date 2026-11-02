"""Check a stated figure against sourced facts: supported, contradicted, supported only by an unverified source, or unverifiable.
Deterministic; no model. Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal

from indiafacts.models import FactSet, Status
from indiafacts.units import format_inr

ALIASES = {
    "eps": ["eps_ttm", "eps_diluted", "eps_basic"], "earnings per share": ["eps_ttm", "eps_diluted", "eps_basic"],
    "net profit": ["net_income", "net_income_total"], "net income": ["net_income", "net_income_total"], "profit": ["net_income", "net_income_total"],
    "pat": ["net_income", "net_income_total"], "revenue": ["revenue"], "sales": ["revenue"], "pe": ["pe_ttm"], "p/e": ["pe_ttm"],
    "pb": ["pb"], "p/b": ["pb"], "roe": ["roe"], "debt to equity": ["debt_to_equity"], "market cap": ["market_cap"],
    "price": ["price", "last_close"], "ebitda": ["ebitda"], "profit before tax": ["profit_before_tax"], "pbt": ["profit_before_tax"],
    "total assets": ["total_assets"], "operating cash flow": ["operating_cash_flow"], "finance costs": ["interest_expense"],
    "interest expense": ["interest_expense"],
}
UNITS = {"inr": Decimal(1), "crore": Decimal(10) ** 7, "lakh_crore": Decimal(10) ** 12, "per_share": Decimal(1), "ratio": Decimal(1), "percent": Decimal("0.01")}
OFFICIAL = ("nse_filing", "nse_xbrl")


def to_base_units(value: float | Decimal, unit: str) -> Decimal:
    return Decimal(str(value)) * UNITS[unit]


@dataclass
class Match:
    fact_id: str
    source: str
    period: str
    value: Decimal
    status: str
    evidence: str
    difference_pct: float


@dataclass
class ClaimResult:
    verdict: str                      # supported | contradicted | supported_unverified | unverifiable
    metric: str
    claimed: Decimal | None
    tolerance_pct: float
    matches: list[Match] = field(default_factory=list)
    closest: Match | None = None
    difference_pct: float | None = None
    explanation: str = ""


def _norm(label: str | None) -> str:
    return re.sub(r"\s+", "", (label or "")).lower()


def _show(value: Decimal, base_unit: str) -> str:
    return format_inr(value) if base_unit == "INR" else f"{value:,.2f}".rstrip("0").rstrip(".")


def check_claim(fs: FactSet, metric: str, value: float, unit: str | None, period: str | None = None, tolerance_pct: float = 1.0) -> ClaimResult:
    name = metric.strip().lower()
    cands = ALIASES.get(name, [name] if any(f.metric == name for f in fs.facts) else [])
    res = ClaimResult("unverifiable", name, None, tolerance_pct)
    if not cands:
        res.explanation = f"'{metric}' is not a measure this tool can check; supported names include: " + ", ".join(sorted(ALIASES)) + "."
        return res
    if unit is None or unit not in UNITS:
        res.explanation = f"State the unit of the claimed figure (one of {', '.join(UNITS)}); without a unit the comparison would be a guess."
        return res
    claimed = to_base_units(value, unit)
    res.claimed = claimed
    pool = [f for f in fs.facts if f.metric in cands and f.value is not None and f.status in (Status.ok, Status.unverified)]
    if period:
        want = _norm(period)
        pool = [f for f in pool if _norm(f.fiscal_label) == want]
    else:
        latest: dict[tuple[str, str], object] = {}
        for f in sorted(pool, key=lambda f: f.period_end):
            latest[(f.metric, f.source)] = f
        pool = list(latest.values())
    if not pool:
        have = sorted({f.fiscal_label for f in fs.facts if f.metric in cands and f.fiscal_label})
        res.explanation = (f"No figure for {name}" + (f" in {period}" if period else "") + " is available in the data for this company"
                           + (f"; periods available: {', '.join(have)}" if have else "") + ".")
        return res
    unit_of = {f.fact_id: f.unit for f in pool}
    ms = []
    for f in pool:
        diff = float((claimed - f.value) / f.value * 100) if f.value != 0 else (0.0 if claimed == 0 else float("inf"))
        ms.append(Match(f.fact_id, f.source, f.fiscal_label or f.period_end.isoformat(), f.value, f.status.value, f.evidence or "", diff))
    ms.sort(key=lambda m: abs(m.difference_pct))
    res.matches = [m for m in ms if abs(m.difference_pct) <= tolerance_pct]
    res.closest, res.difference_pct = ms[0], ms[0].difference_pct
    if res.matches:
        solid = [m for m in res.matches if m.status == "ok"]
        if solid:
            res.verdict = "supported"
            res.explanation = (f"The claim matches {len(solid)} sourced figure(s) within {tolerance_pct:g}%: "
                               + "; ".join(f"{m.source} {m.period} = {_show(m.value, unit_of[m.fact_id])}" for m in solid) + ".")
        else:
            res.verdict = "supported_unverified"
            res.explanation = ("The claim matches a figure, but only one that is marked unverified, so it is not confirmed: "
                               + "; ".join(f"{m.source} {m.period} = {_show(m.value, unit_of[m.fact_id])}" for m in res.matches) + ".")
    else:
        res.verdict = "contradicted"
        c = ms[0]
        bu = unit_of[c.fact_id]
        res.explanation = (f"The claim ({_show(claimed, bu)}) differs from the closest sourced figure by {c.difference_pct:+.1f}%: "
                           f"{c.source} {c.period} = {_show(c.value, bu)} (tolerance {tolerance_pct:g}%).")
        if not period and re.match(r"^\d{4}-\d{2}-\d{2}$", c.period):
            res.explanation += (" That figure is the latest live or trailing-twelve-month value; if the claim is for a fiscal period, "
                                "give the period (for example FY26 or Q2 FY27) so the matching reported figure is used.")
    return res


def result_dict(r: ClaimResult) -> dict:
    return {"verdict": r.verdict, "metric": r.metric, "claimed": str(r.claimed) if r.claimed is not None else None, "tolerance_pct": r.tolerance_pct,
            "difference_pct": r.difference_pct, "explanation": r.explanation,
            "matches": [{"fact_id": m.fact_id, "source": m.source, "period": m.period, "value": str(m.value), "status": m.status, "evidence": m.evidence,
                         "difference_pct": round(m.difference_pct, 3)} for m in (r.matches or ([r.closest] if r.closest else []))]}


def main(argv: list[str] | None = None, client=None, **kw) -> int:
    from indiafacts.pipeline import build_factset

    p = argparse.ArgumentParser(prog="indiafacts.claims", description="Check one stated figure against sourced facts (education only).")
    p.add_argument("ticker")
    p.add_argument("metric")
    p.add_argument("value", type=float)
    p.add_argument("--unit", choices=sorted(UNITS), default=None)
    p.add_argument("--period", default=None, help='for example "Q2 FY27" or "FY26"; default is the latest figure')
    p.add_argument("--tolerance", type=float, default=1.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--filing", type=str, action="append", default=None)
    a = p.parse_args(argv)
    from pathlib import Path

    fs = build_factset(a.ticker, client=client, prices=False, tej=False, filing_path=[Path(x) for x in a.filing] if a.filing else None, **kw)
    r = check_claim(fs, a.metric, a.value, a.unit, a.period, a.tolerance)
    out = result_dict(r)
    print(json.dumps(out) if a.json else f"{r.verdict.upper()}: {r.explanation}\nResearch and education only; not financial, investment or trading advice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
