"""Deterministic peer selection and relative valuation against the peer MEDIAN. No LLM; full trace of picks and exclusions."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from statistics import median

from pydantic import BaseModel

from indiafacts.models import FactSet, Status

PARAMS_PATH = Path(__file__).parent / "data" / "peer_params.json"
METRICS = ("pe_ttm", "pb", "ev_ebitda", "roe", "fy_roce", "net_margin_q", "net_income_yoy")


class PeerPick(BaseModel):
    ticker: str
    tier: int
    size_ratio: float
    reason: str
    fact_ids: list[str]


class Exclusion(BaseModel):
    ticker: str
    reason: str


class PeerGroup(BaseModel):
    target: str
    picks: list[PeerPick] = []
    excluded: list[Exclusion] = []
    candidates: int = 0
    notes: list[str] = []
    unavailable_reason: str = ""


class MetricComparison(BaseModel):
    metric: str
    status: str
    target_value: float | None = None
    peer_median: float | None = None
    premium: float | None = None      # relative, only for price multiples (pe_ttm, pb)
    diff: float | None = None          # absolute difference, for rates (roe, margin, growth)
    higher_than: int | None = None
    of: int | None = None
    n: int = 0
    reason: str = ""
    peer_fact_ids: list[str] = []
    peer_values: list[tuple[str, float]] = []      # valid peers only, for plotting


def load_peer_params(path: Path | None = None, today: date | None = None, strict: bool = True) -> dict:
    d = json.loads(Path(path or PARAMS_PATH).read_text(encoding="utf-8"))
    overdue = date.fromisoformat(d["review_by"]) < (today or date.today())
    if overdue and strict:
        raise ValueError(f"peer params: review overdue (review_by {d['review_by']})")
    d["overdue"] = overdue
    return d


def _latest(fs: FactSet, metric: str):
    c = [f for f in fs.facts if f.metric == metric and f.status == Status.ok and f.value is not None]
    return max(c, key=lambda f: (f.period_end, f.retrieved_at)) if c else None


def _val(fs: FactSet, metric: str):
    f = _latest(fs, metric)
    return (float(f.value), f.fact_id) if f else (None, None)


def select_peers(target: FactSet, pool: dict[str, FactSet], k: int | None = None, params: dict | None = None) -> PeerGroup:
    p = params or load_peer_params(strict=False)
    k = k or p["k"]
    t = target.entity.ticker
    g = PeerGroup(target=t)
    t_cap, _ = _val(target, "market_cap")
    if t_cap is None:
        g.unavailable_reason = "target market cap unavailable; cannot size-match peers"
        return g
    t_ind, t_sec = target.entity.industry, target.entity.sector
    if not t_ind and not t_sec:
        g.unavailable_reason = "target industry or sector unknown; cannot choose peers"
        return g
    if any(f.metric.startswith("segment_revenue_") for f in target.facts):
        g.notes.append("multi-segment company: single-industry peers are approximate; sum-of-the-parts not built")

    eligible = []
    for tk in sorted(pool):
        if tk == t:
            continue
        fs = pool[tk]
        g.candidates += 1
        cap, cap_id = _val(fs, "market_cap")
        pe, pe_id = _val(fs, "pe_ttm")
        ind, sec = fs.entity.industry, fs.entity.sector
        if t_ind and ind and ind == t_ind and (not t_sec or not sec or sec == t_sec):
            tier = 1
        elif t_sec and sec and sec == t_sec:
            tier = 2
        else:
            continue
        if cap is None:
            g.excluded.append(Exclusion(ticker=tk, reason="no market cap"))
            continue
        if pe is None:
            g.excluded.append(Exclusion(ticker=tk, reason="no P/E"))
            continue
        if pe <= 0:
            g.excluded.append(Exclusion(ticker=tk, reason="P/E not positive (loss-maker)"))
            continue
        ratio = cap / t_cap
        floor = p["size_floor_tier1"] if tier == 1 else p["size_floor_tier2"]
        if ratio > p["size_ceiling"]:
            g.excluded.append(Exclusion(ticker=tk, reason=f"{ratio:.1f}x larger than target (ceiling {p['size_ceiling']}x)"))
            continue
        if ratio < 1 / floor:
            g.excluded.append(Exclusion(ticker=tk, reason=f"{1 / ratio:.1f}x smaller than target (tier-{tier} floor 1/{floor})"))
            continue
        eligible.append((tier, abs(math.log(ratio)), tk, ratio, [cap_id, pe_id]))
    eligible.sort(key=lambda e: (e[0], e[1], e[2]))
    for tier, _, tk, ratio, ids in eligible[:k]:
        label = "same industry" if tier == 1 else "same sector"
        g.picks.append(PeerPick(ticker=tk, tier=tier, size_ratio=round(ratio, 4),
                                reason=f"{label}; market cap {ratio:.2f}x target", fact_ids=ids))
    if g.picks and not any(pk.tier == 1 for pk in g.picks):
        g.notes.append("no same-industry peers in the loaded pool; sector-level peers are a coarse comparison")
    for tier, _, tk, ratio, _ in eligible[k:]:
        g.excluded.append(Exclusion(ticker=tk, reason=f"eligible but beyond the {k} closest in size within tier order"))
    if not g.picks:
        g.unavailable_reason = "no peers in pool" if g.candidates == 0 else "no eligible peers in pool"
    return g


def compare_peers(target: FactSet, group: PeerGroup, pool: dict[str, FactSet], params: dict | None = None) -> list[MetricComparison]:
    p = params or load_peer_params(strict=False)
    out = []
    for m in METRICS:
        lo, hi = p["valid_ranges"][m]
        tv, _ = _val(target, m)
        vals, ids, named = [], [], []
        for pick in group.picks:
            v, fid = _val(pool[pick.ticker], m)
            if v is not None and lo < v <= hi if m in p["lower_is_cheaper"] else v is not None and lo <= v <= hi:
                vals.append(v)
                ids.append(fid)
                named.append((pick.ticker, v))
        n = len(vals)
        if n < p["min_valid_peers"]:
            out.append(MetricComparison(metric=m, status="unavailable", target_value=tv, n=n,
                                        reason=f"fewer than {p['min_valid_peers']} valid peer values ({n})"))
            continue
        med = float(median(vals))
        multiple = m in p["lower_is_cheaper"]
        prem = (tv / med - 1) if multiple and tv is not None and med != 0 else None
        diff = (tv - med) if not multiple and tv is not None else None
        out.append(MetricComparison(
            metric=m, status="ok", target_value=tv, peer_median=med, premium=prem, diff=diff, n=n,
            peer_fact_ids=sorted(ids), peer_values=named,
            higher_than=sum(1 for v in vals if tv is not None and v < tv) if tv is not None else None, of=n))
    return out
