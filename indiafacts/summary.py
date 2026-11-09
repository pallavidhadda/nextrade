"""Compact JSON summary of one run, for the web app. Typed facts stay the source; this only reshapes them."""
from __future__ import annotations

from indiafacts.models import FactSet, Status
from indiafacts.render import DISCLAIMER

FACTS_CAP = 800                  # size guard for the JSON summary (and so the snapshot branch); the overflow count is reported
EVIDENCE_CAP = 200
KEY_METRICS = ("price", "market_cap", "revenue", "net_income", "eps_diluted", "pe_ttm", "pb", "roe", "debt_to_equity")


def _val(f):
    return None if f.value is None else float(f.value)


def _pool_name(sc: dict) -> str | None:
    label = sc.get("pool_label") or sc.get("pool")
    if not label:
        return None
    if sc.get("default_pool"):
        return f"the built-in pool of {sc.get('n')} large companies"
    if str(label).lower().endswith((".txt", ".csv")):
        return f"your list of {sc.get('n')} companies"
    return str(label)


from indiafacts.fundamentals_view import fundamentals_rows
from indiafacts.ownership_view import ownership
from indiafacts.peers import peer_summary


def summarize_run(fs: FactSet, scorecard: dict | None, explanation, profile, changes=None, digest=None, news=None, debate=None, levels=None, panel=None, flows=None, scenario=None, prose=None, as_of=None, news_fetched=False, stamp=None) -> dict:
    from indiafacts.completeness import completeness

    e = fs.entity
    gaps = [{"metric": f.metric, "period": str(f.period_end), "status": f.status.value, "reason": f.reason}
            for f in fs.facts if f.status in (Status.gap, Status.unavailable)]
    score = None
    checklist: list[dict] = []
    checklist_groups: list[dict] = []
    if scorecard and scorecard.get("result") is not None:
        r = scorecard["result"]
        score = {"status": r.status, "overall": r.overall, "rank": r.rank, "n": scorecard.get("n"),
                 "reason": r.reason, "pool": _pool_name(scorecard), "flags": list(r.flags),
                 "factors": {k: {"score": v.score, "coverage": v.coverage, "reason": v.reason} for k, v in r.factors.items()},
                 "contributions": {k: c.model_dump() for k, c in r.contributions.items()},
                 "missing_factors": [m.model_dump() for m in r.missing_factors],
                 "pool_failed": len(scorecard.get("failed") or {})}
        from indiafacts.checklist import grouped

        checklist_groups = grouped(scorecard["checklist"])
        checklist = [{"label": c.label, "group": c.group, "result": c.result, "display": c.display, "threshold": c.threshold, "reason": c.reason}
                     for c in scorecard["checklist"]]
    key = []
    for m in KEY_METRICS:
        latest = sorted((f for f in fs.by_metric(m) if f.status == Status.ok), key=lambda f: f.period_end)
        if latest:
            f = latest[-1]
            key.append({"metric": m, "value": _val(f), "unit": f.unit, "period": f.fiscal_label or str(f.period_end),
                        "source": f.source, "basis": f.basis.value, "fact_id": f.fact_id})
    vals = [f for f in fs.facts if f.source == "computed:valuation"]
    valuation = None
    if vals:
        okv = [f for f in vals if f.status == Status.ok]
        valuation = {"method": "justified_pb" if vals[0].metric.startswith("justified") else "reverse_dcf_earnings",
                     "assumptions": (okv or vals)[0].source_field, "unavailable_reason": None if okv else vals[0].reason,
                     "items": [{"metric": f.metric, "value": _val(f), "unit": f.unit, "fact_id": f.fact_id} for f in okv]}
    ex = None
    if explanation is not None:
        ex = {"source": explanation.source, "summary": explanation.summary, "uncertainty": explanation.uncertainty,
              "claims": [{"type": c.type, "text": c.text, "ids": c.ids} for c in explanation.claims],
              "triggers": [{"text": t.text, "ids": t.ids} for t in explanation.triggers], "usage": explanation.usage}
    llm = None
    if digest is not None:
        from indiafacts.llm import build_prompt

        system, user = build_prompt(digest)
        from indiafacts.agents import debate_for_prompts, roles_for_prompts

        llm = {"system": system, "user": user, "max_tokens": 700, "roles": roles_for_prompts(), "debate": debate_for_prompts(), "ids": sorted(digest.ids, key=lambda i: int(i[1:])), "digest": digest.text}
    deb = None
    if debate is not None:
        deb = {"bull": [{"text": p.text, "evidence": p.key} for p in debate.bull], "bear": [{"text": p.text, "evidence": p.key} for p in debate.bear],
               "stance": {"label": debate.stance.label, "confidence": debate.stance.confidence, "reason": debate.stance.reason}}
    lev = None
    if levels is not None:
        lev = {"applies": levels.applies, "last_close": levels.last_close, "stop": levels.stop, "risk_pct": levels.risk_pct,
               "targets": [{"r": r, "price": t} for r, t in zip(levels.reward_risk, levels.targets)],
               "support": [{"name": n, "price": v} for n, v in levels.support], "resistance": [{"name": n, "price": v} for n, v in levels.resistance],
               "reason": levels.reason, "notes": levels.notes}
    rp = None
    if panel is not None:
        rp = {"profile_lens": panel.profile_lens, "notes": panel.notes,
              "lenses": [{"name": l.name, "fits": l.fits, "breaches": l.breaches, "max_position_pct": l.max_position_pct, "reason": l.reason} for l in panel.lenses]}
    nws = [{"title": n.title, "publisher": n.publisher, "published": n.published.date().isoformat() if n.published else None,
            "url": n.url, "sentiment_hint": n.sentiment_hint, "source_kind": n.source_kind, "category": n.category,
            "event_type": n.event_type} for n in (news or [])]
    facts = [{"fact_id": f.fact_id, "metric": f.metric, "value": None if f.value is None else str(f.value), "unit": f.unit,
              "period_end": f.period_end.isoformat(), "period_type": f.period_type.value, "basis": f.basis.value, "source": f.source,
              "status": f.status.value, "reason": f.reason, "evidence": (f.evidence or "")[:EVIDENCE_CAP]} for f in fs.facts[:FACTS_CAP]]
    return {"ticker": e.ticker, "name": e.name, "sector": e.sector, "industry": e.industry,
            "isin": e.isin.value, "retrieved_at": fs.retrieved_at.isoformat(),
            "profile": {"horizon": profile.horizon, "risk": profile.effective_risk, "experience": profile.experience},
            "key_facts": key, "facts": facts, "facts_total": len(fs.facts), "fundamentals": fundamentals_rows(fs), "ownership": ownership(fs), "market_flows": flows, "scenario": (None if scenario is None or not scenario.applies else {"tone": scenario.tone, "headline": scenario.headline, "summary": scenario.summary, "levels": [{"label": l, "price": v, "meaning": m} for l, v, m in scenario.levels], "stages": [{"label": l, "pct": p, "condition": c} for l, p, c in scenario.stages], "watch": scenario.watch, "more_positive_if": scenario.more_positive_if, "more_cautious_if": scenario.more_cautious_if, "notes": scenario.notes}), "prose": (None if prose is None or not prose.favour else {"favour": prose.favour, "against": prose.against, "weighing": prose.weighing}), "score": score, "completeness": completeness(fs, as_of, news=news if news_fetched else None),"checklist": checklist, "checklist_groups": checklist_groups, "peers": peer_summary(scorecard), "gaps": gaps,
            "notices": list(fs.notices), "changes": [str(c) for c in (changes or [])][:20],
            "valuation": valuation, "debate": deb, "levels": lev, "risk_panel": rp, "news": nws, "explanation": ex, "llm": llm, "stamp": stamp, "scenario_reason": getattr(scenario, "reason", "") if scenario is not None else "", "disclaimer": DISCLAIMER}
