"""Deterministic peer selection and relative valuation against the peer MEDIAN. No LLM; full trace of picks and exclusions."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from statistics import median, quantiles

from pydantic import BaseModel

from indiafacts.models import FactSet, Status

PARAMS_PATH = Path(__file__).parent / "data" / "peer_params.json"
NO_SIZE_NOTE = "peers chosen by industry only; company size could not be matched"
APPROX_NOTE = "approximate peers: a diversified group compared with single-business companies"
METRICS = ("pe_ttm", "pb", "ev_ebitda", "roe", "fy_roce", "net_margin_q", "net_income_yoy")


class PeerPick(BaseModel):
    ticker: str
    tier: int
    size_ratio: float | None = None
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
    approximate: bool = False        # a diversified group is compared with single-business companies
    few_peers: bool = False          # fewer peers than the warn threshold
    size_matched: bool = True        # False when the target's market cap was missing and peers were chosen by industry only


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
    q1: float | None = None
    q3: float | None = None
    position: str | None = None        # below_q1 | within_iqr | above_q3 (where the target sits among valid peers)


def load_peer_params(path: Path | None = None, today: date | None = None, strict: bool = True) -> dict:
    d = json.loads(Path(path or PARAMS_PATH).read_text(encoding="utf-8"))
    due = [d["review_by"]] + ([d["conglomerates"]["review_by"]] if d.get("conglomerates") else [])
    overdue = any(date.fromisoformat(x) < (today or date.today()) for x in due)
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
    t_ind, t_sec = target.entity.industry, target.entity.sector
    if not t_ind and not t_sec:
        g.unavailable_reason = "target industry or sector unknown; cannot choose peers"
        return g
    if t_cap is None:
        g.size_matched = False
        g.notes.append(NO_SIZE_NOTE)
    if t in set(p.get("conglomerates", {}).get("tickers", [])):
        g.approximate = True
        g.notes.append(APPROX_NOTE)
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
        if cap is None and t_cap is not None:
            g.excluded.append(Exclusion(ticker=tk, reason="no market cap"))
            continue
        if pe is None:
            g.excluded.append(Exclusion(ticker=tk, reason="no P/E"))
            continue
        if pe <= 0:
            g.excluded.append(Exclusion(ticker=tk, reason="P/E not positive (loss-maker)"))
            continue
        if t_cap is None:
            eligible.append((tier, 0.0, tk, None, [cap_id, pe_id]))
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
        g.picks.append(PeerPick(ticker=tk, tier=tier, size_ratio=None if ratio is None else round(ratio, 4),
                                reason=f"{label}; market cap {ratio:.2f}x target" if ratio is not None else f"{label}; size not matched",
                                fact_ids=[i for i in ids if i]))
    if g.picks and not any(pk.tier == 1 for pk in g.picks):
        g.notes.append("no same-industry peers in the loaded pool; sector-level peers are a coarse comparison")
    for tier, _, tk, ratio, _ in eligible[k:]:
        g.excluded.append(Exclusion(ticker=tk, reason=f"eligible but beyond the {k} closest in size within tier order"))
    warn = p.get("warn_below_peers", 5)
    if g.picks and len(g.picks) < warn:
        g.few_peers = True
        g.notes.append(f"only {len(g.picks)} peer(s) used, fewer than {warn}: treat the comparison as rough")
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
        qs = quantiles(vals, n=4, method="inclusive")
        q1, q3 = float(qs[0]), float(qs[2])
        pos = None if tv is None else "below_q1" if tv < q1 else "above_q3" if tv > q3 else "within_iqr"
        multiple = m in p["lower_is_cheaper"]
        prem = (tv / med - 1) if multiple and tv is not None and med != 0 else None
        diff = (tv - med) if not multiple and tv is not None else None
        out.append(MetricComparison(
            metric=m, status="ok", target_value=tv, peer_median=med, q1=q1, q3=q3, position=pos, premium=prem, diff=diff, n=n,
            peer_fact_ids=sorted(ids), peer_values=named,
            higher_than=sum(1 for v in vals if tv is not None and v < tv) if tv is not None else None, of=n))
    return out


POSITION_TEXT = {"below_q1": "below Q1", "within_iqr": "Q1 to Q3", "above_q3": "above Q3"}


def peer_summary(sc: dict | None) -> dict | None:
    """JSON shape for the web app; None when no peer step ran."""
    g = (sc or {}).get("peers")
    if g is None:
        return None
    return {"n_peers": len(g.picks), "candidates": g.candidates, "approximate": g.approximate, "size_matched": g.size_matched, "few_peers": g.few_peers,
            "unavailable_reason": g.unavailable_reason or None, "notes": list(g.notes),
            "picks": [{"ticker": p.ticker, "tier": p.tier, "size_ratio": p.size_ratio} for p in g.picks],
            "metrics": [{"metric": c.metric, "status": c.status, "target": c.target_value, "median": c.peer_median,
                         "q1": c.q1, "q3": c.q3, "position": POSITION_TEXT.get(c.position or ""), "n": c.n,
                         "premium": c.premium, "diff": c.diff, "reason": c.reason}
                        for c in (sc.get("peer_comparisons") or [])]}


def marketlens_peers(target: FactSet, rows: dict, params: dict | None = None, k: int | None = None):
    """Peers from NSE Market Lens: same Market Lens sector first (tier 1), then the same sub-sector (tier 2), nearest market cap.
    Peer figures (market cap, P/E, P/B) are Market Lens's own. Returns (PeerGroup, comparisons) or None when the target is not
    in Market Lens or no peer is eligible, so the caller can keep the Yahoo-based group."""
    from indiafacts.marketlens import peer_factset

    sym = target.entity.ticker.split(".")[0]
    row = (rows or {}).get(sym)
    if not row:
        return None
    sector, sub = row.get("sector") or None, row.get("subSector") or None
    if not sector and not sub:
        return None
    now = target.retrieved_at
    pool = {}
    for s, r in rows.items():
        if r.get("sector") == sector or (sub and r.get("subSector") == sub):
            fs = peer_factset(s, r, now)
            pool[fs.entity.ticker] = fs
    me = peer_factset(sym, row, now)
    tgt = target.model_copy(update={"entity": target.entity.model_copy(update={"industry": sector, "sector": sub})})
    if not any(f.metric == "market_cap" and f.status == Status.ok for f in tgt.facts):
        tgt = tgt.model_copy(update={"facts": list(tgt.facts) + [f for f in me.facts if f.metric == "market_cap"]})
    pool[tgt.entity.ticker] = tgt
    p = params or load_peer_params(strict=False)
    g = select_peers(tgt, pool, k=k, params=p)
    if not g.picks:
        return None
    g.notes.insert(0, f"peer group: NSE Market Lens sector '{sector}'" + (f" (sub-sector '{sub}')" if sub else "")
                   + "; peer market cap, P/E and P/B are Market Lens figures")
    return g, compare_peers(tgt, g, pool, p)
