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
        if c.id in TRIVIAL_CHECKS:
            continue                      # nearly always true for listed companies; shown in the checklist, not counted as a point
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
    _health_points(fs, d, p)
    dd = _fact(fs, "max_drawdown_3y")
    if dd is not None and dd <= p["drawdown_deep"]:
        d.bear.append(Point(f"The 3-year maximum drawdown was {dd:.1%}, a deep fall", "fact:max_drawdown_3y"))
    vol = _fact(fs, "volatility_1y")
    if vol is not None and vol >= p["volatility_high"]:
        d.bear.append(Point(f"One-year volatility is {vol:.1%}, high", "fact:volatility_1y"))

    nb, nr = len(d.bull), len(d.bear)
    ratio = (nb - nr) / max(p.get("min_points", 6), nb + nr)      # few points cannot swing the rating to an extreme
    s = p["weight_score"] * (r.overall - 50) / 50 + p["weight_points"] * ratio
    b = p["label_bounds"]
    L = p["labels"]
    label = (L["strong_positive"] if s >= b["strong_positive"] else L["positive"] if s >= b["positive"] else
             L["neutral"] if s > b["negative"] else L["negative"] if s > b["strong_negative"] else L["strong_negative"])
    conf, why = _confidence(fs, sc, scored, s, b, ratio, p)
    d.stance = Stance(label, conf, f"overall score {r.overall:.1f} of 100 and {nb} supporting against {nr} cautionary points; "
                                   f"{len(scored)} of 5 factors had enough data; confidence {conf.lower()} because {why}; a rule-based reading, not a prediction", round(s, 3))
    return d


TRIVIAL_CHECKS = {"profitable_latest_quarter", "positive_eps_ttm"}
HEALTH_DEFAULTS = {"roce_good": 0.15, "roce_weak": 0.08, "net_debt_ebitda_high": 3.0, "interest_cover_thin": 2.0,
                   "fcf_yield_good": 0.04, "growth_good": 0.12, "growth_weak": 0.0}


def _ownership_points(fs: FactSet, d: Debate, p: dict) -> None:
    """Official shareholding evidence only; vendor proxies never create a point."""
    h = {"pledge_high": 0.25, "promoter_fall_pp": 0.02, **p.get("ownership", {})}
    pl, ch = _fact(fs, "sh_promoter_pledged"), _fact(fs, "sh_promoter_change")
    if pl is not None and pl >= h["pledge_high"]:
        d.bear.append(Point(f"{pl:.0%} of the promoters' shares are pledged as loan security, a risk flag", "own:sh_promoter_pledged"))
    if ch is not None and ch <= -h["promoter_fall_pp"]:
        d.bear.append(Point(f"The promoter group's holding fell {abs(ch) * 100:.1f} percentage points since the previous filing", "own:sh_promoter"))


