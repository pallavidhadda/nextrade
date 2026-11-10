"""The bull and bear cases as readable paragraphs, with no model: points are grouped by theme and joined into sentences that
name the strongest theme on each side, then a short paragraph says how they were weighed. Each sentence still comes from a point that
names its evidence, so nothing here is new information. Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

THEMES = {
    "score:value": "what the price asks for the earnings", "score:quality": "the quality of the business", "score:growth": "growth",
    "score:momentum": "the recent price trend", "score:risk": "risk",
    "check:profitable_latest_quarter": "profitability", "check:positive_eps_ttm": "profitability", "check:earnings_growing": "growth",
    "check:revenue_growing": "growth", "check:interest_cover": "the balance sheet", "check:debt_moderate": "the balance sheet",
    "check:positive_1y_return": "the recent price trend", "check:beats_nifty_1y": "the recent price trend", "check:near_52w_high": "the recent price trend",
}


def theme(key: str) -> str:
    if key in THEMES:
        return THEMES[key]
    if key.startswith("health:"):
        return "cash flow and the balance sheet"
    if key.startswith("own:"):
        return "who owns the company"
    if key.startswith("valuation"):
        return "what the price implies"
    if key.startswith("fact:"):
        return "price behaviour"
    return "other evidence"


@dataclass
class Prose:
    favour: str = ""
    against: str = ""
    weighing: str = ""
    strongest_for: str = ""
    strongest_against: str = ""


def clean(text: str) -> str:
    """Make a point read as a sentence fragment: 'Check passed: Profit is higher (+1.4%)' becomes 'profit is higher (+1.4%)'."""
    t = text.strip().rstrip(".")
    m = re.match(r"Check passed:\s*(.*)$", t)
    if m:
        return m.group(1)
    m = re.match(r"Check failed:\s*(.*?)\s*\((.*)\)$", t)
    if m:
        return f"\"{m.group(1)}\" did not hold ({m.group(2)})"
    return t


def _lower(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def _side(points, lead: str) -> tuple[str, str]:
    if not points:
        return f"{lead} nothing stands out on this side.", ""
    by: dict[str, list] = {}
    for p in points:
        by.setdefault(theme(p.key), []).append(p)
    order = sorted(by, key=lambda t: -len(by[t]))
    top = order[0]
    first = clean(by[top][0].text)
    parts = [f"{lead} rests mostly on {top}: {_lower(first)}."]
    rest = [p for t in order for p in by[t]][1:4]
    if rest:
        also = "Also in its favour" if "favour" in lead else "Also against it"
        items = [_lower(clean(p.text)).rstrip(".") for p in rest[:3]]
        parts.append(f"{also}: " + ("; ".join(items[:-1]) + f"; and {items[-1]}" if len(items) > 1 else items[0]) + ".")
    if len(order) > 1:
        parts.append(f"Other areas on this side: {', '.join(order[1:4])}.")
    return " ".join(parts), top


def case_prose(debate, sc: dict | None = None) -> Prose:
    pr = Prose()
    if debate is None or debate.stance.label == "No rating":
        return pr
    pr.favour, pr.strongest_for = _side(debate.bull, "The case in its favour")
    pr.against, pr.strongest_against = _side(debate.bear, "The case against")
    nb, nr = len(debate.bull), len(debate.bear)
    r = (sc or {}).get("result") if sc else None
    score = f" The pool score is {r.overall:.0f} of 100." if r is not None and r.overall is not None else ""
    lean = "more points in favour" if nb > nr else "more points against" if nr > nb else "an even split"
    decider = pr.strongest_for if nb >= nr else pr.strongest_against
    pr.weighing = (f"Weighing them: {nb} points in favour and {nr} against give {lean}.{score} "
                   + (f"The side that carries most weight is {decider}. " if decider else "")
                   + f"That gives an educational rating of {debate.stance.label} with {debate.stance.confidence.lower()} confidence. "
                   "This is a rule-based reading of the evidence above, not a prediction.")
    return pr
