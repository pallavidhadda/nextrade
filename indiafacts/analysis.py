"""Pure functions over Facts: duplicates, gaps, TTM, growth. No I/O."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from indiafacts.availability import with_availability
from indiafacts.calendar import expected_quarter_ends, fiscal_label
from indiafacts.models import Fact, FactSet, PeriodType, Status

COMPUTED = "computed"


def _quarters(facts: list[Fact], metric: str) -> list[Fact]:
    return [f for f in facts if f.metric == metric and f.period_type == PeriodType.Q]


def resolve_duplicates(facts: list[Fact]) -> list[Fact]:
    groups: dict[tuple, list[Fact]] = defaultdict(list)
    order: list[tuple] = []
    for f in facts:
        k = (f.metric, f.period_end, f.period_type, f.source)
        if k not in groups:
            order.append(k)
        groups[k].append(f)
    out = []
    for k in order:
        g = groups[k]
        values = {f.value for f in g}
        if len(values) == 1:
            out.append(g[0])
        else:
            shown = " vs ".join(str(f.value) for f in g)
            out.append(g[0].with_(status=Status.conflict,
                                  reason=f"duplicate period with differing values: {shown}",
                                  related_fact_ids=sorted({f.fact_id for f in g})))
    return out


def detect_gaps(facts: list[Fact], metric: str) -> list[Fact]:
    qs = _quarters(facts, metric)
    if not qs:
        return []
    have = {f.period_end for f in qs}
    ref = qs[0]
    gaps = []
    for end in expected_quarter_ends(min(have), max(have)):
        if end not in have:
            gaps.append(Fact.make(
                entity_key=ref.entity_key, metric=metric, value=None, unit=ref.unit,
                period_end=end, period_type=PeriodType.Q, fiscal_label=fiscal_label(end, "Q"),
                source=ref.source, retrieved_at=ref.retrieved_at, status=Status.gap,
                reason=f"period not returned by {ref.source}",
            ))
    return with_availability(gaps)


def add_gaps(factset: FactSet) -> FactSet:
    facts = resolve_duplicates(factset.facts)
    extra = []
    for metric in sorted({f.metric for f in facts if f.period_type == PeriodType.Q}):
        extra.extend(detect_gaps(facts, metric))
    return factset.model_copy(update={"facts": facts + extra})


def _unavailable(ref: Fact, metric: str, period_end: date, ptype: PeriodType, unit: str, reason: str,
                 related: list[str] | None = None) -> Fact:
    return Fact.make(
        entity_key=ref.entity_key, metric=metric, value=None, unit=unit, period_end=period_end,
        period_type=ptype, source=COMPUTED, retrieved_at=ref.retrieved_at, status=Status.unavailable,
        reason=reason, related_fact_ids=related or [],
    )


def ttm(facts: list[Fact], metric: str, as_of_period: date) -> Fact:
    qs = [f for f in _quarters(facts, metric) if f.period_end <= as_of_period and f.status == Status.ok]
    ref = (_quarters(facts, metric) or facts)[0]
    name = f"{metric}_ttm"
    if len(qs) < 4:
        return _unavailable(ref, name, as_of_period, PeriodType.TTM, ref.unit,
                            "fewer than 4 quarters returned")
    wanted = expected_quarter_ends(date(as_of_period.year - 2, 1, 1), as_of_period)[-4:]
    by_end = {f.period_end: f for f in qs}
    missing = [d for d in wanted if d not in by_end]
    if missing:
        return _unavailable(ref, name, as_of_period, PeriodType.TTM, ref.unit,
                            "missing quarter(s): " + ", ".join(d.isoformat() for d in missing),
                            [by_end[d].fact_id for d in wanted if d in by_end])
    parts = [by_end[d] for d in wanted]
    return Fact.make(
        entity_key=ref.entity_key, metric=name, value=sum((p.value for p in parts), Decimal(0)),
        unit=ref.unit, period_end=as_of_period, period_type=PeriodType.TTM, source=COMPUTED,
        retrieved_at=ref.retrieved_at, status=Status.ok, related_fact_ids=[p.fact_id for p in parts],
    )


def growth_yoy(facts: list[Fact], metric: str, period_end: date) -> Fact:
    qs = {f.period_end: f for f in _quarters(facts, metric)}
    prior_end = date(period_end.year - 1, period_end.month, period_end.day)
    cur, base = qs.get(period_end), qs.get(prior_end)
    ref = cur or base or (_quarters(facts, metric) or facts)[0]
    name = f"{metric}_yoy"
    if cur is None or base is None or cur.status != Status.ok or base.status != Status.ok:
        return _unavailable(ref, name, period_end, PeriodType.Q, "ratio",
                            "current or prior-year quarter unavailable")
    if base.value <= 0:
        return _unavailable(ref, name, period_end, PeriodType.Q, "ratio", "base not positive",
                            [cur.fact_id, base.fact_id])
    return Fact.make(
        entity_key=ref.entity_key, metric=name, value=cur.value / base.value - 1, unit="ratio",
        period_end=period_end, period_type=PeriodType.Q, source=COMPUTED, retrieved_at=ref.retrieved_at,
        status=Status.ok, related_fact_ids=[cur.fact_id, base.fact_id],
    )
