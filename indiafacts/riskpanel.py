"""Three risk lenses (aggressive, neutral, conservative) applied to the company's own measured volatility, drawdown and beta, with a
fixed-fractional position ceiling. Replaces three language-model debaters with arithmetic. Not advice and not personalised suitability.
Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from indiafacts.models import FactSet, Status
from indiafacts.tradeplan import Levels

PARAMS_PATH = Path(__file__).parent / "data" / "risk_lenses.json"


def load_risk_lenses(path: Path | None = None, today: date | None = None, strict: bool = True) -> dict:
    data = json.loads(Path(path or PARAMS_PATH).read_text(encoding="utf-8"))
    data["overdue"] = date.fromisoformat(data["review_by"]) < (today or date.today())
    if data["overdue"] and strict:
        raise ValueError(f"risk lenses: review overdue (review_by {data['review_by']})")
    return data


@dataclass
class Lens:
    name: str
    fits: bool | None
    breaches: list[str] = field(default_factory=list)
    max_position_pct: float | None = None
    reason: str = ""


@dataclass
class RiskPanel:
    lenses: list[Lens]
    profile_lens: str
    notes: list[str] = field(default_factory=list)


def _val(fs: FactSet, metric: str) -> float | None:
    ok = [f for f in fs.facts if f.metric == metric and f.status == Status.ok and f.value is not None]
    return float(sorted(ok, key=lambda f: f.period_end)[-1].value) if ok else None


def build_risk_panel(fs: FactSet, profile, levels: Levels | None, params: dict | None = None) -> RiskPanel:
    p = params or load_risk_lenses(strict=False)
    vol, dd, beta = _val(fs, "volatility_1y"), _val(fs, "max_drawdown_3y"), _val(fs, "beta_1y")
    stop_pct = levels.sizing_risk_pct if levels is not None else None
    out: list[Lens] = []
    for name in ("aggressive", "neutral", "conservative"):
        lim = p["lenses"][name]
        missing = [n for n, v in (("volatility", vol), ("drawdown", dd), ("beta", beta)) if v is None]
        if missing:
            out.append(Lens(name, None, [], None, f"{', '.join(missing)} not measured, so this lens cannot be applied"))
            continue
        b: list[str] = []
        if vol > lim["volatility_max"]:
            b.append(f"volatility {vol:.1%} is above this lens's limit of {lim['volatility_max']:.0%}")
        if dd < lim["drawdown_max"]:
            b.append(f"3-year drawdown {dd:.1%} is deeper than this lens's limit of {lim['drawdown_max']:.0%}")
        if beta > lim["beta_max"]:
            b.append(f"beta {beta:.2f} is above this lens's limit of {lim['beta_max']}")
        size = None
        if stop_pct:
            size = min(float(profile.max_single_stock_pct), lim["risk_per_position_pct"] / stop_pct * 100)
        out.append(Lens(name, not b, b, size))
    notes = []
    if stop_pct is None:
        notes.append("no position ceiling: it needs the 14-day average move, which is unavailable")
    if stop_pct is not None:
        notes.append(f"position ceiling = risk per position / {stop_pct:.1f}% volatility-based stop distance, capped by your single-stock limit; a sizing rule, not a suggestion to hold the stock")
    return RiskPanel(out, p["profile_map"].get(profile.effective_risk, "neutral"), notes)
