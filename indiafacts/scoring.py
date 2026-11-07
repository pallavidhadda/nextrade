"""Reproducible factor scoring. Pure functions over Facts: no imputation, no LLM, explicit weights, full provenance."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from indiafacts.models import Fact, FactSet, PeriodType, Status

SCORE_PATH = Path(__file__).parent / "data" / "score_metrics.json"
COMPUTED = "computed"
_NOT_FOR_FINANCIALS = {"debt_to_equity"}
_REQUIRED_PARAMS = ("winsorise_low", "winsorise_high", "winsorise_min_n", "min_universe", "min_factor_coverage",
                    "min_valid_factors", "max_age_days")


@dataclass(frozen=True)
class MetricSpec:
    id: str
    factor: str
    direction: str
    valid_min: float
    valid_max: float
    exclusive_min: bool = False
    optional: bool = False       # adds to a factor when data exists; its absence never lowers coverage

    def valid(self, v: float) -> bool:
        lo_ok = v > self.valid_min if self.exclusive_min else v >= self.valid_min
        return bool(np.isfinite(v)) and lo_ok and v <= self.valid_max


@dataclass
class ScoreConfig:
    metrics: list[MetricSpec]
    params: dict
    review_by: date
    base_hash: str
    overdue: bool = False


class FactorScore(BaseModel):
    score: float | None
    coverage: float
    reason: str = ""
    input_fact_ids: list[str] = []


class ScoreResult(BaseModel):
    ticker: str
    status: str                         # ok | abstain
    overall: float | None
    reason: str = ""
    rank: int | None = None
    n: int = 0
    factors: dict[str, FactorScore] = {}
    metric_scores: dict[str, float] = {}
    flags: list[str] = []
    input_fact_ids: list[str] = []
    config_hash: str = ""
    as_of: date | None = None


class RankChange(BaseModel):
    ticker: str
    old_rank: int | None
    new_rank: int | None
    delta: int


def load_score_config(path: Path | str | None = None, today: date | None = None, strict: bool = True) -> ScoreConfig:
    data = json.loads(Path(path or SCORE_PATH).read_text(encoding="utf-8"))
    review_by = date.fromisoformat(data["review_by"])
    overdue = review_by < (today or date.today())
    if overdue and strict:
        raise ValueError(f"score config: review overdue (review_by {review_by})")
    for k in _REQUIRED_PARAMS:
        if k not in data.get("params", {}):
            raise ValueError(f"score config: missing param {k}")
    specs = []
    for m in data["metrics"]:
        for k in ("id", "factor", "direction", "valid_min", "valid_max"):
            if k not in m:
                raise ValueError(f"score config: metric {m.get('id')} missing {k}")
        if m["direction"] not in ("higher", "lower"):
            raise ValueError(f"score config: metric {m['id']} direction must be higher or lower")
        if not m["valid_min"] < m["valid_max"]:
            raise ValueError(f"score config: metric {m['id']} valid_min must be below valid_max")
        specs.append(MetricSpec(m["id"], m["factor"], m["direction"], float(m["valid_min"]), float(m["valid_max"]),
                                bool(m.get("exclusive_min", False)), bool(m.get("optional", False))))
    base = hashlib.sha256(json.dumps({"m": data["metrics"], "p": data["params"]}, sort_keys=True).encode()).hexdigest()[:12]
    return ScoreConfig(specs, data["params"], review_by, base, overdue)


def _extract(fs: FactSet, cfg: ScoreConfig, as_of: date, now: datetime):
    flags: list[str] = []
    out: dict[str, tuple[float, str]] = {}
    max_age = timedelta(days=cfg.params["max_age_days"])
    financial = (fs.entity.sector or "") == "Financial Services"
    for spec in cfg.metrics:
        if financial and spec.id in _NOT_FOR_FINANCIALS:
            flags.append(f"financial company: {spec.id} not comparable for banks/lenders; excluded")
            continue
        cands = [f for f in fs.facts if f.metric == spec.id and f.status == Status.ok and f.value is not None]
        if not cands:
            continue
        cands.sort(key=lambda f: (f.period_end, f.retrieved_at))
        f = cands[-1]
        if f.available_from is not None and f.available_from > as_of:
            flags.append(f"not yet public: {spec.id} (public from {f.available_from})")
            continue
        if now - f.retrieved_at > max_age:
            flags.append(f"stale: {spec.id} retrieved {f.retrieved_at.date()}")
            continue
        v = float(f.value)
        if not spec.valid(v):
            flags.append(f"{spec.id}={v:g} outside valid range ({spec.valid_min:g}, {spec.valid_max:g}); excluded")
            continue
        out[spec.id] = (v, f.fact_id)
    return out, flags


def _percentiles(values: list[float], lo_q: float, hi_q: float, winsor_min_n: int) -> list[float]:
    arr = np.array(values, dtype=float)
    if len(arr) >= winsor_min_n:
        lo, hi = np.percentile(arr, [lo_q * 100, hi_q * 100])
        arr = np.clip(arr, lo, hi)
    n = len(arr)
    out = []
    for v in arr:
        less, equal = int(np.sum(arr < v)), int(np.sum(arr == v))
        rank_avg = less + (equal + 1) / 2
        out.append((rank_avg - 1) / (n - 1) * 100)
    return out


def score_universe(factsets: dict[str, FactSet], factor_weights: dict[str, float], cfg: ScoreConfig,
                   as_of: date, now: datetime) -> dict[str, ScoreResult]:
    tickers = sorted(factsets)
    extracted = {t: _extract(factsets[t], cfg, as_of, now) for t in tickers}
    chash = hashlib.sha256((cfg.base_hash + json.dumps(factor_weights, sort_keys=True)).encode()).hexdigest()[:12]
    p = cfg.params

    metric_scores: dict[str, dict[str, float]] = {t: {} for t in tickers}
    universe_flags: list[str] = []
    for spec in cfg.metrics:
        have = [(t, extracted[t][0][spec.id][0]) for t in tickers if spec.id in extracted[t][0]]
        if len(have) < p["min_universe"]:
            if have:
                universe_flags.append(f"{spec.id}: universe too small ({len(have)} < {p['min_universe']}); not scored")
            continue
        pcts = _percentiles([v for _, v in have], p["winsorise_low"], p["winsorise_high"], p["winsorise_min_n"])
        for (t, _), pc in zip(have, pcts):
            metric_scores[t][spec.id] = round(100 - pc if spec.direction == "lower" else pc, 4)

    factors = sorted({m.factor for m in cfg.metrics})
    results: dict[str, ScoreResult] = {}
    for t in tickers:
        vals, flags = extracted[t]
        flags = flags + universe_flags
        fscores: dict[str, FactorScore] = {}
        for fac in factors:
            specs = [m for m in cfg.metrics if m.factor == fac]
            got = [m for m in specs if m.id in metric_scores[t]]
            core = [m for m in specs if not m.optional] or specs
            cov = len([m for m in got if m in core]) / len(core)
            ids = sorted(vals[m.id][1] for m in got)
            opt_got = [m for m in got if m.optional]
            if cov < p["min_factor_coverage"] and len(opt_got) >= 2:
                cov = max(cov, p["min_factor_coverage"])          # quarterly data has gaps; annual figures carry the factor
            if cov < p["min_factor_coverage"]:
                fscores[fac] = FactorScore(score=None, coverage=round(cov, 4),
                                           reason=f"coverage {cov:.0%} < {p['min_factor_coverage']:.0%}")
            else:
                fscores[fac] = FactorScore(score=round(float(np.mean([metric_scores[t][m.id] for m in got])), 4),
                                           coverage=round(cov, 4), input_fact_ids=ids)
        valid = {f: s.score for f, s in fscores.items() if s.score is not None and factor_weights.get(f, 0) > 0}
        used = sorted(i for f in valid for i in fscores[f].input_fact_ids)
        if len(valid) < p["min_valid_factors"]:
            results[t] = ScoreResult(ticker=t, status="abstain", overall=None, n=len(tickers), factors=fscores,
                                     metric_scores=metric_scores[t], flags=flags, config_hash=chash, as_of=as_of,
                                     reason=f"fewer than {p['min_valid_factors']} valid factors ({len(valid)})")
            continue
        wsum = sum(factor_weights[f] for f in valid)
        overall = round(sum(factor_weights[f] * s for f, s in valid.items()) / wsum, 4)
        results[t] = ScoreResult(ticker=t, status="ok", overall=overall, n=len(tickers), factors=fscores,
                                 metric_scores=metric_scores[t], flags=flags, input_fact_ids=used,
                                 config_hash=chash, as_of=as_of)
    ranked = sorted((r for r in results.values() if r.status == "ok"), key=lambda r: (-r.overall, r.ticker))
    for i, r in enumerate(ranked, 1):
        r.rank = i
    return results


def rank_diff(before: dict[str, ScoreResult], after: dict[str, ScoreResult]) -> list[RankChange]:
    out = []
    for t in sorted(set(before) | set(after)):
        a, b = before.get(t), after.get(t)
        old, new = (a.rank if a else None), (b.rank if b else None)
        if old != new:
            out.append(RankChange(ticker=t, old_rank=old, new_rank=new,
                                  delta=(old - new) if old is not None and new is not None else 0))
    return sorted(out, key=lambda c: (-abs(c.delta), c.ticker))


def score_facts(result: ScoreResult, retrieved_at: datetime) -> list[Fact]:
    """Score results as Facts with provenance: inputs for ok scores, reasons for the rest."""
    src = f"scorecard:config={result.config_hash}|universe={result.n}"
    base = dict(entity_key=result.ticker, unit="score_0_100", period_end=result.as_of or date.today(),
                period_type=PeriodType.point, source=COMPUTED, source_field=src, retrieved_at=retrieved_at)
    out = []
    if result.status == "ok":
        out.append(Fact.make(metric="score_overall", value=Decimal(str(result.overall)), status=Status.ok,
                             related_fact_ids=result.input_fact_ids, **base))
    else:
        out.append(Fact.make(metric="score_overall", value=None, status=Status.unavailable,
                             reason=result.reason or "abstain", **base))
    for fac, fs in sorted(result.factors.items()):
        if fs.score is not None:
            out.append(Fact.make(metric=f"score_{fac}", value=Decimal(str(fs.score)), status=Status.ok,
                                 related_fact_ids=fs.input_fact_ids, **base))
        else:
            out.append(Fact.make(metric=f"score_{fac}", value=None, status=Status.unavailable,
                                 reason=fs.reason, **base))
    return out
