"""Local investor profile. The USER sets the horizon; the agent only derives weights and the evaluation window from it.
Research/education only: a profile never produces a buy or sell instruction."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PRESETS_PATH = Path(__file__).parent / "data" / "weight_presets.json"
LEVELS = ("low", "medium", "high")
EVAL_DAYS = {"<1y": 63, "1-3y": 504, "3-5y": 1008, "5y+": 1260}      # trading days; proposals


class ProfileError(ValueError):
    pass


def default_path() -> Path:
    return Path.home() / ".indiafacts" / "profile.json"


class InvestorProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: Literal["growth", "income", "preservation"] = "growth"
    horizon: Literal["<1y", "1-3y", "3-5y", "5y+"] = "5y+"
    risk_tolerance: Literal["low", "medium", "high"] = "medium"
    risk_capacity: Literal["low", "medium", "high"] = "medium"
    max_single_stock_pct: float = Field(default=10, gt=0, le=100)
    liquidity_need: Literal["can_lock_away", "may_need_within_1y"] = "can_lock_away"
    experience: Literal["beginner", "expert"] = "beginner"

    @property
    def effective_risk(self) -> str:
        return min(self.risk_tolerance, self.risk_capacity, key=LEVELS.index)

    @property
    def view(self) -> str:
        return "simple" if self.experience == "beginner" else "pro"

    @property
    def profile_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:10]


def default_profile() -> InvestorProfile:
    return InvestorProfile()


def eval_horizon_days(p: InvestorProfile) -> int:
    return EVAL_DAYS[p.horizon]


def save_profile(p: InvestorProfile, path: Path | None = None) -> Path:
    path = Path(path or default_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(p.model_dump(), indent=2), encoding="utf-8")
    return path


def load_profile(path: Path | None = None) -> InvestorProfile:
    path = Path(path or default_path())
    try:
        return InvestorProfile(**json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ProfileError(f"invalid profile file {path}: {exc}") from exc


def load_presets(path: Path | None = None, today: date | None = None, strict: bool = True) -> dict[str, dict[str, float]]:
    """strict=True (tests/CI): overdue review raises. Runtime callers use strict=False and check presets_overdue()."""
    data = json.loads(Path(path or PRESETS_PATH).read_text(encoding="utf-8"))
    if strict and date.fromisoformat(data["review_by"]) < (today or date.today()):
        raise ValueError(f"weight presets: review overdue (review_by {data['review_by']})")
    for horizon, w in data["presets"].items():
        if abs(sum(w.values()) - 1.0) > 1e-9:
            raise ValueError(f"weight preset {horizon!r}: weights sum to {sum(w.values())}, expected 1.0")
    return data["presets"]


def presets_overdue(path: Path | None = None, today: date | None = None) -> str | None:
    data = json.loads(Path(path or PRESETS_PATH).read_text(encoding="utf-8"))
    return data["review_by"] if date.fromisoformat(data["review_by"]) < (today or date.today()) else None


def weights_for(p: InvestorProfile, presets: dict | None = None) -> dict[str, float]:
    return dict((presets or load_presets(strict=False))[p.horizon])
