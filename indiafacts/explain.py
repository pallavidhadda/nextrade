"""Explanations built from the digest. The template version is deterministic and always available; an LLM may rewrite
it, but only numbers and ids that exist in the digest survive validation."""
from __future__ import annotations

from pydantic import BaseModel

from indiafacts.digest import Digest


class Claim(BaseModel):
    type: str                       # fact | inference | hypothesis
    text: str
    ids: list[str]


class Trigger(BaseModel):
    text: str
    ids: list[str]


class Explanation(BaseModel):
    source: str                     # "template" or a model name
    summary: str
    claims: list[Claim]
    triggers: list[Trigger] = []
    uncertainty: str = ""
    removed: int = 0
    notes: list[str] = []
    usage: dict = {}              # {'in','out','cached','estimated'} when an LLM was involved


def _ids(d: Digest, *keys: str) -> list[str]:
    return [d.by_key[k] for k in keys if k in d.by_key]


def _text(d: Digest, key: str) -> str:
    sid = d.by_key.get(key)
    return d.items[sid].text.split(" ", 2)[-1] if sid else ""


def triggers(sc: dict | None, d: Digest) -> list[Trigger]:
    out: list[Trigger] = []
    for c in (sc or {}).get("checklist", []):
        ids = _ids(d, f"check:{c.id}")
        if not ids:
            continue
        if c.result == "fail":
            out.append(Trigger(text=f"{c.label}: now {c.display}; this test would pass at {c.threshold}", ids=ids))
        elif c.result == "unavailable":
            out.append(Trigger(text=f"Needs data: {c.label} ({c.reason})", ids=ids))
    return out


def template_explanation(d: Digest, sc: dict | None, fs=None) -> Explanation:
    claims: list[Claim] = []
    r = (sc or {}).get("result")
    if r is not None and r.status == "ok":
        facs = {k: v for k, v in r.factors.items() if v.score is not None}
        if facs:
            hi = max(sorted(facs), key=lambda k: facs[k].score)
            lo = min(sorted(facs), key=lambda k: facs[k].score)
            claims.append(Claim(type="fact", text=f"The company scores {r.overall:.1f} out of 100, rank {r.rank} of {sc['n']} in the "
                                f"comparison pool; its strongest factor is {hi} ({facs[hi].score:.1f}) and its weakest is {lo} "
                                f"({facs[lo].score:.1f}). The ranking compares it with that pool only.",
                                ids=_ids(d, "score:overall", f"score:{hi}", f"score:{lo}")))
            side = "below" if r.overall < 50 else "at or above"
            claims.append(Claim(type="inference", text=f"Its overall score sits {side} the middle of the pool, mainly because of its "
                                f"{lo} factor.", ids=_ids(d, "score:overall", f"score:{lo}")))
    if sc and sc.get("checklist"):
        known = [c for c in sc["checklist"] if c.result != "unavailable"]
        failed = [c for c in known if c.result == "fail"]
        claims.append(Claim(type="fact", text=f"{sc['checklist_summary']} of the nine checklist tests"
                            + (f"; those it did not pass: {'; '.join(c.label.lower() for c in failed[:3])}." if failed else "."),
                            ids=_ids(d, *[f"check:{c.id}" for c in (failed[:3] or known[:1])])))
    if "fact:net_income" in d.by_key:
        yoy = _text(d, "fact:net_income_yoy")
        claims.append(Claim(type="fact", text="Latest quarter profit: " + _text(d, "fact:net_income")
                            + (f"; change on a year earlier {yoy.split(' ')[-1].split('[')[0]}." if yoy else "."),
                            ids=_ids(d, "fact:net_income", "fact:net_income_yoy")))
    if "fact:return_1y" in d.by_key:
        rel = _text(d, "fact:relative_return_1y")
        claims.append(Claim(type="fact", text="Price over the last year: " + _text(d, "fact:return_1y").replace("return_1y ", "")
                            + (f", {rel.replace('relative_return_1y ', '')} against the Nifty 50." if rel else "."),
                            ids=_ids(d, "fact:return_1y", "fact:relative_return_1y")))
    if "peer:pe_ttm" in d.by_key:
        claims.append(Claim(type="fact", text="Valuation against peers: " + _text(d, "peer:pe_ttm").replace("peer ", "") + ".",
                            ids=_ids(d, "peer:pe_ttm")))
    gaps = [i for i in d.items.values() if i.group == "gaps"]
    unc = (f"Data gaps: {len(gaps)} item(s) are missing, unavailable, unverified or in conflict"
           + (f" (for example {gaps[0].text.split(':')[0].lower()})" if gaps else "")
           + ". Scores are relative to the pool and are not forecasts; they say nothing about future returns.")
    claims = [c for c in claims if c.ids]
    return Explanation(source="template", summary=claims[0].text if claims else "No explanation could be built from the available data.",
                       claims=claims, triggers=triggers(sc, d), uncertainty=unc)
