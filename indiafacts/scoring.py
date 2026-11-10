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


class FactorContribution(BaseModel):
    """One scored factor's part in the overall: contribution = effective_weight x score, effective weights sum to 1."""
    score: float
    base_weight: float                  # the preset's weight for the factor
    effective_weight: float             # base weight renormalised over the factors that were scored
    contribution: float                 # effective_weight x score; contributions add up to the overall
    coverage: float
    n_metrics: int                      # metrics that fed the factor score


class MissingFactor(BaseModel):
    factor: str
    base_weight: float                  # weight the preset gave it, now redistributed over the scored factors
    reason: str = ""


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
    contributions: dict[str, FactorContribution] = {}        # empty when the score abstained
    missing_factors: list[MissingFactor] = []
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


def _rank(f: Fact) -> int:
    from indiafacts.analysis import SOURCE_RANK

    return SOURCE_RANK.index(f.source) if f.source in SOURCE_RANK else len(SOURCE_RANK)


def _extract(fs: FactSet, cfg: ScoreConfig, as_of: date, now: datetime):
    facts, flags = extract_facts(fs, cfg, as_of, now)
    return {m: (float(f.value), f.fact_id) for m, f in facts.items()}, flags


def extract_facts(fs: FactSet, cfg: ScoreConfig, as_of: date, now: datetime):
    """The Fact scoring would use for each metric, under the scoring rules (best source, latest period, not-yet-public,
    stale, valid bounds, financials). Shared with poolstore so stored values equal what scoring uses."""
    flags: list[str] = []
    out: dict[str, Fact] = {}
    max_age = timedelta(days=cfg.params["max_age_days"])
    financial = (fs.entity.sector or "") == "Financial Services"
    for spec in cfg.metrics:
        if financial and spec.id in _NOT_FOR_FINANCIALS:
            flags.append(f"financial company: {spec.id} not comparable for banks/lenders; excluded")
            continue
        cands = [f for f in fs.facts if f.metric == spec.id and f.status == Status.ok and f.value is not None]
        if not cands:
            continue
        pts = [f for f in cands if f.period_type == PeriodType.point]
        if pts and len({f.source for f in pts}) > 1:                   # snapshots from several sources: the best-ranked source wins
            best = min(_rank(f) for f in pts)
            cands = [f for f in cands if f.period_type != PeriodType.point or _rank(f) == best]
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
        out[spec.id] = f
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
        missing = [MissingFactor(factor=f, base_weight=factor_weights[f], reason=s.reason)
                   for f, s in sorted(fscores.items()) if s.score is None and factor_weights.get(f, 0) > 0]
        used = sorted(i for f in valid for i in fscores[f].input_fact_ids)
        if len(valid) < p["min_valid_factors"]:
            results[t] = ScoreResult(ticker=t, status="abstain", overall=None, n=len(tickers), factors=fscores,
                                     metric_scores=metric_scores[t], flags=flags, config_hash=chash, as_of=as_of,
                                     missing_factors=missing, reason=f"fewer than {p['min_valid_factors']} valid factors ({len(valid)})")
            continue
        wsum = sum(factor_weights[f] for f in valid)
        overall = round(sum(factor_weights[f] * s for f, s in valid.items()) / wsum, 4)
        contribs = {f: FactorContribution(score=s, base_weight=factor_weights[f], effective_weight=round(factor_weights[f] / wsum, 6),
                                          contribution=round(factor_weights[f] / wsum * s, 4), coverage=fscores[f].coverage,
                                          n_metrics=len(fscores[f].input_fact_ids))
                    for f, s in valid.items()}
        results[t] = ScoreResult(ticker=t, status="ok", overall=overall, n=len(tickers), factors=fscores,
                                 contributions=contribs, missing_factors=missing,
                                 metric_scores=metric_scores[t], flags=flags, input_fact_ids=used,
                                 config_hash=chash, as_of=as_of)
    ranked = sorted((r for r in results.values() if r.status == "ok"), key=lambda r: (-r.overall, r.ticker))
    for i, r in enumerate(ranked, 1):
        r.rank = i
    return results


POLICY_PATH = Path(__file__).parent / "data" / "source_policy.json"


def load_source_policy(path: Path | None = None) -> dict:
    data = json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))
    if not isinstance(data.get("metrics"), dict) or not 0 < float(data.get("min_coverage", 0)) <= 1:
        raise ValueError("source policy: needs metrics and a min_coverage in (0, 1]")
    return data