def _health_points(fs: FactSet, d: Debate, p: dict) -> None:
    _ownership_points(fs, d, p)
    """Business-health evidence from annual statements. Absent data adds nothing: no point is ever made up."""
    h = {**HEALTH_DEFAULTS, **p.get("health", {})}
    fcf, fcfy, roce = _fact(fs, "fy_free_cash_flow"), _fact(fs, "fy_fcf_yield"), _fact(fs, "fy_roce")
    lev, cover = _fact(fs, "fy_net_debt_to_ebitda"), _fact(fs, "fy_interest_cover")
    pg, rg = _fact(fs, "fy_net_income_cagr_3y"), _fact(fs, "fy_revenue_cagr_3y")
    if fcf is not None and fcf < 0:
        d.bear.append(Point("Free cash flow for the last financial year was negative: the business spent more than it generated", "health:fy_free_cash_flow"))
    elif fcfy is not None and fcfy >= h["fcf_yield_good"]:
        d.bull.append(Point(f"Free cash flow is {fcfy:.1%} of the market value, a solid cash return", "health:fy_fcf_yield"))
    if roce is not None:
        if roce >= h["roce_good"]:
            d.bull.append(Point(f"Return on capital employed is {roce:.1%}, a strong return on the money in the business", "health:fy_roce"))
        elif roce < h["roce_weak"]:
            d.bear.append(Point(f"Return on capital employed is only {roce:.1%}, a weak return on the money in the business", "health:fy_roce"))
    if lev is not None and lev >= h["net_debt_ebitda_high"]:
        d.bear.append(Point(f"Net debt is {lev:.1f} times a year of operating earnings, heavy", "health:fy_net_debt_to_ebitda"))
    if cover is not None and cover < h["interest_cover_thin"]:
        d.bear.append(Point(f"Operating profit covers interest only {cover:.1f} times, thin", "health:fy_interest_cover"))
    if pg is not None:
        if pg >= h["growth_good"]:
            d.bull.append(Point(f"Profit grew {pg:.1%} a year on average over three years", "health:fy_net_income_cagr_3y"))
        elif pg < h["growth_weak"]:
            d.bear.append(Point(f"Profit shrank {abs(pg):.1%} a year on average over three years", "health:fy_net_income_cagr_3y"))
    elif rg is not None and rg < h["growth_weak"]:
        d.bear.append(Point(f"Sales shrank {abs(rg):.1%} a year on average over three years", "health:fy_revenue_cagr_3y"))


def _confidence(fs: FactSet, sc: dict, scored: dict, s: float, bounds: dict, ratio: float, p: dict) -> tuple[str, str]:
    """Confidence in the rating, from six visible ingredients. It says how well-supported the reading is, not how likely it is to be right.
    1) factors with data, 2) size of the comparison pool, 3) checks that could be measured, 4) distance from a rating boundary,
    5) whether the score and the evidence points lean the same way, 6) annual business-health data present."""
    cp = {"high_min": 6, "medium_min": 4, "pool_large": 25, "pool_ok": 12, "edge_margin": 0.08, **p.get("confidence", {})}
    r = sc["result"]
    pts, good, weak = 0, [], []
    nf = len(scored)
    if nf >= 5:
        pts += 2; good.append("all five factors had data")
    elif nf == 4:
        pts += 1; weak.append("one factor lacked data")
    else:
        weak.append(f"only {nf} factors had data")
    n = sc.get("n") or r.n or 0
    if n >= cp["pool_large"]:
        pts += 2; good.append(f"a comparison pool of {n}")
    elif n >= cp["pool_ok"]:
        pts += 1; weak.append(f"a smallish comparison pool ({n})")
    else:
        weak.append(f"a small comparison pool ({n})")
    unavailable = sum(1 for c in (sc.get("checklist") or []) if c.result == "unavailable")
    if unavailable <= 1:
        pts += 1; good.append("nearly every check measurable")
    else:
        weak.append(f"{unavailable} checks unavailable")
    cuts = [bounds[k] for k in ("strong_positive", "positive", "negative", "strong_negative")]
    if min(abs(s - c) for c in cuts) >= cp["edge_margin"]:
        pts += 1; good.append("clear of a rating boundary")
    else:
        weak.append("close to a rating boundary")
    lean_score = r.overall - 50
    if lean_score * ratio >= 0 and not (abs(lean_score) > 10 and ratio * lean_score < 0):
        pts += 1; good.append("score and evidence points agree")
    else:
        weak.append("the score and the evidence points disagree")
    if _fact(fs, "fy_free_cash_flow") is not None or _fact(fs, "fy_roce") is not None or _fact(fs, "fy_equity_multiplier") is not None:
        pts += 1; good.append("annual business-health data present")
    else:
        weak.append("no annual business-health data")
    conf = "High" if pts >= cp["high_min"] else "Medium" if pts >= cp["medium_min"] else "Low"
    if nf < 4:
        conf = "Low"                                   # a rating built on fewer than four factors is never better than low confidence
    reasons = (weak if conf != "High" and weak else good)[:3]
    return conf, ", ".join(reasons) if reasons else "all ingredients present"
