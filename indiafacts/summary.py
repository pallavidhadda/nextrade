"""Compact JSON summary of one run, for the web app. Typed facts stay the source; this only reshapes them."""
from __future__ import annotations

from indiafacts.models import FactSet, Status
from indiafacts.render import DISCLAIMER

KEY_METRICS = ("price", "market_cap", "revenue", "net_income", "eps_diluted", "pe_ttm", "pb", "roe", "debt_to_equity")


def _val(f):
    return None if f.value is None else float(f.value)


def summarize_run(fs: FactSet, scorecard: dict | None, explanation, profile, changes=None) -> dict:
    e = fs.entity
    gaps = [{"metric": f.metric, "period": str(f.period_end), "status": f.status.value, "reason": f.reason}
            for f in fs.facts if f.status in (Status.gap, Status.unavailable)]
    score = None
    checklist: list[dict] = []
    if scorecard and scorecard.get("result") is not None:
        r = scorecard["result"]
        score = {"status": r.status, "overall": r.overall, "rank": r.rank, "n": scorecard.get("n"),
                 "reason": r.reason, "pool": scorecard.get("pool_label"), "flags": list(r.flags),
                 "factors": {k: {"score": v.score, "coverage": v.coverage, "reason": v.reason} for k, v in r.factors.items()}}
        checklist = [{"label": c.label, "result": c.result, "display": c.display, "threshold": c.threshold, "reason": c.reason}
                     for c in scorecard["checklist"]]
    key = []
    for m in KEY_METRICS:
        latest = sorted((f for f in fs.by_metric(m) if f.status == Status.ok), key=lambda f: f.period_end)
        if latest:
            f = latest[-1]
            key.append({"metric": m, "value": _val(f), "unit": f.unit, "period": f.fiscal_label or str(f.period_end),
                        "source": f.source, "basis": f.basis.value, "fact_id": f.fact_id})
    ex = None
    if explanation is not None:
        ex = {"source": explanation.source, "summary": explanation.summary, "uncertainty": explanation.uncertainty,
              "claims": [{"type": c.type, "text": c.text, "ids": c.ids} for c in explanation.claims],
              "triggers": [{"text": t.text, "ids": t.ids} for t in explanation.triggers], "usage": explanation.usage}
    return {"ticker": e.ticker, "name": e.name, "sector": e.sector, "industry": e.industry,
            "isin": e.isin.value, "retrieved_at": fs.retrieved_at.isoformat(),
            "profile": {"horizon": profile.horizon, "risk": profile.effective_risk, "experience": profile.experience},
            "key_facts": key, "score": score, "checklist": checklist, "gaps": gaps,
            "notices": list(fs.notices), "changes": [str(c) for c in (changes or [])][:20],
            "explanation": ex, "disclaimer": DISCLAIMER}