def factsets_from_sources(members: list[str], target_fs: FactSet, store: dict | None, ml_rows: dict | None, policy: dict,
                          cfg: ScoreConfig, as_of: date, now: datetime, nifty_1y: float | None = None,
                          store_at: datetime | None = None) -> tuple[dict[str, FactSet], dict[str, dict]]:
    """Synthetic FactSets for score_universe in which every metric comes from ONE source for ALL members.
    Per metric the first policy candidate ('pool_store' = pool_metrics.json, 'nse_marketlens' = Market Lens rows) that has a valid
    value for at least policy min_coverage of the members wins; a metric with no such source is left out (not scored).
    The target counts as a member: its pool_store value is its own freshly computed one, its Market Lens value is its row's.
    Returns (factsets by ticker, metric_sources {metric: {source, covered, of}}); source is None when nothing qualified."""
    from indiafacts import marketlens
    from indiafacts.models import Entity

    target = target_fs.entity.ticker
    members = sorted(set(members) | {target})
    n = len(members)
    smetrics = (store or {}).get("metrics") or {}
    ml_rows = ml_rows or {}
    ml_vals = {t: marketlens.score_metrics_for(ml_rows.get(t.split(".")[0]) or {}, nifty_1y) for t in members}
    fresh, _ = extract_facts(target_fs, cfg, as_of, now)
    min_cov = float(policy["min_coverage"])

    def store_val(t: str, m: str):
        if t == target and m in fresh:
            f = fresh[m]
            return float(f.value), f.source, f.period_end, f.fact_id
        e = (smetrics.get(t) or {}).get(m)
        if not isinstance(e, dict) or not isinstance(e.get("value"), (int, float)):
            return None
        try:
            end = date.fromisoformat(str(e.get("as_of")))
        except ValueError:
            return None
        return float(e["value"]), str(e.get("source") or "unknown"), end, None

    def ml_val(t: str, m: str):
        v = ml_vals[t].get(m)
        return None if v is None else (v, marketlens.SOURCE, marketlens.row_as_of(ml_rows[t.split(".")[0]], now), None)

    getters = {"pool_store": store_val, "nse_marketlens": ml_val}
    chosen: dict[str, dict[str, tuple]] = {t: {} for t in members}
    sources: dict[str, dict] = {}
    for spec in cfg.metrics:
        best = 0
        sources[spec.id] = {"source": None, "covered": 0, "of": n}
        for name in policy["metrics"].get(spec.id, []):
            get = getters.get(name)
            if get is None:
                continue
            vals = {}
            for t in members:
                got = get(t, spec.id)
                if got is not None and spec.valid(got[0]):
                    vals[t] = got
            best = max(best, len(vals))
            if vals and len(vals) / n >= min_cov:
                for t, got in vals.items():
                    chosen[t][spec.id] = got
                sources[spec.id] = {"source": name, "covered": len(vals), "of": n}
                break
        else:
            sources[spec.id]["covered"] = best          # the best attempt, so the reason can be shown
    out: dict[str, FactSet] = {}
    for t in members:
        if t == target:
            ent = target_fs.entity
        else:
            row = ml_rows.get(t.split(".")[0]) or {}
            ent = Entity.from_ticker(t).model_copy(update={
                "name": row.get("name"), "sector": "Financial Services" if row.get("subSector") == "Financial Services" else None})
        facts = []
        for m, (v, src, end, _fid) in chosen[t].items():
            label = marketlens.SOURCE if src == marketlens.SOURCE else f"pool_store:{src}"
            ev = ("NSE Market Lens row used for every company in the comparison" if src == marketlens.SOURCE
                  else f"pool_metrics.json (daily snapshot), originally from {src}; used for every company in the comparison")
            facts.append(Fact.make(entity_key=t, metric=m, value=Decimal(str(round(v, 10))), unit="score_input", period_end=end,
                                   period_type=PeriodType.point, source=label, source_field=f"source_policy:{m}",
                                   retrieved_at=(store_at or now) if label.startswith("pool_store") and t != target else now,
                                   status=Status.ok, evidence=ev))
        out[t] = FactSet(entity=ent, facts=facts, retrieved_at=now)
    return out, sources


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
