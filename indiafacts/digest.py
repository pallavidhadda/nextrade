"""Compact, deterministic digest of a report for narration. Every line has a short id (F1..) that maps to a fact id
or a score/check/peer label. Gaps and unavailable items are always included. Token counts are estimates (chars / 4)."""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal

from indiafacts.analysis import prefer_sources
from indiafacts.models import Fact, FactSet, PeriodType, Status
from indiafacts.units import format_inr

BANNED_WORDS = ("buy", "sell", "recommend", "recommendation", "target price", "overweight", "underweight",
                "outperform", "underperform")
DEFAULT_BUDGET = 1500
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")


def est_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def clean(s, n: int = 60) -> str:
    return _CTRL.sub(" ", "" if s is None else str(s)).strip()[:n]


@dataclass
class Item:
    key: str            # e.g. "score:overall", "fact:net_income", "check:positive_1y_return"
    ref: str            # fact id or label
    text: str
    group: str


@dataclass
class Digest:
    text: str
    ids: dict[str, str]                   # short id -> ref
    items: dict[str, Item]                # short id -> item
    by_key: dict[str, str]                # key -> short id
    est_tokens: int
    dropped: list[str] = field(default_factory=list)
    digest_hash: str = ""


def _pct(v) -> str:
    return f"{float(v):+.1%}"


def _val(f: Fact) -> str:
    v = f.value
    if f.metric.endswith(("_yoy",)) or f.metric.startswith(("return_", "benchmark_return_", "relative_return_", "max_drawdown_",
                                                            "pct_from_", "net_margin")) or f.metric in ("volatility_1y",):
        return _pct(v) if f.metric != "volatility_1y" else f"{float(v):.1%}"
    if f.unit in ("INR", "INR_per_share"):
        return format_inr(Decimal(str(v)))
    return f"{float(v):.3g}"


def _latest(facts: list[Fact], metric: str, quarterly: bool = False) -> Fact | None:
    pool = [f for f in facts if f.metric == metric and f.status in (Status.ok, Status.unverified) and f.value is not None]
    if quarterly:
        pool = prefer_sources([f for f in pool if f.period_type == PeriodType.Q])
    return max(pool, key=lambda f: (f.period_end, f.retrieved_at), default=None)


KEY_QUARTER = ("net_income", "revenue")
KEY_POINT = ("net_income_yoy", "revenue_yoy", "net_margin_q", "pe_ttm", "pb", "roe", "debt_to_equity",
             "interest_service_coverage_ratio", "ebitda_derived")
PRICE_KEYS = ("return_1y", "relative_return_1y", "max_drawdown_3y", "pct_from_52w_high", "volatility_1y", "beta_1y")


