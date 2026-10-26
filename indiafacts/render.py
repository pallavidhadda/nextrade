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
                f"retrieved {f.retrieved_at.date()}"
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
    qs = prefer_sources([f for f in facts if f.period_type == PeriodType.Q and f.source != "computed"])
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
              "profile fit: not scored yet (scoring layer not built). Research only, not a recommendation."]
    return lines


def _scorecard_block(sc: dict) -> list[str]:
    r = sc["result"]
    pool = ("built-in pool of 30 large NSE names (not an index)" if sc.get("default_pool")
            else (sc["pool"] if str(sc["pool"]).startswith("TejHQ") else f"pool file {sc['pool']}"))
    lines = ["", f"SCORECARD (percentile ranks inside {sc['n']} companies from the {pool}; ordering within the pool, "
                 "not absolute quality)"]
    if r is None:
        lines.append("this company could not be scored: it is not among the loaded pool members")
    elif r.status != "ok":
        lines.append(f"abstain: {r.reason}")
    else:
        lines.append(f"overall {r.overall:.1f}/100 | rank {r.rank} of {sc['n']} | config {r.config_hash}")
    if r is not None:
        for fac, fs_ in sorted(r.factors.items()):
            val = f"{fs_.score:.1f}" if fs_.score is not None else f"unav ({fs_.reason})"
            lines.append(f"  {fac}: {val} (coverage {fs_.coverage:.0%})")
        lines += [f"  flag: {f}" for f in r.flags]
    if sc.get("config_overdue"):
        lines.append("  warning: score metric config review overdue; treat bounds as stale")
    if sc["failed"]:
        lines.append("  not loaded: " + "; ".join(f"{t} ({why})" for t, why in sc["failed"].items()))
    lines += ["", f"CHECKLIST (project-defined, 9 pass/fail tests): {sc['checklist_summary']}"]
    for c in sc["checklist"]:
        tag = {"pass": "pass", "fail": "fail", "unavailable": "unav"}[c.result]
        detail = f"{c.display}, needs {c.threshold}" if c.value is not None else c.reason
        lines.append(f"  [{tag}] {c.label} ({detail})")
    return lines


def _peers_block(sc: dict, ticker: str) -> list[str]:
    g = sc.get("peers")
    if g is None:
        return []
    lines = ["", "PEERS (picked by rule from the loaded pool; medians use valid values only; not-meaningful P/E above 75 is left out)"]
    if g.unavailable_reason:
        return lines[:1] + [f"no peer comparison: {g.unavailable_reason}"] + [f"note: {n}" for n in g.notes]
    lines.append("picks: " + "; ".join(f"{p.ticker} (tier {p.tier}, {'same industry' if p.tier == 1 else 'same sector'}, "
                                         f"{p.size_ratio:.2f}x size)" for p in g.picks))
    if g.excluded:
        lines.append("left out: " + "; ".join(f"{e.ticker} ({e.reason})" for e in g.excluded))
    lines += [f"note: {n}" for n in g.notes]
    lines += [f"| metric | {ticker} | peer median | vs median | position | n |", "|---|---|---|---|---|---|"]
    for c in sc.get("peer_comparisons", []):
        if c.status != "ok":
            lines.append(f"| {c.metric} | {'-' if c.target_value is None else f'{c.target_value:.3g}'} | unav | unav | unav | {c.n} |")
            lines.append(f"  {c.metric}: {c.reason}")
            continue
        tv = "-" if c.target_value is None else f"{c.target_value:.3g}"
        prem = (f"{c.premium:+.1%}" if c.premium is not None
                else f"{c.diff * 100:+.1f} pp" if c.diff is not None else "-")
        pos = "-" if c.higher_than is None else f"above {c.higher_than} of {c.of}"
        lines.append(f"| {c.metric} | {tv} | {c.peer_median:.3g} | {prem} | {pos} | {c.n} |")
    lines.append("for pe_ttm and pb a positive 'vs median' means pricier than the peer median (relative); "
                 "for roe, net_margin_q and net_income_yoy it is the gap in percentage points; "
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


def render(factset: FactSet, as_of: date | None = None, profile=None, profile_is_default: bool = False,
           view: str = "pro", scorecard: dict | None = None, explanation=None, digest=None) -> str:
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

    bad = [f for f in facts if f.status in (Status.gap, Status.unavailable, Status.conflict, Status.unverified)]
    refs = _Refs()
    parts = [head, *notes, *(_profile_block(profile, profile_is_default, view) if profile else []),
             *(_explanation_block(explanation, digest) if explanation is not None else []),
             *(_scorecard_block(scorecard) if scorecard else []),
             *(_peers_block(scorecard, e.ticker) if scorecard else []),
             "", f"DATA QUALITY: {len(bad)} item(s) need attention (gaps, unavailable, conflicts, unverified)"]

    parts += ["", "QUARTERLY (Yahoo; availability dates are deadline estimates)", render_table([f for f in facts if view == "pro" or not (f.metric in PRO_ONLY or f.metric.startswith("segment_"))], refs)]

    overview = [f for f in facts if f.period_type == PeriodType.point and f.status == Status.ok
                and f.source != "computed"]
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

    parts += ["", "Could not check"]
    missing = [f for f in facts if f.status == Status.unavailable and f.period_type != PeriodType.Q]
    parts += [f"- {f.metric}: {f.reason}" for f in missing] or ["- none"]

    pending = [f for f in factset.not_yet_public if f.period_type == PeriodType.Q]
    if pending:
        parts += ["", "Not yet public (as of the date above)"]
        parts += [f"- {f.fiscal_label} {f.metric}: public from {f.available_from} "
                  f"({f.availability_kind.value.replace('_', ' ')})" for f in pending]

    if refs.index():
        parts += ["", "SOURCES", refs.index()]
    parts += ["", DISCLAIMER]
    return "\n".join(parts)
