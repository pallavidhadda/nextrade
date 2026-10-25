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


def render(factset: FactSet, as_of: date | None = None) -> str:
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
    parts = [head, *notes, "", f"DATA QUALITY: {len(bad)} item(s) need attention (gaps, unavailable, conflicts, unverified)"]

    parts += ["", "QUARTERLY (Yahoo; availability dates are deadline estimates)", render_table(facts, refs)]

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
