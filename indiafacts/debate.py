"""Bull case, bear case and an educational stance built by transparent rules from the same evidence as the report.
Every point names the evidence it rests on (a digest key). The stance is arithmetic on the score and the points, not a prediction or a recommendation.
Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from indiafacts.models import FactSet, Status

PARAMS_PATH = Path(__file__).parent / "data" / "stance_params.json"
FACTOR_NAMES = {"value": "Value", "quality": "Quality", "growth": "Growth", "momentum": "Momentum", "risk": "Risk"}


def load_stance_params(path: Path | None = None, today: date | None = None, strict: bool = True) -> dict:
    data = json.loads(Path(path or PARAMS_PATH).read_text(encoding="utf-8"))
    data["overdue"] = date.fromisoformat(data["review_by"]) < (today or date.today())
    if data["overdue"] and strict:
        raise ValueError(f"stance params: review overdue (review_by {data['review_by']})")
    return data


@dataclass
class Point:
    text: str
    key: str                 # digest key of the evidence, for example "score:quality" or "check:debt_moderate"


@dataclass
class Stance:
    label: str               # Buy | Overweight | Hold | Underweight | Sell | No rating
    confidence: str          # High | Medium | Low | n/a
    reason: str
    value: float | None = None


@dataclass
class Debate:
    bull: list[Point] = field(default_factory=list)
    bear: list[Point] = field(default_factory=list)
    stance: Stance = field(default_factory=lambda: Stance("No rating", "n/a", "no score available"))


def _fact(fs: FactSet, metric: str):
    ok = [f for f in fs.facts if f.metric == metric and f.status == Status.ok and f.value is not None]
    return float(sorted(ok, key=lambda f: f.period_end)[-1].value) if ok else None


def build_debate(fs: FactSet, sc: dict | None, params: dict | None = None) -> Debate:
    p = params or load_stance_params(strict=False)
    d = Debate()
    r = sc.get("result") if sc else None
    if r is None or r.status != "ok" or r.overall is None:
        reason = (r.reason if r is not None and r.reason else "no score available") if sc else "no score available"
        d.stance = Stance("No rating", "n/a", f"no rating because the score could not be computed ({reason})")
        return d

    scored = {k: v.score for k, v in r.factors.items() if v.score is not None}
    for k, v in sorted(scored.items(), key=lambda kv: -kv[1]):
        if v >= p["bull_factor_min"]:
            d.bull.append(Point(f"{FACTOR_NAMES.get(k, k)} scores {v:.0f} of 100 against the comparison pool", f"score:{k}"))
    for k, v in sorted(scored.items(), key=lambda kv: kv[1]):
        if v <= p["bear_factor_max"]:
            d.bear.append(Point(f"{FACTOR_NAMES.get(k, k)} scores only {v:.0f} of 100 against the comparison pool", f"score:{k}"))
    for c in (sc.get("checklist") or []):
        if c.result == "pass":
            d.bull.append(Point(f"Check passed: {c.label} ({c.display})", f"check:{c.id}"))
        elif c.result == "fail":
            d.bear.append(Point(f"Check failed: {c.label} ({c.display}, needs {c.threshold})", f"check:{c.id}"))

    g = _fact(fs, "implied_growth_r12_n10")
    if g is not None:
        if g <= p["implied_growth_modest_max"]:
            d.bull.append(Point(f"At a 12% discount rate the price implies {g:.1f}% yearly earnings growth for 10 years, a modest ask", "valuation:n10"))
        elif g >= p["implied_growth_demanding_min"]:
            d.bear.append(Point(f"At a 12% discount rate the price implies {g:.1f}% yearly earnings growth for 10 years, a demanding ask", "valuation:n10"))
    dd = _fact(fs, "max_drawdown_3y")
    if dd is not None and dd <= p["drawdown_deep"]:
        d.bear.append(Point(f"The 3-year maximum drawdown was {dd:.1%}, a deep fall", "fact:max_drawdown_3y"))
    vol = _fact(fs, "volatility_1y")
    if vol is not None and vol >= p["volatility_high"]:
        d.bear.append(Point(f"One-year volatility is {vol:.1%}, high", "fact:volatility_1y"))

    nb, nr = len(d.bull), len(d.bear)
    ratio = (nb - nr) / max(1, nb + nr)
    s = p["weight_score"] * (r.overall - 50) / 50 + p["weight_points"] * ratio
    b = p["label_bounds"]
    L = p["labels"]
    label = (L["strong_positive"] if s >= b["strong_positive"] else L["positive"] if s >= b["positive"] else
             L["neutral"] if s > b["negative"] else L["negative"] if s > b["strong_negative"] else L["strong_negative"])
    cp = p["confidence"]
    unavailable = sum(1 for c in (sc.get("checklist") or []) if c.result == "unavailable")
    if len(scored) >= cp["high_min_factors"] and unavailable <= cp["max_unavailable_checks_for_high"]:
        conf = "High"
    elif len(scored) >= cp["medium_min_factors"]:
        conf = "Medium"
    else:
        conf = "Low"
    d.stance = Stance(label, conf, f"overall score {r.overall:.1f} of 100 and {nb} supporting against {nr} cautionary points; "
                                   f"{len(scored)} of 5 factors had enough data; a rule-based reading, not a prediction", round(s, 3))
    return d
