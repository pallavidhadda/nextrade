"""What the price implies, as arithmetic. Never a fair value or target.
Reverse DCF on trailing earnings: the growth rate that makes a two-stage earnings stream, discounted at an assumed rate, equal today's price.
It treats earnings as distributable and ignores reinvestment, so it is a rough expectations gauge. Banks use book-value methods instead.
Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from indiafacts.models import Entity, Fact, FactSet, Status

PARAMS_PATH = Path(__file__).parent / "data" / "valuation_params.json"
SOURCE = "computed:valuation"


def load_valuation_params(path: Path | None = None, today: date | None = None, strict: bool = True) -> dict:
    data = json.loads(Path(path or PARAMS_PATH).read_text(encoding="utf-8"))
    data["overdue"] = date.fromisoformat(data["review_by"]) < (today or date.today())
    if data["overdue"] and strict:
        raise ValueError(f"valuation params: review overdue (review_by {data['review_by']})")
    return data


def present_value(eps: float, growth: float, rate: float, years: int, terminal: float) -> float:
    """Value per share of earnings growing at `growth` for `years`, then at `terminal` for ever, discounted at `rate`."""
    if rate <= terminal:
        raise ValueError("discount rate must exceed terminal growth")
    pv, e = 0.0, eps
    for t in range(1, years + 1):
        e *= 1 + growth
        pv += e / (1 + rate) ** t
    tv = e * (1 + terminal) / (rate - terminal) / (1 + rate) ** years
    return pv + tv


def implied_growth(price: float, eps: float, rate: float, years: int, terminal: float,
                   search: tuple[float, float] = (-0.30, 0.60)) -> float | None:
    """Growth that makes present_value equal price; None when it lies outside the search range."""
    if price <= 0 or eps <= 0:
        return None
    lo, hi = search
    f = lambda g: present_value(eps, g, rate, years, terminal) - price
    if f(lo) > 0 or f(hi) < 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def applicable_methods(entity: Entity, params: dict | None = None) -> list[str]:
    p = params or load_valuation_params(strict=False)
    text = f"{entity.sector or ''} {entity.industry or ''}".lower()
    if any(w in text for w in p["financial_industry_words"]):
        return ["justified_pb"]
    return ["reverse_dcf_earnings"]


def _latest_ok(fs: FactSet, metric: str) -> tuple[Fact | None, str]:
    cands = sorted([f for f in fs.facts if f.metric == metric and f.period_type == "point"], key=lambda f: f.period_end)
    if not cands:
        return None, f"{metric} not available"
    f = cands[-1]
    if f.status != Status.ok or f.value is None:
        return None, f"{metric} is {f.status.value}: {f.reason}"
    return f, ""


def valuation_facts(fs: FactSet, params: dict | None = None, today: date | None = None, now: datetime | None = None) -> list[Fact]:
    p = params or load_valuation_params(today=today, strict=False)
    now = now or datetime.now(timezone.utc)
    as_of = today or now.date()
    key = fs.entity.ticker
    out: list[Fact] = []

    def make(metric, value, unit, source_field, related, status="ok", reason=""):
        return Fact.make(entity_key=key, metric=metric, value=None if value is None else Decimal(str(round(value, 6))), unit=unit,
                         period_end=as_of, period_type="point", source=SOURCE, source_field=source_field, retrieved_at=now,
                         status=status, reason=reason, related_fact_ids=related)

    method = applicable_methods(fs.entity, p)[0]
    note = f"assumptions reviewed {p['reviewed_on']}, review by {p['review_by']}"
    if method == "reverse_dcf_earnings":
        price, why_p = _latest_ok(fs, "price")
        eps, why_e = _latest_ok(fs, "eps_ttm")
        reason = ""
        if price is None:
            reason = why_p
        elif eps is None:
            reason = why_e
        elif float(eps.value) <= 0:
            reason = "trailing earnings per share are not positive, so earnings-based arithmetic does not apply"
        related = [f.fact_id for f in (price, eps) if f]
        for rate in p["discount_rates"]:
            for years in p["horizons"]:
                metric = f"implied_growth_r{int(round(rate * 100))}_n{years}"
                sf = (f"assumption: discount {rate:.0%}, explicit years {years}, terminal growth {p['terminal_growth']:.0%}, "
                      f"earnings-based; {note}")
                if reason:
                    out.append(make(metric, None, "percent", sf, related, "unavailable", reason))
                    continue
                g = implied_growth(float(price.value), float(eps.value), rate, years, p["terminal_growth"], tuple(p["growth_search_range"]))
                if g is None:
                    out.append(make(metric, None, "percent", sf, related, "unavailable",
                                    "the price lies outside the growth range searched under these assumptions"))
                else:
                    out.append(make(metric, g * 100, "percent", sf, related))
    else:
        roe, why_r = _latest_ok(fs, "roe")
        pb, _ = _latest_ok(fs, "pb")
        names = ("justified_pb_low", "justified_pb_high")
        related = [f.fact_id for f in (roe, pb) if f]
        sf = (f"assumption: cost of equity {p['justified_pb']['cost_of_equity']}, growth {p['justified_pb']['growth']}, "
              f"(ROE - g) / (r - g); {note}")
        if roe is None:
            reason = "ROE is not available, so a justified price-to-book range cannot be computed" if "not available" in why_r or "unavailable" in why_r \
                else f"ROE unusable: {why_r}"
            out += [make(n, None, "ratio", sf, related, "unavailable", reason) for n in names]
        else:
            vals = [(float(roe.value) - g) / (r - g) for r in p["justified_pb"]["cost_of_equity"] for g in p["justified_pb"]["growth"] if r > g]
            vals = [v for v in vals if v > 0]
            if not vals:
                out += [make(n, None, "ratio", sf, related, "unavailable", "ROE is below the growth assumptions, so the formula gives no positive value") for n in names]
            else:
                out += [make(names[0], min(vals), "ratio", sf, related), make(names[1], max(vals), "ratio", sf, related)]
    return out
