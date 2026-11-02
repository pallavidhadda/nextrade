"""Volatility-based reference levels from past closes: support and resistance for every company; a stop and two reward-to-risk
levels only when the educational rating is bullish. These are arithmetic on measured prices, not predictions and not price targets.
Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from indiafacts.models import FactSet, Status

PARAMS_PATH = Path(__file__).parent / "data" / "levels_params.json"


def load_levels_params(path: Path | None = None, today: date | None = None, strict: bool = True) -> dict:
    data = json.loads(Path(path or PARAMS_PATH).read_text(encoding="utf-8"))
    data["overdue"] = date.fromisoformat(data["review_by"]) < (today or date.today())
    if data["overdue"] and strict:
        raise ValueError(f"levels params: review overdue (review_by {data['review_by']})")
    return data


@dataclass
class Levels:
    applies: bool = False                 # a stop and reward-to-risk levels exist (bullish rating with enough data)
    last_close: float | None = None
    stop: float | None = None
    risk_pct: float | None = None         # distance from the last close to the stop, in percent of the last close
    targets: list[float] = field(default_factory=list)
    reward_risk: list[float] = field(default_factory=list)
    support: list[tuple[str, float]] = field(default_factory=list)
    resistance: list[tuple[str, float]] = field(default_factory=list)
    reason: str = ""
    notes: list[str] = field(default_factory=list)


def _val(fs: FactSet, metric: str) -> float | None:
    ok = [f for f in fs.facts if f.metric == metric and f.status == Status.ok and f.value is not None]
    return float(sorted(ok, key=lambda f: f.period_end)[-1].value) if ok else None


def reference_levels(fs: FactSet, rating: str, params: dict | None = None) -> Levels:
    p = params or load_levels_params(strict=False)
    lv = Levels()
    last = _val(fs, "last_close") or _val(fs, "price")
    if last is None:
        lv.reason = "no last close is available, so no reference levels can be computed"
        return lv
    lv.last_close = last
    named = [("50-day average", _val(fs, "sma_50")), ("200-day average", _val(fs, "sma_200")), ("52-week low", _val(fs, "low_52w")),
             ("52-week high", _val(fs, "high_52w"))]
    lv.support = [(n, v) for n, v in named if v is not None and v < last]
    lv.resistance = [(n, v) for n, v in named if v is not None and v > last]
    if rating not in p["bullish_ratings"]:
        lv.reason = "stop and reward-to-risk levels are shown only when the educational rating is bullish (Overweight or higher)"
        return lv
    move = _val(fs, "avg_move_14")
    if move is None or move <= 0:
        lv.reason = "the 14-day average move is unavailable, so a volatility-based stop cannot be computed"
        return lv
    stop = last - p["stop_multiple"] * move
    low = _val(fs, "low_52w")
    if low is not None and stop < low:
        stop = low
        lv.notes.append("the stop is held at the 52-week low")
    risk = last - stop
    if risk <= 0:
        lv.reason = "the last close is at or below the 52-week low, so no stop distance exists"
        return lv
    lv.applies, lv.stop, lv.risk_pct = True, stop, risk / last * 100
    lv.reward_risk = list(p["target_r_multiples"])
    lv.targets = [last + r * risk for r in lv.reward_risk]
    high = _val(fs, "high_52w")
    if high is not None and lv.targets and lv.targets[-1] > high:
        lv.notes.append("the second reference level lies above the 52-week high")
    return lv