def build_digest(fs: FactSet, sc: dict | None, profile=None, budget_tokens: int = DEFAULT_BUDGET) -> Digest:
    e = fs.entity
    groups: dict[str, list[Item]] = {"header": [], "gaps": [], "scores": [], "checklist": [], "facts": [], "price": [],
                                     "peers": [], "notices": []}
    G = lambda g, key, ref, text: groups[g].append(Item(key, ref, text, g))
    G("header", "entity", "entity",
      f"ENTITY {clean(e.ticker)} | {clean(e.name)} | ISIN {clean(e.isin.value) or 'unavailable'} | sector {clean(e.sector) or 'unavailable'}")
    if profile is not None:
        G("header", "asof", "profile", f"ASOF {fs.retrieved_at.date()} | profile horizon {profile.horizon}, effective risk "
                                      f"{profile.effective_risk}, hash {profile.profile_hash}")

    facts = fs.facts
    # gaps, unavailable, unverified, conflicts: never dropped
    gap_periods: dict[str, list[Fact]] = {}
    for f in facts:
        if f.status == Status.gap:
            gap_periods.setdefault(f.fiscal_label or f.period_end.isoformat(), []).append(f)
    for label, fl in sorted(gap_periods.items()):
        G("gaps", f"gap:{label}", fl[0].fact_id, f"GAP {label}: no figure for {', '.join(sorted({x.metric for x in fl})[:6])} "
                                                  f"({clean(fl[0].reason)})")
    for f in sorted([f for f in facts if f.status == Status.unavailable and f.period_type != PeriodType.Q],
                    key=lambda f: f.metric)[:10]:
        G("gaps", f"unavailable:{f.metric}", f.fact_id, f"UNAVAILABLE {f.metric}: {clean(f.reason, 80)}")
    unver = sorted({(f.metric, f.reason) for f in facts if f.status == Status.unverified and not (f.source_field or "").startswith("series:")})
    seen = set()
    for f in facts:
        if f.status == Status.unverified and (f.metric not in seen) and not (f.source_field or "").startswith("series:"):
            seen.add(f.metric)
            G("gaps", f"unverified:{f.metric}", f.fact_id, f"UNVERIFIED {f.metric}: {clean(f.reason, 90)}")
    for f in facts:
        if f.status == Status.conflict:
            G("gaps", f"conflict:{f.metric}", f.fact_id, f"CONFLICT {f.metric}: {clean(f.reason, 90)}")

    if sc and sc.get("result") is not None:
        r = sc["result"]
        if r.status == "ok":
            G("scores", "score:overall", "score:overall", f"SCORE overall {r.overall:.1f}/100 rank {r.rank} of {sc['n']} (pool, not absolute)")
        else:
            G("scores", "score:overall", "score:overall", f"SCORE overall abstain: {clean(r.reason, 80)}")
        for fac, s_ in sorted(r.factors.items()):
            G("scores", f"score:{fac}", f"score:{fac}",
              f"SCORE {fac} " + (f"{s_.score:.1f} coverage {s_.coverage:.0%}" if s_.score is not None else f"unavailable ({clean(s_.reason, 40)})"))
    if sc:
        G("checklist", "check:summary", "check:summary", f"CHECKLIST {sc['checklist_summary']}")
        for c in sc["checklist"]:
            G("checklist", f"check:{c.id}", f"check:{c.id}",
              f"CHECK {c.id} {c.result}" + (f" {c.display} needs {c.threshold}" if c.value is not None else f" ({clean(c.reason, 40)})"))

    for m in KEY_QUARTER:
        f = _latest(facts, m, quarterly=True)
        if f is not None:
            G("facts", f"fact:{m}", f.fact_id, f"FACT {m} {f.fiscal_label} {_val(f)} [{f.source}]")
    by_id = {f.fact_id: f for f in facts}
    for m in KEY_POINT:
        f = _latest(facts, m)
        if f is not None:
            mix = ""
            if m.endswith("_yoy") and len(f.related_fact_ids) == 2 and all(i in by_id for i in f.related_fact_ids):
                cur, base = (by_id[i] for i in f.related_fact_ids)
                if cur.source != base.source:
                    mix = f" (mixed sources: current {cur.source}, prior year {base.source})"
            G("facts", f"fact:{m}", f.fact_id, f"FACT {m} {_val(f)} [{f.source}]{mix}" + (" unverified" if f.status == Status.unverified else ""))
    for m in PRICE_KEYS:
        f = _latest([x for x in facts if (x.source_field or "").startswith("series:")], m)
        if f is not None:
            G("price", f"fact:{m}", f.fact_id, f"PRICE {m} {_val(f)}" + (" unverified" if f.status == Status.unverified else ""))
    if sc:
        for c in sc.get("peer_comparisons", []):
            if c.status == "ok" and c.metric in ("pe_ttm", "pb"):
                prem = f"{c.premium:+.1%}" if c.premium is not None else "n/a"
                G("peers", f"peer:{c.metric}", f"peer:{c.metric}",
                  f"PEER {c.metric} {c.target_value:.3g} vs median {c.peer_median:.3g} ({prem}, n={c.n})")
    for n in fs.notices[:3]:
        G("notices", f"notice:{len(groups['notices'])}", "notice", f"NOTICE {clean(n, 100)}")

    # shrink: drop whole groups from the lowest priority first; gaps and header are never dropped
    order = ["notices", "peers", "price", "facts", "checklist", "scores"]
    dropped: list[str] = []

    def render() -> tuple[str, dict, dict, dict]:
        ids, items, by_key, lines = {}, {}, {}, []
        n = 0
        for g in ("header", "scores", "checklist", "facts", "price", "peers", "gaps", "notices"):
            for it in groups[g]:
                if it.ref in ("entity", "profile", "notice"):
                    lines.append(it.text)
                    continue
                n += 1
                sid = f"F{n}"
                ids[sid], items[sid], by_key[it.key] = it.ref, it, sid
                lines.append(f"{sid} {it.text}")
        if dropped:
            lines.append("DROPPED for length: " + ", ".join(dropped))
        return "\n".join(lines), ids, items, by_key

    text, ids, items, by_key = render()
    for g in order:
        if est_tokens(text) <= budget_tokens:
            break
        if groups[g]:
            groups[g] = []
            dropped.append(g)
            text, ids, items, by_key = render()
    return Digest(text, ids, items, by_key, est_tokens(text), dropped, hashlib.sha256(text.encode()).hexdigest()[:12])
