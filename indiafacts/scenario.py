"""An educational scenario plan for every rating: reference levels, a staged exposure ceiling, dates to watch and what would change the view.

It turns the rating, the reference levels and the risk lenses into something a person can read as a plan, for bullish, neutral and
cautious ratings alike. Every number is arithmetic on measured prices or the stated risk limits; there are no price targets and no
instruction to trade. Avoids the words in digest.BANNED_WORDS on purpose.
Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from indiafacts.availability import available_from
from indiafacts.models import FactSet, PeriodType, Status
from indiafacts.narrative import clean

BULLISH, NEUTRAL, CAUTIOUS = ("Buy", "Overweight"), ("Hold",), ("Underweight", "Sell")
TRANCHES = (1 / 3, 1 / 3, 1 / 3)


@dataclass
class Scenario:
    applies: bool = False
    tone: str = ""                        # constructive | neutral | cautious
    headline: str = ""
    summary: str = ""
    levels: list[tuple[str, float, str]] = field(default_factory=list)       # (label, price, what it means)
    stages: list[tuple[str, float | None, str]] = field(default_factory=list)  # (label, % of portfolio or None, condition)
    ceiling_pct: float | None = None
    watch: list[str] = field(default_factory=list)
    more_positive_if: list[str] = field(default_factory=list)
    more_cautious_if: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reason: str = ""


def _next_results_due(fs: FactSet, today: date) -> date | None:
    ends = [f.period_end for f in fs.facts if f.period_type == PeriodType.Q and f.status == Status.ok]
    if not ends:
        return None
    last = max(ends)
    month = last.month + 3
    year = last.year + (1 if month > 12 else 0)
    month = month - 12 if month > 12 else month
    nxt = date(year, month, 1) + timedelta(days=31)
    nxt = date(nxt.year, nxt.month, 1) - timedelta(days=1)             # last day of that month
    due = available_from(nxt, "Q")
    while due < today:                                                  # the company is already overdue on the estimate: roll forward
        month = nxt.month + 3
        nxt = date(nxt.year + (1 if month > 12 else 0), month - 12 if month > 12 else month, 1)
        nxt = date(nxt.year, nxt.month, 1) + timedelta(days=31)
        nxt = date(nxt.year, nxt.month, 1) - timedelta(days=1)
        due = available_from(nxt, "Q")
    return due


def _inr(v: float) -> str:
    return f"₹{v:,.2f}"


def build_scenario(fs: FactSet, debate, levels, panel, today: date | None = None) -> Scenario:
    today = today or date.today()
    sc = Scenario()
    label = debate.stance.label if debate is not None else "No rating"
    from indiafacts.debate import has_direction

    if not has_direction(label) or levels is None or levels.last_close is None:
        sc.reason = ("no scenario plan: the evidence is not enough for a rating" if label == "Insufficient evidence"
                     else "no scenario plan without a rating and a last close")
        return sc
    last = levels.last_close
    sc.applies = True
    below = sorted(levels.support, key=lambda kv: -kv[1])                 # nearest support first
    above = sorted(levels.resistance, key=lambda kv: kv[1])                # nearest resistance first
    ref_stop = levels.stop if levels.stop is not None else (last * (1 - levels.sizing_risk_pct / 100) if levels.sizing_risk_pct else None)
    ceiling = None
    if panel is not None:
        lens = next((l for l in panel.lenses if l.name == panel.profile_lens), None)
        ceiling = lens.max_position_pct if lens is not None else None
    sc.ceiling_pct = ceiling
    conf = debate.stance.confidence
    half = conf == "Low"
    if half:
        sc.notes.append("confidence is low, so the staged sizes below are halved")

    def stage(label, frac, cond):
        sc.stages.append((label, None if ceiling is None else round(ceiling * frac * (0.5 if half else 1), 2), cond))

    if label in BULLISH:
        sc.tone, sc.headline = "constructive", "Constructive scenario: build exposure in stages, with the exit decided in advance"
        zone_low = below[0][1] if below else None
        if zone_low is not None:
            sc.levels.append(("Gradual entry area", zone_low, f"pullbacks toward {below[0][0]} ({_inr(zone_low)}) up to the last close ({_inr(last)}) are where staged exposure would be considered"))
        if above:
            sc.levels.append(("Confirmation level", above[0][1], f"a close above the {above[0][0]} would show the move is holding"))
        if ref_stop is not None:
            sc.levels.append(("Invalidation level (reference stop)", ref_stop, f"{(last - ref_stop) / last * 100:.1f}% below the last close; a close below it means the constructive reading no longer holds"))
        for r, t in zip(levels.reward_risk, levels.targets):
            sc.levels.append((f"Reference level at {r:g}x the risk", t, "arithmetic on the stop distance, not a forecast"))
        stage("First stage", TRANCHES[0], "now, if the scenario fits your plan")
        stage("Second stage", TRANCHES[1], f"after a close above {_inr(above[0][1])}" if above else "after the price makes a new 52-week high")
        stage("Third stage", TRANCHES[2], "after the next results keep the checklist passing")
        sc.summary = ("The evidence leans positive. A staged approach limits the cost of being early: start small, add only when the price and the next results confirm, "
                      "and decide in advance the level at which the reading is wrong.")
    elif label in NEUTRAL:
        sc.tone, sc.headline = "neutral", "Neutral scenario: wait for a clearer signal before adding"
        if above:
            sc.levels.append(("Upside trigger", above[0][1], f"a close above the {above[0][0]} would be the first sign the picture is improving"))
        down = ref_stop if ref_stop is not None else (below[0][1] if below else None)
        if down is not None:
            sc.levels.append(("Downside trigger", down, "a close below this would weaken the case; reconsider any existing exposure"))
        stage("New exposure now", 0.0, "none: the evidence is balanced")
        stage("If the upside trigger is cleared and the checks improve", TRANCHES[0], "a first stage, no more")
        sc.summary = ("The evidence is balanced, so the plan is to wait. Existing exposure can be kept within the ceiling; adding needs a trigger below to be met.")
    else:
        sc.tone, sc.headline = "cautious", "Cautious scenario: keep exposure small or avoid it until the picture improves"
        if above:
            sc.levels.append(("Where the cautious view would be wrong", above[0][1], f"a close above the {above[0][0]} would argue against staying cautious"))
        if below:
            sc.levels.append(("Weakness confirmed below", below[0][1], f"a close below the {below[0][0]} would add to the cautious reading"))
        stage("Largest exposure in this scenario", TRANCHES[0], "a third of the ceiling at most")
        stage("If weakness is confirmed", 0.0, "reduce further")
        sc.summary = ("The evidence leans negative. The plan is to keep exposure small or avoid it, and to name the level at which that view would be dropped.")
    due = _next_results_due(fs, today)
    if due is not None:
        sc.watch.append(f"Next quarterly results are due by {due.strftime('%d %b %Y')} (a deadline estimate; the company may report earlier)")
    pledge = next((f for f in fs.facts if f.metric == "sh_promoter_pledged" and f.value is not None), None)
    if pledge is not None:
        sc.watch.append("Promoter pledge and holding change with each quarterly shareholding filing")
    sc.watch.append("The rating is recomputed from fresh data each run; a changed rating changes this plan")
    bull, bear = (debate.bull if debate else []), (debate.bear if debate else [])
    sc.more_positive_if = [clean(p.text) for p in bear[:3]]
    sc.more_cautious_if = [clean(p.text) for p in bull[:3]]
    if ceiling is not None:
        sc.notes.append(f"the ceiling is {ceiling:.1f}% of a portfolio: risk per position divided by the volatility-based stop distance, capped by your single-stock limit")
    else:
        sc.notes.append("no exposure ceiling could be computed (volatility or the average move is unavailable)")
    return sc


def scenario_lines(sc: Scenario) -> list[str]:
    if not sc.applies:
        return []
    out = ["", f"SCENARIO PLAN (educational arithmetic, not a forecast and not advice): {sc.headline}", f"  {sc.summary}"]
    out += [f"  level: {l} {_inr(v)}: {m}" for l, v, m in sc.levels]
    for label, pct, cond in sc.stages:
        size = "size depends on your ceiling" if pct is None else f"up to {pct:.1f}% of a portfolio"
        out.append(f"  stage: {label}: {size}; {cond}")
    out += [f"  watch: {w}" for w in sc.watch]
    if sc.more_positive_if:
        out.append("  would turn more positive if these improve: " + "; ".join(sc.more_positive_if))
    if sc.more_cautious_if:
        out.append("  would turn more cautious if these fade: " + "; ".join(sc.more_cautious_if))
    out += [f"  note: {n}" for n in sc.notes]
    return out
