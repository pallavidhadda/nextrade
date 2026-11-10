"""How complete and how fresh the data behind a report is, pillar by pillar. Pure functions over a FactSet; no I/O.

Facts are never changed: stale figures are counted and listed here, not rewritten. The issue definition is the one the text
report's DATA QUALITY line uses (gap, unavailable, conflict, unverified; a lender's not-applicable items excluded).
Education only; not financial advice."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from indiafacts.fundamentals import LENDER_REASON
from indiafacts.models import Fact, FactSet, PeriodType, Status

PRESENT_STATUSES = (Status.ok, Status.unverified, Status.conflict)     # a figure with a value in one of these counts as present
PARAMS_PATH = Path(__file__).parent / "data" / "completeness_params.json"
ISSUE_STATUSES = (Status.gap, Status.unavailable, Status.conflict, Status.unverified)
LEVELS = ("High", "Medium", "Low", "Insufficient")


def load_completeness_params(path: Path | None = None) -> dict:
    data = json.loads(Path(path or PARAMS_PATH).read_text(encoding="utf-8"))
    data["overdue"] = date.fromisoformat(data["review_by"]) < date.today()
    return data


def is_issue(f: Fact) -> bool:
    return f.status in ISSUE_STATUSES and f.reason != LENDER_REASON


# A vendor figure that is missing is not a gap when the same measure exists under another name from another source: the
# exchange shareholding for Yahoo's holding percentages, trailing sums of reported quarters for Yahoo's TTM figures, and
# last-full-year ratios from the annual statements for Yahoo's current ROE / ROA.
GAP_ALIASES: dict[str, tuple[str, ...]] = {
    "insider_holding": ("sh_promoter",),
    "institutional_holding": ("sh_foreign_inst", "sh_domestic_inst"),
    "revenue_ttm_vendor": ("revenue_ttm",),
    "net_income_ttm_vendor": ("net_income_ttm",),
    "eps_ttm": ("eps_diluted_ttm",),
    "roe": ("fy_roe",),
    "roa": ("fy_roa",),
    "payout_ratio": ("fy_payout_ratio",),
}
POINT_FILL_DAYS = 10          # a current figure (price, P/E, market value) from another source dated within this many days


def attention_items(facts: list[Fact]) -> list[Fact]:
    """Issue facts, minus gaps/unavailable/unverified figures that another source fills with an ok value: for the same period,
    for a current (point) figure dated within POINT_FILL_DAYS, or (gaps only) under a GAP_ALIASES name."""
    ok = [f for f in facts if f.status == Status.ok and f.value is not None]
    filled = {(f.metric, f.period_end, f.period_type): f.source for f in ok}
    points: dict[str, list[Fact]] = {}
    for f in ok:
        points.setdefault(f.metric, []).append(f)

    def covered(f: Fact) -> bool:
        if f.status == Status.conflict:
            return False
        k = (f.metric, f.period_end, f.period_type)
        if k in filled and filled[k] != f.source:
            return True
        if f.period_type == PeriodType.point and any(
                g.source != f.source and g.period_type == PeriodType.point and abs((g.period_end - f.period_end).days) <= POINT_FILL_DAYS
                for g in points.get(f.metric, [])):
            return True
        return f.status in (Status.gap, Status.unavailable) and any(points.get(a) for a in GAP_ALIASES.get(f.metric, ()))

    return [f for f in facts if is_issue(f) and not covered(f)]


def definition_differences(facts: list[Fact]) -> list[Fact]:
    """Checks where two sources state the same figure on a different basis or definition: listed, never counted as disagreement."""
    from indiafacts.analysis import DEFINITION_PREFIX

    return [f for f in facts if f.metric.endswith("_source_check") and f.reason.startswith(DEFINITION_PREFIX)]


def data_notes(items: list[Fact], definitions: list[Fact] | None = None) -> str:
    """'Data notes: X figures missing, Y figures where sources disagree, Z vendor figures not checked against filings'."""
    def n(pred) -> int:
        return len({(f.metric, f.period_end, f.period_type) for f in items if pred(f)})

    nd = len({(f.metric, f.period_end, f.period_type) for f in definitions or []})
    missing = n(lambda f: f.status in (Status.gap, Status.unavailable))
    conflicts = n(lambda f: f.status == Status.conflict)
    vendor = n(lambda f: f.status == Status.unverified and f.source == "yahoo" and not f.metric.startswith("fy_"))
    parts = [p for p in (f"{missing} figures missing" if missing else "",
                         f"{conflicts} figures where sources disagree" if conflicts else "",
                         f"{vendor} vendor figures not checked against filings" if vendor else "",
                         f"{nd} figures that sources define differently (not a disagreement)" if nd else "") if p]
    return "Data notes: " + ", ".join(parts) if parts else "Data notes: nothing flagged"


def _val(f: Fact | None):
    return None if f is None or f.value is None else str(f.value)


def _pillar_of(f: Fact, pillars: dict) -> str | None:
    """Exact names first (expected or also), then prefixes, in the order the params list the pillars."""
    for key, p in pillars.items():
        if p.get("sources"):                                   # a source-restricted pillar only measures presence
            continue
        names = {m for e in p["expected"] for m in e.split("|")} | set(p.get("also", []))
        if f.metric in names:
            return key
    for key, p in pillars.items():
        if not p.get("sources") and any(f.metric.startswith(x) for x in p.get("prefixes", [])):
            return key
    return None


def _limit(p: dict, f: Fact) -> int:
    if f.period_type.value == "FY" and "max_age_days_fy" in p:
        return p["max_age_days_fy"]
    return p["max_age_days"]


def _conflicts(fs: FactSet) -> list[dict]:
    by_id = {f.fact_id: f for f in fs.facts}
    out = []
    for f in fs.facts:
        if f.status != Status.conflict:
            continue
        rel = [by_id[i] for i in f.related_fact_ids if i in by_id]
        if f.metric.endswith("_source_check") and len(rel) == 2:
            chosen, alt, metric = rel[0], rel[1], f.metric.removesuffix("_source_check")
        else:
            chosen, metric = f, f.metric
            alt = next((r for r in rel if r.metric == f.metric and r.fact_id != f.fact_id), None)
        out.append({"metric": metric, "period": str(chosen.period_end),
                    "chosen": {"value": _val(chosen), "source": chosen.source, "unit": chosen.unit},
                    "alternative": None if alt is None else {"value": _val(alt), "source": alt.source, "unit": alt.unit},
                    "reason": f.reason, "fact_id": f.fact_id})
    return out


def completeness(fs: FactSet, as_of: date | None = None, news: list | None = None, params: dict | None = None) -> dict:
    """Per-pillar coverage and freshness, an overall level, and the conflicts with both values.

    A metric counts as covered when its latest ok figure is within the pillar's age limit; an older ok figure is reported as
    stale and does not count toward coverage. `news` is optional: None leaves the news pillar out as not assessed."""
    p = params or load_completeness_params()
    when = as_of or fs.retrieved_at.date()
    ok = [f for f in fs.facts if f.status in PRESENT_STATUSES and f.value is not None]
    official = set(p.get("official_sources", []))
    counted: list[Fact] = []                                     # the latest figure behind every covered or stale entry
    pillars: dict[str, dict] = {}
    totals: dict[str, int] = {}
    attributed: dict[str, list[Fact]] = {k: [] for k in p["pillars"]}
    other = 0
    for f in fs.facts:
        if not is_issue(f):
            continue
        totals[f.status.value] = totals.get(f.status.value, 0) + 1
        key = _pillar_of(f, p["pillars"])
        if key is None:
            other += 1
        else:
            attributed[key].append(f)
    for key, pp in p["pillars"].items():
        srcs = pp.get("sources")
        pool = [f for f in ok if not srcs or f.source in srcs]
        expected, present, stale, missing, n_a = [], [], [], [], []
        verified_n, vendor_est = 0, []
        for entry in pp["expected"]:
            names = entry.split("|")
            stated = [f for f in fs.facts if f.metric in names and (not srcs or f.source in srcs)]
            if stated and not any(f.metric in names for f in pool) and all(f.reason == LENDER_REASON for f in stated):
                n_a.append(entry)                                # every figure for it is a lender's not-applicable item
                continue
            expected.append(entry)
            have = [f for f in pool if f.metric in names]
            if not have:
                missing.append(entry)
                continue
            latest = max(have, key=lambda f: (f.period_end, f.status == Status.ok, f.source in official, f.retrieved_at))
            counted.append(latest)
            if latest.status == Status.ok:
                verified_n += 1
            elif latest.status == Status.unverified:
                vendor_est.append(entry)
            age, limit = (when - latest.period_end).days, _limit(pp, latest)
            if age > limit:
                stale.append({"metric": latest.metric, "period": str(latest.period_end), "age_days": age, "max_age_days": limit,
                              "source": latest.source, "fact_id": latest.fact_id})
            else:
                present.append(entry)
        by_status: dict[str, int] = {}
        for f in attributed[key]:
            by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
        n_present = len(present) + len(stale)
        pillars[key] = {"label": pp["label"], "expected": expected, "expected_n": len(expected), "not_applicable": n_a,
                        "present_ok": n_present, "fresh_ok": len(present), "verified_n": verified_n,
                        "vendor_only": n_present > 0 and verified_n == 0 and len(vendor_est) == n_present, "vendor_estimate": vendor_est, "stale_n": len(stale), "stale": stale, "missing": missing,
                        "coverage_pct": round(100 * len(present) / len(expected), 1) if expected else None,
                        "issues": by_status, "issues_n": sum(by_status.values())}
    if news is not None:
        need = p["news"]["min_items"]
        pillars["news"] = {"label": p["news"]["label"], "expected": [f"{need} recent item(s)"], "expected_n": 1, "not_applicable": [],
                           "present_ok": int(len(news) >= need), "fresh_ok": int(len(news) >= need), "verified_n": int(len(news) >= need),
                           "vendor_only": False, "vendor_estimate": [], "stale_n": 0, "stale": [],
                           "missing": [] if len(news) >= need else ["news"], "coverage_pct": 100.0 if len(news) >= need else 0.0,
                           "issues": {}, "issues_n": 0}
    scored = [v["coverage_pct"] for v in pillars.values() if v["coverage_pct"] is not None]
    overall = round(sum(scored) / len(scored), 1) if scored else 0.0
    th = p["thresholds"]
    weak = [k for k in th["insufficient_pillars"] if k in pillars and (pillars[k]["coverage_pct"] or 0) < th["insufficient_below"] * 100]
    if weak:
        level, why = "Insufficient", ", ".join(f"{pillars[k]['label'].lower()} {pillars[k]['coverage_pct'] or 0:.0f}%" for k in weak) + \
            f" covered, below {th['insufficient_below']:.0%}"
    elif overall >= th["high"] * 100:
        level, why = "High", f"average pillar coverage {overall:.0f}%"
    elif overall >= th["medium"] * 100:
        level, why = "Medium", f"average pillar coverage {overall:.0f}%"
    else:
        level, why = "Low", f"average pillar coverage {overall:.0f}%"
    n_off = sum(1 for f in counted if f.source in official)
    n_comp = sum(1 for f in counted if f.source not in official and f.source.startswith("computed"))
    verification = {"official_n": n_off, "vendor_n": len(counted) - n_off - n_comp, "computed_n": n_comp,
                    "label": "Not checked against official filings" if n_off == 0 else "Partly checked against official filings"}
    return {"as_of": str(when), "level": level, "verification": verification, "reason": why, "overall_coverage_pct": overall, "pillars": pillars,
            "issues_total": sum(totals.values()), "issues_by_status": totals, "issues_unmapped": other,
            "stale_total": sum(v["stale_n"] for v in pillars.values()), "conflicts": _conflicts(fs),
            "definitions": [{"metric": f.metric.removesuffix("_source_check"), "period": str(f.period_end), "reason": f.reason.removeprefix("different definition: ")}
                            for f in definition_differences(fs.facts)],
            "params_reviewed_on": p["reviewed_on"], "params_overdue": p["overdue"]}
