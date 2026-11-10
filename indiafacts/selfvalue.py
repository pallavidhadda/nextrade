"""Valuation figures we compute ourselves from filed data, so they do not depend on the vendor's overview.

market cap = last close x shares outstanding; EPS (TTM) = four reported quarters' EPS (or TTM net profit to owners / shares);
P/E = last close / EPS (TTM); P/B = market cap / equity attributable to owners (latest filed balance sheet).
Shares come from the official shareholding pattern when it states them, else from Yahoo. Metric names match the ones scoring reads
(market_cap, eps_ttm, pe_ttm, pb). Where the vendor also states one of them and the two differ by more than 5%, cross_check
flags a conflict and both Facts stay. Pure functions; no I/O. Education only; not financial advice."""
from __future__ import annotations

from decimal import Decimal

from indiafacts.analysis import cross_check
from indiafacts.models import Fact, PeriodType, Status

SOURCE = "computed:selfvalue"
SHARES_SOURCES = ("nse_shp", "yahoo")           # official first


def _ok(facts: list[Fact], metric: str, kinds=(PeriodType.point,), sources: tuple[str, ...] | None = None) -> Fact | None:
    c = [f for f in facts if f.metric == metric and f.period_type in kinds and f.status == Status.ok and f.value is not None
         and (sources is None or f.source in sources)]
    return max(c, key=lambda f: (f.period_end, f.retrieved_at)) if c else None


def pick_shares(facts: list[Fact]) -> Fact | None:
    for src in SHARES_SOURCES:
        f = _ok(facts, "shares_outstanding", sources=(src,))
        if f is not None and f.value > 0:
            return f
    return None


def self_valuation_facts(facts: list[Fact]) -> list[Fact]:
    """New Facts (computed ones plus source checks against the vendor). Inputs that are missing yield no Fact."""
    lc = _ok(facts, "last_close")
    shares = pick_shares(facts)
    if lc is None or shares is None:
        return []
    out: list[Fact] = []

    def make(metric, value, unit, period_type, period_end, formula, related, ref=lc):
        return Fact.make(entity_key=ref.entity_key, metric=metric, value=value, unit=unit, period_end=period_end,
                         period_type=period_type, source=SOURCE, source_field=formula, retrieved_at=ref.retrieved_at,
                         status=Status.ok if value is not None else Status.unavailable, related_fact_ids=related,
                         reason=formula if value is not None else "")

    mcap_v = lc.value * shares.value
    mcap = make("market_cap", mcap_v, "INR", PeriodType.point, lc.period_end,
                f"last close {lc.value} x shares outstanding {shares.value} ({shares.source})", [lc.fact_id, shares.fact_id])
    out.append(mcap)

    eps = _ok(facts, "eps_diluted_ttm", (PeriodType.TTM,))
    if eps is not None:
        eps_v, eps_rel, eps_how = eps.value, [eps.fact_id], f"sum of four reported quarters' diluted EPS {eps.value}"
    else:
        ni = _ok(facts, "net_income_ttm", (PeriodType.TTM,))
        eps_v, eps_rel, eps_how = ((ni.value / shares.value, [ni.fact_id, shares.fact_id], f"TTM net profit {ni.value} / shares {shares.value}")
                                   if ni is not None else (None, [], ""))
    if eps_v is not None:
        eps_f = make("eps_ttm", eps_v, "INR_per_share", PeriodType.point, lc.period_end, eps_how, eps_rel)
        out.append(eps_f)
        if eps_v > 0:
            out.append(make("pe_ttm", lc.value / eps_v, "ratio", PeriodType.point, lc.period_end,
                            f"last close {lc.value} / EPS (TTM) {eps_v:.4f}", [lc.fact_id, eps_f.fact_id]))
        else:
            out.append(Fact.make(entity_key=lc.entity_key, metric="pe_ttm", value=None, unit="ratio", period_end=lc.period_end,
                                 period_type=PeriodType.point, source=SOURCE, retrieved_at=lc.retrieved_at, status=Status.unavailable,
                                 reason="trailing EPS is not positive, so P/E is not meaningful", related_fact_ids=[lc.fact_id, eps_f.fact_id]))
    eq = _ok(facts, "equity_owners")
    if eq is not None and eq.value > 0:
        out.append(make("pb", mcap_v / eq.value, "ratio", PeriodType.point, lc.period_end,
                        f"market cap {mcap_v:.0f} / equity attributable to owners {eq.value} (balance sheet {eq.period_end})",
                        [mcap.fact_id, eq.fact_id]))

    for mine in [f for f in out if f.status == Status.ok]:
        vend = _ok(facts, mine.metric, sources=("yahoo",))
        if vend is not None and vend.unit == mine.unit:
            out.append(cross_check(mine, vend))
    other = [f for f in facts if f.metric == "shares_outstanding" and f.status == Status.ok and f.source != shares.source and f.value]
    if other:
        out.append(cross_check(shares, max(other, key=lambda f: f.period_end)))
    return out
