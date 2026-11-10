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
    if not facts:
        raise ValueError("ttm needs at least one fact")
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


def comparability_check(cur: Fact, base: Fact) -> tuple[list[str], list[str]]:
    """Is cur / base a fair growth comparison? Returns (issues that block verification, notes that only caveat it)."""
    issues: list[str] = []
    notes: list[str] = []
    if cur.metric != base.metric:
        issues.append(f"different metrics ({cur.metric} vs {base.metric})")
    gap = (cur.period_end - base.period_end).days
    if cur.period_type != base.period_type or abs(gap - 365) > 7:
        issues.append(f"periods not comparable ({base.fiscal_label or base.period_end} {base.period_type.value} to "
                      f"{cur.fiscal_label or cur.period_end} {cur.period_type.value}, {gap} days apart)")
    if cur.unit != base.unit:
        issues.append(f"units differ ({cur.unit} vs {base.unit})")
    if cur.source != base.source:
        issues.append(f"sources differ ({cur.source} vs {base.source}); definitions may differ")
    if cur.basis != base.basis:
        issues.append(f"basis differs ({cur.basis.value} vs {base.basis.value})")
    elif cur.basis.value == "unknown":
        notes.append("basis not stated by the source (same source and series)")
    if cur.restated == "yes" or base.restated == "yes":
        issues.append("a figure was restated")
    elif cur.restated == "unknown" or base.restated == "unknown":
        notes.append("restatement status unknown")
    if not cur.evidence or not base.evidence:
        issues.append("evidence not traceable for one of the figures")
    return issues, notes


def growth_yoy(facts: list[Fact], metric: str, period_end: date) -> Fact:
    if not facts:
        raise ValueError("growth_yoy needs at least one fact")
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
    issues, notes = comparability_check(cur, base)
    return Fact.make(
        entity_key=ref.entity_key, metric=name, value=cur.value / base.value - 1, unit="ratio",
        period_end=period_end, period_type=PeriodType.Q, source=COMPUTED, retrieved_at=ref.retrieved_at,
        status=Status.unverified if issues else Status.ok, reason="; ".join(issues + notes),
        related_fact_ids=[cur.fact_id, base.fact_id],
    )


def reconcile_price(price: Fact, pe: Fact, eps: Fact, tol: float = 0.01) -> Fact:
    related = [price.fact_id, pe.fact_id, eps.fact_id]
    name = "price_pe_eps_check"

    def out(status: Status, value: Decimal | None, reason: str = "") -> Fact:
        return Fact.make(
            entity_key=price.entity_key, metric=name, value=value, unit="ratio",
            period_end=price.period_end, period_type=PeriodType.point, source=COMPUTED,
            retrieved_at=price.retrieved_at, status=status, reason=reason, related_fact_ids=related,
        )

    if any(f.status not in (Status.ok, Status.unverified) or f.value is None for f in (price, pe, eps)):
        return out(Status.unavailable, None, "price, P/E or EPS unavailable")
    if eps.value <= 0:
        return out(Status.unavailable, None, "EPS not positive; P/E check not meaningful")
    implied = pe.value * eps.value
    diff = abs(implied - price.value) / price.value
    if diff <= Decimal(str(tol)):
        return out(Status.ok, diff)
    return out(Status.conflict, diff,
               f"P/E x EPS implies {implied:.2f} but price is {price.value:.2f} (off {diff:.1%})")


def reconcile_sources(a: Fact, b: Fact, tol: float = 0.05) -> list[Fact]:
    if a.value is None or b.value is None or a.value == 0:
        return [a, b]
    spread = abs(b.value - a.value) / abs(a.value)
    if spread <= Decimal(str(tol)):
        return [a, b]
    reason = f"{a.source} {a.value} vs {b.source} {b.value}: sources differ by {spread:.1%}"
    return [
        a.with_(status=Status.conflict, reason=reason, related_fact_ids=[b.fact_id]),
        b.with_(status=Status.conflict, reason=reason, related_fact_ids=[a.fact_id]),
    ]


DEFINITION_PREFIX = "different definition: "


def cross_check(a: Fact, b: Fact, tol: float = 0.05, definition: str = "") -> Fact:
    """One computed Fact stating whether two sources agree on the same metric and period. When the two sources are known to define
    the figure differently (`definition` says how), a gap is not a disagreement: the check is ok and its reason starts with
    DEFINITION_PREFIX so reports can list it separately."""
    related = [a.fact_id, b.fact_id]
    spread = abs(b.value - a.value) / abs(a.value) if a.value else None
    ok = spread is not None and spread <= Decimal(str(tol))
    reason = "" if ok else (
        f"{a.source} {a.value} vs {b.source} {b.value}: sources differ by {spread:.1%}"
        if spread is not None else "reference value is zero")
    if definition and not ok and spread is not None:
        ok, reason = True, f"{DEFINITION_PREFIX}{definition} ({a.source} {a.value} vs {b.source} {b.value}, {spread:.1%} apart)"
    return Fact.make(
        entity_key=a.entity_key, metric=f"{a.metric}_source_check", value=spread, unit="ratio",
        period_end=a.period_end, period_type=a.period_type, fiscal_label=a.fiscal_label, source=COMPUTED,
        retrieved_at=a.retrieved_at, status=Status.ok if ok else (Status.conflict if spread is not None else Status.unavailable),
        reason=reason, related_fact_ids=related,
    )


