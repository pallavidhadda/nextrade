"""Fact-only renderer: every printed number is a Fact, tagged with a ref into a source index."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Sequence

from indiafacts.analysis import prefer_sources
from indiafacts.calendar import fiscal_label
from indiafacts.models import Fact, FactSet, PeriodType, Status
from indiafacts.units import format_inr

DISCLAIMER = (
    "Research and education only. Not financial, investment or trading advice. "
    "Data may be late, incomplete or wrong; check primary sources."
)


_PCT_PREFIXES = ("return_", "benchmark_return_", "relative_return_", "max_drawdown_", "pct_from_", "volatility")


def _is_price(f: Fact) -> bool:
    return f.source == "computed" and (f.source_field or "").startswith("series:")


class _Refs:
    def __init__(self) -> None:
        self._by_id: dict[str, str] = {}
        self._rows: list[str] = []

    def ref(self, f: Fact) -> str:
        if f.fact_id not in self._by_id:
            name = f"r{len(self._by_id) + 1}"
            self._by_id[f.fact_id] = name
            where = f"{f.source}:{f.source_field}" if f.source_field else f.source
            self._rows.append(
                f"{name} = {f.fact_id} | {f.metric} | {f.fiscal_label or f.period_end} | {where} | "
                f"retrieved {f.retrieved_at.date()}" + (f" | evidence: {f.evidence}" if f.evidence else "")
            )
        return self._by_id[f.fact_id]

    def index(self) -> str:
        return "\n".join(self._rows)


def _fmt(f: Fact) -> str:
    v: Decimal = f.value
    if f.metric.startswith(_PCT_PREFIXES):
        return f"{v:+.1%}" if not f.metric.startswith(("volatility", "benchmark_return")) else f"{v:.1%}"
    if f.metric.endswith("_yoy") or f.metric.endswith("_source_check"):
        return f"{v:.1%}" if f.metric.endswith("_source_check") else f"{v:+.1%}"
    if f.unit in ("INR", "INR_per_share"):
        return format_inr(v)
    return f"{v:.2f}"


def _cell(f: Fact | None, refs: _Refs) -> str:
    if f is None:
        return "–"
    if f.status == Status.gap:
        return "unav (gap)"
    if f.status == Status.unavailable:
        return "unav"
    tag = f"{_fmt(f)} [{refs.ref(f)}]"
    if f.status == Status.conflict:
        return tag + " conflict"
    if f.status == Status.unverified:
        return tag + " unverified"
    return tag


def render_table(facts: Sequence[Fact], refs: _Refs | None = None) -> str:
    for f in facts:
        if not isinstance(f, Fact):
            raise TypeError(f"render_table accepts only Fact objects, got {type(f).__name__}")
    own = refs is None
    refs = refs or _Refs()
    qs = prefer_sources([f for f in facts if f.period_type == PeriodType.Q and f.source != "computed" and f.status != Status.stale])
    ends = sorted({f.period_end for f in qs}, reverse=True)
    labels = {f.period_end: f.fiscal_label or fiscal_label(f.period_end, "Q") for f in qs}
    metrics = sorted({f.metric for f in qs})
    cell: dict[tuple[str, date], Fact] = {(f.metric, f.period_end): f for f in qs}
    lines = ["| metric | " + " | ".join(labels[e] for e in ends) + " |",
             "|" + "---|" * (len(ends) + 1)]
    for m in metrics:
        lines.append(f"| {m} | " + " | ".join(_cell(cell.get((m, e)), refs) for e in ends) + " |")
    out = "\n".join(lines)
    return out + "\n\n" + refs.index() if own and refs.index() else out


PRO_ONLY = {"change_in_inventories", "net_income_nci", "net_income_total", "other_income", "total_income",
            "total_expenses", "total_tax", "depreciation", "eps_basic", "profit_before_tax"}


def _profile_block(profile, is_default: bool, view: str) -> list[str]:
    from indiafacts.profile import presets_overdue, weights_for

    w = ", ".join(f"{k} {v:.0%}" for k, v in weights_for(profile).items())
    lines = ["", "PROFILE",
             f"horizon {profile.horizon} | goal {profile.goal} | tolerance {profile.risk_tolerance}, capacity "
             f"{profile.risk_capacity} -> effective risk {profile.effective_risk} | max single stock "
             f"{profile.max_single_stock_pct:g}% | view {view} | profile {profile.profile_hash}"]
    if is_default:
        lines.append("default profile (not set by you); set your own with --horizon / --risk-tolerance / --save-profile")
    late = presets_overdue()
    if late:
        lines.append(f"warning: weight presets review overdue (review_by {late}); treat weights as stale")
    lines += [f"scoring weights for this horizon (preset proposal, not evidence-based): {w}",
              "the profile only changes how factors are weighted in the pool score; it is not a suitability assessment. Research only, not a recommendation."]
    return lines


# ---------------------------------------------------------------------------------------------------------------------------
# Shared "how sure is this report" view. Works on the same dict shape as the JSON summary so the text, HTML and web
# renderers print identical wording. Education only; no buy/sell/target words.
# ---------------------------------------------------------------------------------------------------------------------------
SMALL_POOL = 12
FACTOR_NAMES = {"value": "Value", "quality": "Quality", "growth": "Growth", "momentum": "Momentum", "risk": "Risk"}


def _inr0(v: float) -> str:
    return f"₹{v:,.0f}" if abs(v) >= 10 else f"₹{v:,.2f}"


def _join_and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def level_formula(price: float, last: float | None, stop: float | None, targets: list[tuple[float, float]], notes: list[str] | None = None,
                  mult: float = 3.0) -> str:
    """Inline arithmetic for a reference level, or '' when it is not one of the computed ones."""
    if last is None or stop is None or stop >= last:
        return ""
    held = any("held at the 52-week low" in n for n in (notes or []))
    if abs(price - stop) < 0.005:
        if held:
            return f"{_inr0(stop)} = the 52-week low (the volatility-based stop would sit below it)"
        move = (last - stop) / mult
        return f"{_inr0(stop)} = last close {_inr0(last)} − {mult:g} × average daily move {_inr0(move)}"
    for r, t in targets:
        if abs(price - t) < 0.005:
            return f"{_inr0(t)} = last close {_inr0(last)} + {r:g} × the stop distance {_inr0(last - stop)}"
    return ""


def exec_input(fs: FactSet, as_of: date | None, scorecard: dict | None, debate, explanation, scenario, levels, stamp: dict | None = None) -> dict:
    """The parts of the JSON summary the executive block needs, built from the Python objects."""
    from indiafacts.completeness import completeness
    from indiafacts.stamp import report_stamp

    when = as_of or fs.retrieved_at.date()
    score = None
    r = (scorecard or {}).get("result")
    if r is not None:
        score = {"status": r.status, "overall": r.overall, "rank": r.rank, "n": scorecard.get("n"), "reason": r.reason,
                 "factors": {k: {"score": v.score, "coverage": v.coverage, "reason": v.reason} for k, v in r.factors.items()},
                 "contributions": {k: c.model_dump() for k, c in r.contributions.items()},
                 "missing_factors": [m.model_dump() for m in r.missing_factors], "pool_failed": len((scorecard or {}).get("failed") or {})}
    deb = None if debate is None else {"stance": {"label": debate.stance.label, "confidence": debate.stance.confidence,
                                                    "reason": debate.stance.reason, "partial": debate.stance.partial,
                                                    "evidence_note": debate.stance.evidence_note}}
    lev = None if levels is None else {"applies": levels.applies, "last_close": levels.last_close, "stop": levels.stop,
                                       "targets": [{"r": a, "price": b} for a, b in zip(levels.reward_risk, levels.targets)], "notes": levels.notes}
    ex = None if explanation is None else {"triggers": [{"text": t.text} for t in explanation.triggers]}
    st = stamp or report_stamp(fs.entity.ticker, when, (scorecard or {}).get("members") or [])
    return {"completeness": completeness(fs, when), "score": score, "debate": deb, "levels": lev, "explanation": ex, "stamp": st,
            "scenario_reason": getattr(scenario, "reason", "") if scenario is not None else ""}


LEVEL_WORDS = {"High": "Nearly all the figures we look for were found",
               "Medium": "Most figures were found; some are missing",
               "Low": "About half the figures are missing",
               "Insufficient": "Key figures are missing, so read the rating with care"}
# plain area name, and what a gap in it means for the reader
AREAS = {"price_history": ("Price history (returns, 52-week range, volatility)", "the trend and risk readings are limited"),
         "fundamentals": ("Company results (sales, profit, earnings per share)", "growth and profitability are hard to judge"),
         "valuation": ("Valuation (P/E, price-to-book, market value)", "we can't say whether the price is high or low for what the company earns"),
         "balance_sheet": ("Balance sheet (debt, cash, assets)", "we can't judge how much debt the company carries"),
         "ownership": ("Ownership (who holds the shares)", ""),
         "news": ("News", "")}
AREA_SHORT = {"price_history": "Price history", "fundamentals": "Company results", "valuation": "Valuation", "balance_sheet": "Balance sheet",
              "ownership": "Ownership", "news": "News"}
SKIP_AREAS = ("filings",)                      # official-vs-vendor is shown once, as the verification line, not as a missing area
REAL_GAP_PCT = 60                             # an area covered at or below this is a real gap


def _area_status(p: dict) -> str:
    """Status word for one area of the completeness JSON; tolerates old and new shapes."""
    pct = p.get("coverage_pct")
    if p.get("vendor_only"):
        return "Vendor estimate only"
    if pct is None:
        return ""
    if pct >= 99.95:
        return "Complete"
    n = p.get("expected_n") or 0
    got = p.get("fresh_ok")
    if got is None:
        got = round(pct / 100 * n)
    return "Not found" if pct <= 0 else f"Partly found ({got} of {n})" if n else "Partly found"


def area_items(comp: dict) -> list[tuple[str, str]]:
    return [(AREA_SHORT.get(k, v.get("label", k)), st) for k, v in (comp.get("pillars") or {}).items()
            if k not in SKIP_AREAS and (st := _area_status(v))]


def missing_items(comp: dict) -> list[str]:
    """Plain lines for areas with a real gap, worst first. Nothing is listed for an area that is mostly there."""
    rows = []
    for k, p in (comp.get("pillars") or {}).items():
        if k in SKIP_AREAS or p.get("coverage_pct") is None:
            continue
        name, effect = AREAS.get(k, (p.get("label", k), ""))
        pct = p["coverage_pct"]
        if p.get("vendor_only"):
            rows.append((pct - 0.5, "Ownership: only a data vendor's estimate, not the official exchange filing." if k == "ownership"
                         else f"{name}: only a data vendor's estimate."))
        elif pct <= REAL_GAP_PCT:
            status = "not available" if pct <= 0 else "only partly found"
            rows.append((pct, f"{name}: {status}" + (f", so {effect}." if effect else ".")))
    return [t for _, t in sorted(rows, key=lambda r: r[0])][:4]


def exec_view(s: dict) -> dict:
    """Plain-English executive block, completeness badge, score decomposition, rank caveat and stamp line from a summary-shaped dict."""
    from indiafacts.debate import has_direction

    out: dict = {}
    st = ((s.get("debate") or {}).get("stance")) or None
    label = st["label"] if st else "No rating"
    directional = has_direction(label)
    out["label"], out["directional"] = label, directional
    note = (st or {}).get("evidence_note") or ""
    out["evidence_note"] = note if directional else ""
    out["insufficient"] = bool(directional and st and (st.get("partial") or note))
    if directional:
        out["meaning"] = f"Rule-based rating: {label}, {str(st['confidence']).lower()} confidence." + (f" {note}" if note else "")
    elif st and label == "No rating":
        why = (st.get("reason") or "").strip().rstrip(".")
        out["meaning"] = (why[:1].upper() + why[1:] if why else "No rating: the score could not be computed") + "."
    else:
        out["meaning"] = "No rating: the score could not be computed."
    comp = s.get("completeness") or {}
    out["missing"] = missing_items(comp)
    out["monitor"] = [t["text"] for t in ((s.get("explanation") or {}).get("triggers") or []) if not t["text"].startswith("Needs data")][:4]
    level = comp.get("level")
    conflicts = []
    for c in comp.get("conflicts") or []:
        ch, alt = c["chosen"], c.get("alternative")
        txt = f"{c['metric']} ({c['period']}): used {ch['value']} from {ch['source']}"
        txt += (f"; other source {alt['source']} says {alt['value']}" if alt else "; no second value to compare")
        conflicts.append(txt + f". {c['reason']}" if c.get("reason") else txt)
    stale = comp.get("stale_total", 0) or 0
    out["comp"] = {"level": level, "tone": {"High": "good", "Medium": "warn", "Low": "bad", "Insufficient": "bad"}.get(level, "warn"),
                   "words": LEVEL_WORDS.get(level, ""), "items": area_items(comp),
                   "stale": f"{stale} figure{' is' if stale == 1 else 's are'} out of date" if stale > 0 else "",
                   "verification": ((comp.get("verification") or {}).get("label") or ""), "conflicts": conflicts} if level else None
    sc = s.get("score") or {}
    rows, sentence = [], ""
    for k, c in (sc.get("contributions") or {}).items():
        rows.append([FACTOR_NAMES.get(k, k.capitalize()), c["score"], c["base_weight"], c["effective_weight"], c["contribution"]])
    miss = sc.get("missing_factors") or []
    if miss:
        names = [f"{FACTOR_NAMES.get(m['factor'], m['factor'].capitalize())} ({m['base_weight']:.0%})" for m in miss]
        sentence = f"{_join_and(names)} could not be scored: {'its' if len(miss) == 1 else 'their'} weight moved to the remaining factors."
    out["decomp"] = {"rows": rows, "total": sum(r[4] for r in rows), "overall": sc.get("overall"), "sentence": sentence} if rows else None
    n, failed = sc.get("n"), sc.get("pool_failed") or 0
    notes = []
    if sc.get("rank") and n and n < SMALL_POOL:
        notes.append(f"rank {sc['rank']} of {n} in a comparison set of {n} (small: rank is unstable)")
    if failed:
        notes.append(f"{failed} of {(n or 0) + failed} comparison companies could not be loaded")
    out["rank_notes"] = notes
    sp = s.get("stamp")
    if sp:
        line = f"Report {sp['report_id']} · data as of {sp['as_of']} · rules {sp['params_hash']} · build {sp['commit']}"
        out["stamp_line"] = line + (f" · model {sp['llm_model']}" if sp.get("llm_model") else "")
    else:
        out["stamp_line"] = ""
    out["scenario_reason"] = s.get("scenario_reason") or ("no scenario plan without a rating" if not directional else "")
    return out


def exec_lines(x: dict) -> list[str]:
    lines = ["", "WHAT THIS MEANS", "  " + x["meaning"]]
    lines += ["WHAT IS MISSING"] + (["  " + m for m in x["missing"]] or ["  nothing flagged"])
    lines += ["WHAT TO MONITOR"] + (["  " + m for m in x["monitor"]] or ["  nothing specific flagged"])
    c = x["comp"]
    if c:
        lines += ["", f"HOW COMPLETE IS THE DATA: {c['words']}"]
        lines += [f"  {n}: {st}" for n, st in c["items"]]
        if c["stale"]:
            lines.append(f"  {c['stale']}")
        if c["verification"]:
            lines.append(f"  {c['verification']}")
        lines += [f"  conflict: {t}" for t in c["conflicts"]]
    return lines


def decomp_lines(x: dict) -> list[str]:
    d = x["decomp"]
    if not d:
        return []
    out = ["  score breakdown (factor | score | base weight | effective weight | contribution)"]
    out += [f"    {n} | {sc:.1f} | {b:.0%} | {e:.0%} | {co:.1f}" for n, sc, b, e, co in d["rows"]]
    out.append(f"    sum of contributions {d['total']:.1f}" + (f" = overall {d['overall']:.1f}" if d["overall"] is not None else ""))
    if d["sentence"]:
        out.append("  " + d["sentence"])
    return out


def _scorecard_block(sc: dict, x: dict | None = None) -> list[str]:
    r = sc["result"]
    pool = ("built-in pool of 30 large NSE names (not an index)" if sc.get("default_pool")
            else (sc["pool"] if str(sc["pool"]).startswith(("TejHQ", "NSE industry group")) else f"pool file {sc['pool']}"))
    lines = ["", f"SCORECARD (percentile ranks inside {sc['n']} companies from the {pool}; ordering within the pool, "
                 "not absolute quality)"]
    if r is None:
        lines.append("this company could not be scored: it is not among the loaded pool members")
    elif r.status != "ok":
        lines.append(f"abstain: {r.reason}")
    else:
        lines.append(f"overall {r.overall:.1f}/100 | rank {r.rank} of {sc['n']} | config {r.config_hash}")
        lines += [f"  note: {n}" for n in (x or {}).get("rank_notes", [])]
    if r is not None:
        for fac, fs_ in sorted(r.factors.items()):
            val = f"{fs_.score:.1f}" if fs_.score is not None else f"unav ({fs_.reason})"
            lines.append(f"  {fac}: {val} (coverage {fs_.coverage:.0%})")
        lines += decomp_lines(x) if x else []
        lines += [f"  flag: {f}" for f in r.flags]
    if sc.get("config_overdue"):
        lines.append("  warning: score metric config review overdue; treat bounds as stale")
    if sc["failed"]:
        lines.append("  not loaded: " + "; ".join(f"{t} ({why})" for t, why in sc["failed"].items()))
    lines += ["", f"CHECKLIST (project-defined, 9 pass/fail tests): {sc['checklist_summary']}"]
    from indiafacts.checklist import grouped

    for g in grouped(sc["checklist"]):
        lines.append(f" {g['group']}: {g['text']}")
        for c in sc["checklist"]:
            if c.id not in g["checks"]:
                continue
            tag = {"pass": "pass", "fail": "fail", "unavailable": "unav"}[c.result]
            detail = f"{c.display}, needs {c.threshold}" if c.value is not None else c.reason
            lines.append(f"  [{tag}] {c.label} ({detail})")
    lines.append(" each check counts once; there are no weights")
    return lines


from indiafacts.fundamentals import LENDER_REASON  # noqa: E402
from indiafacts.fundamentals_view import fundamentals_lines  # noqa: E402
from indiafacts.scenario import scenario_lines  # noqa: E402
from indiafacts.ownership_view import ownership_lines  # noqa: E402


def _prose_lines(p) -> list[str]:
    if not p.favour:
        return []
    return ["", "IN PLAIN WORDS", "  " + p.favour, "  " + p.against, "  " + p.weighing]

from indiafacts.flows import lines as flows_lines_raw  # noqa: E402
from indiafacts.peers import POSITION_TEXT  # noqa: E402


def flows_lines(flows):
    return flows_lines_raw(flows) if flows is not None else []


def peer_pick_text(p) -> str:
    """'same industry, 1.20x size'; the size part is left out when the size ratio is unknown."""
    base = "same industry" if p.tier == 1 else "same sector"
    return base if p.size_ratio is None else f"{base}, {p.size_ratio:.2f}x size"


def _peers_block(sc: dict, ticker: str) -> list[str]:
    g = sc.get("peers")
    if g is None:
        return []
    lines = ["", "PEERS (picked by rule from the loaded pool; medians use valid values only; not-meaningful P/E above 75 is left out)"]
    if g.unavailable_reason:
        return lines[:1] + [f"no peer comparison: {g.unavailable_reason}"] + [f"note: {n}" for n in g.notes]
    lines.append(f"peers used: {len(g.picks)}" + (f" (of {g.candidates} candidates in the pool)" if g.candidates else "")
                 + (f"; WARNING: fewer than 5 peers, treat as rough" if g.few_peers else ""))
    lines.append("picks: " + "; ".join(f"{p.ticker} (tier {p.tier}, {peer_pick_text(p)})" for p in g.picks))
    if g.excluded:
        lines.append("left out: " + "; ".join(f"{e.ticker} ({e.reason})" for e in g.excluded))
    lines += [f"note: {n}" for n in g.notes]
    lines += [f"| metric | {ticker} | peer median | Q1 | Q3 | vs median | position | n |", "|---|---|---|---|---|---|---|---|"]
    for c in sc.get("peer_comparisons", []):
        if c.status != "ok":
            lines.append(f"| {c.metric} | {'-' if c.target_value is None else f'{c.target_value:.3g}'} | unav | unav | unav | unav | unav | {c.n} |")
            lines.append(f"  {c.metric}: {c.reason}")
            continue
        tv = "-" if c.target_value is None else f"{c.target_value:.3g}"
        prem = (f"{c.premium:+.1%}" if c.premium is not None
                else f"{c.diff * 100:+.1f} pp" if c.diff is not None else "-")
        pos = "-" if c.higher_than is None else f"{POSITION_TEXT.get(c.position or '', '-')} (above {c.higher_than} of {c.of})"
        lines.append(f"| {c.metric} | {tv} | {c.peer_median:.3g} | {c.q1:.3g} | {c.q3:.3g} | {prem} | {pos} | {c.n} |")
    lines.append("for pe_ttm, pb and ev_ebitda a positive 'vs median' means pricier than the peer median (relative); "
                 "for roe, fy_roce, net_margin_q and net_income_yoy it is the gap in percentage points; "
                 "this is a comparison of ratios, not a statement about value or a recommendation")
    return lines


def _explanation_block(ex, digest) -> list[str]:
    lines = ["", f"EXPLANATION (generated by {ex.source}; every claim cites evidence ids; research only, not a recommendation)",
             ex.summary]
    used: list[str] = []
    for c in ex.claims:
        lines.append(f"- [{c.type} {', '.join(c.ids)}] {c.text}")
        used += c.ids
    if ex.triggers:
        lines += ["", "WHAT WOULD CHANGE THE PICTURE"]
        for t in ex.triggers:
            lines.append(f"- {t.text} [{', '.join(t.ids)}]")
            used += t.ids
    lines += ["", f"UNCERTAINTY: {ex.uncertainty}"] + [f"note: {n}" for n in ex.notes]
    seen = []
    for i in used:
        if i not in seen and i in digest.items:
            seen.append(i)
    lines += ["", "Evidence index"] + [f"{i} {digest.items[i].text}" for i in sorted(seen, key=lambda x: int(x[1:]))]
    u = ex.usage
    if not u:
        use = "no LLM call (deterministic template)"
    elif u.get("cached"):
        use = f"cached response: 0 new tokens (saved in {u['in']}, out {u['out']})"
    else:
        use = f"LLM call: in {u['in']}, out {u['out']}" + (" (estimated)" if u.get("estimated") else "")
    if u:
        from indiafacts.digest import est_tokens
        from indiafacts.llm import SYSTEM_PROMPT

        ins = est_tokens(SYSTEM_PROMPT)
        lines.append(f"tokens: prompt ~{ins + digest.est_tokens} estimated tokens (instructions ~{ins} + digest ~{digest.est_tokens}); {use}")
    else:
        lines.append(f"tokens: digest ~{digest.est_tokens} estimated tokens; {use}")
    return lines


def _changes_block(changes, note) -> list[str]:
    if not changes and not note:
        return []
    lines = ["", "WHAT CHANGED SINCE THE LAST RUN (the app keeps every version of every figure)"]
    if not changes:
        return lines + [note]
    lines += [f"- [{c.severity}] {c.kind}: {c.text}" for c in changes]
    return lines


def _filings_block(filings) -> list[str]:
    if not filings:
        return []
    lines = ["", "FILINGS USED (official pages; the latest by filing date is the current version)"]
    for m in filings:
        lines.append(f"- {m.document} | filed {m.filing_date} | period {m.period_end} | {m.basis} | {m.audit_status or 'audit status unknown'}"
                     f" | rounding {m.rounding or 'unknown'} | revision: {m.revision_note}")
    return lines


def _debate_block(d) -> list[str]:
    out = ["", "BULL CASE VERSUS BEAR CASE (educational; rule-based from the evidence above)"]
    out += ["bull:"] + ([f"  + {p.text}" for p in d.bull] or ["  (none found)"])
    out += ["bear:"] + ([f"  - {p.text}" for p in d.bear] or ["  (none found)"])
    if d.stance.label == "No rating":
        out.append(f"EDUCATIONAL RATING: No rating. {d.stance.reason}.")
    else:
        tag = " [Insufficient evidence]" if d.stance.partial else ""
        out.append(f"EDUCATIONAL RATING: {d.stance.label}{tag} (confidence {d.stance.confidence}). {d.stance.reason}.")
    return out


def _levels_block(lv, panel, scenario=None, directional: bool = True) -> list[str]:
    out = ["", "REFERENCE LEVELS (NOT TARGETS) AND RISK LENSES (arithmetic on past closes; not predictions, not price targets, not personal advice)"]
    if not directional:
        return out + [f"not shown: {getattr(scenario, 'reason', '') or 'there is no rating'}"]
    if getattr(scenario, "evidence_note", ""):
        out.append(scenario.evidence_note)
    if lv.last_close is None:
        return out + [f"unavailable: {lv.reason}"]
    inr = lambda v: f"₹{v:,.2f}"
    out.append(f"last close {inr(lv.last_close)}")
    out += [f"support: {n} {inr(v)}" for n, v in lv.support] + [f"resistance: {n} {inr(v)}" for n, v in lv.resistance]
    if lv.applies:
        tg = list(zip(lv.reward_risk, lv.targets))
        out.append(f"reference stop {inr(lv.stop)} ({lv.risk_pct:.1f}% below the last close): "
                   + (level_formula(lv.stop, lv.last_close, lv.stop, tg, lv.notes) or ""))
        out += [f"reference level at {r:g}x the risk {inr(t)}: {level_formula(t, lv.last_close, lv.stop, tg, lv.notes)}" for r, t in tg]
        out += [f"note: {n}" for n in lv.notes]
    else:
        out.append(f"stop and reward-to-risk levels: not shown ({lv.reason})")
    if panel is not None:
        out.append("risk lenses (limits are proposals; the lens matching your profile is marked):")
        for l in panel.lenses:
            mark = " <- your profile" if l.name == panel.profile_lens else ""
            if l.fits is None:
                out.append(f"  {l.name}: not applied ({l.reason}){mark}")
                continue
            size = f"; position ceiling {l.max_position_pct:.1f}% of a portfolio" if l.max_position_pct is not None else ""
            out.append(f"  {l.name}: {'within limits' if l.fits else 'breaches: ' + '; '.join(l.breaches)}{size}{mark}")
        out += [f"  note: {n}" for n in panel.notes]
    return out


def _news_block(items) -> list[str]:
    out = ["", "RECENT HEADLINES (NSE announcements first, then third-party text that names the company; unverified; keyword hints only, not analysis)"]
    for n in items:
        when = n.published.date().isoformat() if n.published else "undated"
        src = f"NSE announcement{': ' + n.category if n.category else ''}" if n.source_kind == "exchange" else "third-party headline"
        out.append(f"- {when} {n.publisher} ({src}): {n.title} [{n.sentiment_hint}; event type, keyword guess: {n.event_type}]")
    return out


def _valuation_block(facts: Sequence[Fact], refs: _Refs) -> list[str]:
    v = [f for f in facts if f.source == "computed:valuation"]
    if not v:
        return []
    ok = [f for f in v if f.status == Status.ok]
    out = ["", "WHAT THE PRICE IMPLIES (arithmetic under stated assumptions; not a forecast, a fair value or a target)"]
    if not ok:
        return out + [f"unavailable: {v[0].reason}"]
    from indiafacts.valuation import load_valuation_params

    p = load_valuation_params(strict=False)
    if ok[0].metric.startswith("implied_growth"):
        out.append(f"assumptions: discount rates {', '.join(f'{r:.0%}' for r in p['discount_rates'])}; explicit years {', '.join(map(str, p['horizons']))}; "
                   f"terminal growth {p['terminal_growth']:.0%}; earnings-based; reviewed {p['reviewed_on']}, review by {p['review_by']}")
    else:
        out.append(f"assumptions: {ok[0].source_field}")
    if ok[0].metric.startswith("implied_growth"):
        out.append("annual earnings growth the current price would need to be explained, by discount rate and years (earnings treated as distributable):")
        rows: dict[str, dict[int, Fact]] = {}
        for f in ok:
            rows.setdefault(f.metric.split("_")[2], {})[int(f.metric.split("_")[3][1:])] = f
        years = sorted({y for d in rows.values() for y in d})
        out += ["| discount rate | " + " | ".join(f"{y} years" for y in years) + " |", "|---|" + "---|" * len(years)]
        for r in sorted(rows, key=lambda x: int(x[1:])):
            out.append(f"| {r[1:]}% | " + " | ".join((f"{float(rows[r][y].value):.1f}% a year [{refs.ref(rows[r][y])}]" if y in rows[r] else "n/a") for y in years) + " |")
    else:
        lo = next(f for f in ok if f.metric == "justified_pb_low")
        hi = next(f for f in ok if f.metric == "justified_pb_high")
        out.append(f"price-to-book that the stated ROE and assumptions would support: {float(lo.value):.2f} to {float(hi.value):.2f} [{refs.ref(lo)}, {refs.ref(hi)}]")
    return out


def render(factset: FactSet, as_of: date | None = None, profile=None, profile_is_default: bool = False,
           view: str = "pro", scorecard: dict | None = None, explanation=None, digest=None, changes=None, changes_note=None,
           debate=None, news=None, levels=None, panel=None, flows=None, scenario=None, prose=None, stamp=None) -> str:
    e = factset.entity
    when = as_of or factset.retrieved_at.date()
    head = f"{e.ticker}  |  as of {when}  |  amounts in INR (₹ crore = 10^7)"
    notes = ["", "NOTICES"] + [f"- {n}" for n in factset.notices] if factset.notices else []
    if e.resolution != "resolved":
        return "\n".join([head, *notes, "", f"No data: {e.resolution_reason}", "", DISCLAIMER])
    facts = factset.facts
    bases = sorted({str(f.basis.value) for f in facts}) or ["unknown"]
    head += f"  |  basis: {', '.join(bases)}"
    if e.isin.value:
        head += f"  |  ISIN {e.isin.value}"

    from indiafacts.debate import has_direction

    x = exec_view(exec_input(factset, as_of, scorecard, debate, explanation, scenario, levels, stamp))
    directional = debate is None or has_direction(debate.stance.label)
    bad = [f for f in facts if f.status in (Status.gap, Status.unavailable, Status.conflict, Status.unverified) and f.reason != LENDER_REASON]
    refs = _Refs()
    parts = [head, *notes, *exec_lines(x), *(_profile_block(profile, profile_is_default, view) if profile else []),
             *_filings_block(factset.filings),
             *_changes_block(changes, changes_note),
             *(_explanation_block(explanation, digest) if explanation is not None else []),
             *(_scorecard_block(scorecard, x) if scorecard else []),
             *(_peers_block(scorecard, e.ticker) if scorecard else []),
             *fundamentals_lines(factset),
             *ownership_lines(factset),
             *flows_lines(flows),
             *(_debate_block(debate) if debate is not None else []),
             *(_prose_lines(prose) if prose is not None else []),
             *(scenario_lines(scenario, levels) if scenario is not None else []),
             *([f"SCENARIO PLAN: not shown: {x['scenario_reason']}"] if not directional else []),
             *(_levels_block(levels, panel, scenario, directional) if levels is not None else []),
             *(_news_block(news) if news else []),
             "", f"DATA QUALITY: {len(bad)} item(s) need attention (gaps, unavailable, conflicts, unverified)"]

    parts += ["", "QUARTERLY (Yahoo; availability dates are deadline estimates)", render_table([f for f in facts if view == "pro" or not (f.metric in PRO_ONLY or f.metric.startswith("segment_"))], refs)]

    overview = [f for f in facts if f.period_type == PeriodType.point and f.status == Status.ok
                and not f.source.startswith("computed")]
    if overview:
        parts += ["", "OVERVIEW (live snapshot)"]
        parts += [f"{f.metric}: {_fmt(f)} [{refs.ref(f)}]" for f in overview]

    computed = [f for f in facts if f.source == "computed" and not _is_price(f)]
    if computed:
        parts += ["", "COMPUTED CHECKS"]
        for f in computed:
            val = f"{_fmt(f)} [{refs.ref(f)}]" if f.value is not None else f"unavailable: {f.reason}"
            parts.append(f"{f.metric} {f.fiscal_label or f.period_end}: {val}"
                         + (f" ({f.reason})" if f.value is not None and f.reason else ""))

    vendor = [f for f in facts if f.status == Status.unverified and not _is_price(f)]
    if vendor:
        parts += ["", "UNVERIFIED VENDOR FIGURES"]
        parts += [f"{f.metric}: {_fmt(f)} [{refs.ref(f)}] - {f.reason}" for f in vendor]

    pf = {f.metric: f for f in facts if _is_price(f)}
    if pf:
        parts += ["", "PRICE HISTORY (price returns; dividends excluded; Nifty 50 = price index)"]
        parts += [f"- {n}" for n in factset.price_notes]
        parts += ["| window | stock | Nifty 50 | relative | max drawdown |", "|---|---|---|---|---|"]
        for n in (1, 3, 5):
            cells = [_cell(pf.get(f"{m}_{n}y"), refs) for m in ("return", "benchmark_return", "relative_return", "max_drawdown")]
            parts.append(f"| {n}y | " + " | ".join(cells) + " |")
        for m in ("high_52w", "low_52w", "pct_from_52w_high", "volatility_1y", "beta_1y", "beta_3y"):
            if m in pf:
                parts.append(f"{m}: {_cell(pf[m], refs)}")
        parts += [f"note: {pf[m].metric}: {pf[m].reason}" for m in pf if pf[m].status == Status.unverified][:1]

    parts += _valuation_block(facts, refs)

    parts += ["", "Could not check"]
    missing = [f for f in facts if f.status == Status.unavailable and f.period_type != PeriodType.Q and f.source != "computed:valuation"]
    vmissing = [f for f in facts if f.status == Status.unavailable and f.source == "computed:valuation"]
    parts += [f"- {f.metric}: {f.reason}" for f in missing]
    if vmissing:
        parts.append(f"- price-implied valuation: {vmissing[0].reason}")
    if not missing and not vmissing:
        parts.append("- none")

    pending = [f for f in factset.not_yet_public if f.period_type == PeriodType.Q]
    if pending:
        parts += ["", "Not yet public (as of the date above)"]
        parts += [f"- {f.fiscal_label} {f.metric}: public from {f.available_from} "
                  f"({f.availability_kind.value.replace('_', ' ')})" for f in pending]

    if refs.index():
        parts += ["", "SOURCES", refs.index()]
    parts += ["", DISCLAIMER]
    if x["stamp_line"]:
        parts.append(x["stamp_line"])
    return "\n".join(parts)