SOURCE_RANK = ("nse_filing", "nse_xbrl", "computed:filing_ebitda", "nse_shp", "nse_marketlens", "computed:selfvalue", "yahoo")   # official filing, exchange screener, our own arithmetic, then the vendor


def prefer_sources(facts: list[Fact]) -> list[Fact]:
    """One Fact per (metric, period, type): the best-ranked source wins (official filing over vendor)."""
    def rank(f: Fact) -> int:
        return SOURCE_RANK.index(f.source) if f.source in SOURCE_RANK else len(SOURCE_RANK)

    best: dict[tuple, Fact] = {}
    for f in facts:
        k = (f.metric, f.period_end, f.period_type)
        if k not in best or rank(f) < rank(best[k]):
            best[k] = f
    return list(best.values())


def check_ebitda(filing_facts: list[Fact], vendor_facts: list[Fact]) -> tuple[list[Fact], dict[str, Fact]]:
    """Derive EBITDA from filing lines (PBT + finance costs + depreciation) and test the vendor's EBITDA.

    Returns (new computed facts, replacements keyed by fact_id). A vendor series that equals
    PBT + finance costs (EBIT) is demoted to `unverified` for every period.
    """
    def one(metric: str, end: date, basis=None) -> Fact | None:
        hits = [f for f in filing_facts if f.metric == metric and f.period_end == end
                and f.period_type == PeriodType.Q and f.status == Status.ok and (basis is None or f.basis == basis)]
        return hits[0] if hits else None

    new: list[Fact] = []
    demote: dict[str, Fact] = {}
    for end in sorted({f.period_end for f in filing_facts if f.period_type == PeriodType.Q}):
        pbt = one("profit_before_tax", end)
        interest, dep = (one("interest_expense", end, pbt.basis), one("depreciation", end, pbt.basis)) if pbt else (None, None)
        if not (pbt and interest and dep):
            continue
        derived = Fact.make(
            entity_key=pbt.entity_key, metric="ebitda_derived", value=pbt.value + interest.value + dep.value,
            unit="INR", period_end=end, period_type=PeriodType.Q, fiscal_label=pbt.fiscal_label, basis=pbt.basis,
            source=COMPUTED, retrieved_at=pbt.retrieved_at, status=Status.ok,
            related_fact_ids=[pbt.fact_id, interest.fact_id, dep.fact_id],
        )
        same_basis = pbt.basis == interest.basis == dep.basis
        if same_basis:                                              # same filing period and basis: the figure vendors often call EBITDA
            ref = Fact.make(
                entity_key=pbt.entity_key, metric="ebitda", value=derived.value, unit="INR", period_end=end,
                period_type=PeriodType.Q, fiscal_label=pbt.fiscal_label, basis=pbt.basis, source="computed:filing_ebitda",
                source_field="profit_before_tax + interest_expense + depreciation", retrieved_at=pbt.retrieved_at,
                status=Status.ok, available_from=pbt.available_from, availability_kind=pbt.availability_kind,
                reason="EBITDA = profit before tax + finance costs + depreciation & amortisation, all from the same filing",
                related_fact_ids=[pbt.fact_id, interest.fact_id, dep.fact_id])
            new.append(ref)                                         # the filing EBITDA replaces ebitda_derived for this period
        else:
            ref = derived
            new.append(derived)                                     # mixed bases: only the derived figure, labelled as such
        vend = [f for f in vendor_facts if f.metric == "ebitda" and f.period_end == end
                and f.period_type == PeriodType.Q and f.status == Status.ok]
        if not vend:
            continue
        chk = cross_check(ref, vend[0])
        ebit = pbt.value + interest.value
        if chk.status == Status.conflict and abs(vend[0].value - ebit) <= abs(ebit) * Decimal("0.001"):
            chk = cross_check(ref, vend[0], definition=(f"{vend[0].source} 'EBITDA' equals profit before tax + finance costs (EBIT); "
                                                          f"depreciation is not added back (filing EBITDA {derived.value})"))
            note = f"appears to be EBIT, not EBITDA (checked against {pbt.fiscal_label} filing); series not trusted"
            for f in vendor_facts:
                if f.metric == "ebitda" and f.period_type == PeriodType.Q and f.value is not None:
                    demote[f.fact_id] = f.with_(status=Status.unverified, reason=note)
        new.append(chk)
    return new, demote


def margin_latest(facts: list[Fact], numerator: str, denominator: str, name: str) -> Fact | None:
    """Latest quarter where both inputs are ok: numerator / denominator (e.g. net margin)."""
    nums = {f.period_end: f for f in _quarters(facts, numerator) if f.status == Status.ok}
    dens = {f.period_end: f for f in _quarters(facts, denominator) if f.status == Status.ok}
    common = sorted(set(nums) & set(dens))
    if not common:
        return None
    end = common[-1]
    n, d = nums[end], dens[end]
    base = dict(entity_key=n.entity_key, metric=name, unit="ratio", period_end=end, period_type=PeriodType.Q,
                fiscal_label=n.fiscal_label, source=COMPUTED, retrieved_at=n.retrieved_at,
                related_fact_ids=[n.fact_id, d.fact_id])
    if d.value == 0:
        return Fact.make(value=None, status=Status.unavailable, reason=f"{denominator} is zero", **base)
    return Fact.make(value=n.value / d.value, status=Status.ok, **base)
