"""Price-signal scorecard: did simple, rule-fixed price signals rank next-period returns on a point-in-time universe?
History only; says nothing about the future. Education only; not financial, investment or trading advice."""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd

DISCLAIMER = "Not financial, investment or trading advice. A historical test of simple price signals is not evidence that any score predicts future returns."
SIGNALS = ("mom_12_1", "low_vol", "near_high", "composite")
LOOKBACK = 252
SKIP = 21
CAVEATS = (
    "In-sample history, a single path; nothing here was tuned on the results.",
    "Four signals were tested, so some apparent edge can appear by chance (multiple comparisons).",
    "Costs are an assumption (round trip on the replaced share of the top bucket); no taxes, market impact or liquidity limits.",
    "A name that stopped trading before the period ended keeps its last available price (carried), which can flatter or hurt results.",
    "Adjusted prices include splits, bonuses and dividends; a demerger or merger is not scaled, so such names can mislead.",
    "The benchmark is the equal-weight average of the same universe, not an index; symbols are matched by name, so renamed companies split into two series.",
)


class PanelSource(Protocol):
    def prices(self, start: date | None, end: date | None) -> pd.DataFrame: ...
    def members(self, as_of: date) -> list[str]: ...


@dataclass(frozen=True)
class BacktestConfig:
    horizon_days: int = 21
    quantiles: int = 5
    cost_bps: float = 30.0
    start: date | None = None
    end: date | None = None
    oos_start: date | None = None


@dataclass
class Half:
    periods: int
    ic_mean: float
    net_excess_mean: float
    first_date: date | None = None
    last_date: date | None = None


@dataclass
class SignalResult:
    name: str
    periods: int = 0
    ic_mean: float = float("nan")
    ic_t: float = float("nan")
    bucket_means: list[float] = field(default_factory=list)
    spread: float = float("nan")
    hit_rate: float = float("nan")
    gross_excess_mean: float = float("nan")
    net_excess_mean: float = float("nan")
    turnover_mean: float = float("nan")
    halves: list[Half] = field(default_factory=list)
    in_sample: Half | None = None
    out_of_sample: Half | None = None


@dataclass
class BacktestResult:
    config: BacktestConfig
    first_date: date | None
    last_date: date | None
    periods_used: int
    periods_skipped: int
    carried: int
    universe_sizes: list[int]
    signals: dict[str, SignalResult]


def compute_signals(px: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Every value at row t uses prices up to and including t only."""
    daily = px.pct_change(fill_method=None)
    mom = px.shift(SKIP) / px.shift(LOOKBACK) - 1
    vol = -daily.rolling(LOOKBACK).std()
    near = px / px.rolling(LOOKBACK).max() - 1
    ranks = [s.rank(axis=1, pct=True) for s in (mom, vol, near)]
    comp = (ranks[0] + ranks[1] + ranks[2]) / 3
    return {"mom_12_1": mom, "low_vol": vol, "near_high": near, "composite": comp}


def forward_returns(px: pd.DataFrame, i: int, horizon: int) -> tuple[pd.Series, int]:
    end = i + horizon
    if end >= len(px):
        return pd.Series(dtype=float), 0
    start_p = px.iloc[i]
    window = px.iloc[i:end + 1]
    end_p = window.iloc[-1]
    carried_mask = end_p.isna() & start_p.notna()
    last_valid = window.ffill().iloc[-1]
    end_p = end_p.where(~carried_mask, last_valid)
    fr = (end_p / start_p - 1)[start_p.notna()].dropna()
    return fr, int(carried_mask.sum())


def _buckets(sig: pd.Series, q: int) -> pd.Series:
    return pd.qcut(sig.rank(method="first"), q, labels=False)


def _half(rows: list[dict]) -> Half:
    if not rows:
        return Half(0, float("nan"), float("nan"))
    return Half(len(rows), float(np.nanmean([r["ic"] for r in rows])), float(np.mean([r["net"] for r in rows])),
                rows[0].get("date"), rows[-1].get("date"))


def run_backtest(source: PanelSource, cfg: BacktestConfig) -> BacktestResult:
    px = source.prices(cfg.start, cfg.end)
    sigs = compute_signals(px)
    rows: dict[str, list[dict]] = {k: [] for k in SIGNALS}
    prev: dict[str, set] = {k: set() for k in SIGNALS}
    sizes: list[int] = []
    used = skipped = carried_total = 0
    first = last = None
    min_names = 2 * cfg.quantiles
    for i in range(LOOKBACK, len(px) - cfg.horizon_days, cfg.horizon_days):
        d = px.index[i].date()
        mem = set(source.members(d)) & set(px.columns)
        fr, _ = forward_returns(px, i, cfg.horizon_days)
        gone = px.iloc[i + cfg.horizon_days].isna()
        elig = [s for s in fr.index if s in mem]
        if len(elig) < min_names:
            skipped += 1
            continue
        used += 1
        carried_total += int(gone.reindex(elig).sum())
        sizes.append(len(elig))
        first = first or d
        last = d
        for name in SIGNALS:
            s = sigs[name].iloc[i].reindex(elig).dropna()
            if len(s) < min_names:
                continue
            f = fr.reindex(s.index)
            b = _buckets(s, cfg.quantiles)
            means = [float(f[b == k].mean()) for k in range(cfg.quantiles)]
            top = set(s.index[b == cfg.quantiles - 1])
            replaced = 1.0 - len(top & prev[name]) / len(top) if top else 0.0
            prev[name] = top
            cost = 2 * replaced * cfg.cost_bps / 1e4
            gross = means[-1] - float(f.mean())
            ic = float(s.rank().corr(f.rank()))
            rows[name].append({"date": d, "ic": ic, "means": means, "gross": gross, "net": gross - cost, "turn": replaced})
    out: dict[str, SignalResult] = {}
    for name, rs in rows.items():
        r = SignalResult(name, periods=len(rs))
        if rs:
            ics = np.array([x["ic"] for x in rs])
            r.ic_mean = float(np.nanmean(ics))
            sd = float(np.nanstd(ics, ddof=1)) if len(rs) > 1 else float("nan")
            r.ic_t = r.ic_mean / sd * math.sqrt(len(rs)) if sd and sd == sd else float("nan")
            r.bucket_means = [float(np.nanmean([x["means"][k] for x in rs])) for k in range(cfg.quantiles)]
            r.spread = r.bucket_means[-1] - r.bucket_means[0]
            r.hit_rate = float(np.mean([x["gross"] > 0 for x in rs]))
            r.gross_excess_mean = float(np.mean([x["gross"] for x in rs]))
            r.net_excess_mean = float(np.mean([x["net"] for x in rs]))
            r.turnover_mean = float(np.mean([x["turn"] for x in rs]))
            h = len(rs) // 2
            r.halves = [_half(rs[:h]), _half(rs[h:])]
            if cfg.oos_start:
                r.in_sample = _half([x for x in rs if x["date"] < cfg.oos_start])
                r.out_of_sample = _half([x for x in rs if x["date"] >= cfg.oos_start])
        out[name] = r
    return BacktestResult(cfg, first, last, used, skipped, carried_total, sizes, out)


def _pct(x: float) -> str:
    return "n/a" if x != x else f"{x * 100:+.2f}%"


def render_backtest(res: BacktestResult) -> str:
    c = res.config
    lines = [
        "PRICE-SIGNAL SCORECARD (history only)",
        f"Window {res.first_date} to {res.last_date}; {res.periods_used} rebalances of {c.horizon_days} trading days "
        f"({res.periods_skipped} skipped for too few names); universe {min(res.universe_sizes, default=0)}-{max(res.universe_sizes, default=0)} names; "
        f"carried returns: {res.carried}; one-way cost assumption {c.cost_bps:g} bps.",
        "Excess = top-quintile mean minus equal-weight universe mean, per period. IC = rank correlation of signal and next-period return.",
        "",
        f"{'signal':<10} {'IC':>7} {'IC t':>6} {'Q5-Q1':>8} {'hit':>5} {'gross':>8} {'net':>8} {'turn':>5}  halves (net)",
    ]
    for n in SIGNALS:
        r = res.signals[n]
        halves = " / ".join(_pct(h.net_excess_mean) for h in r.halves) or "n/a"
        lines.append(f"{n:<10} {r.ic_mean:>7.3f} {r.ic_t:>6.1f} {_pct(r.spread):>8} {r.hit_rate * 100 if r.hit_rate == r.hit_rate else float('nan'):>4.0f}% "
                     f"{_pct(r.gross_excess_mean):>8} {_pct(r.net_excess_mean):>8} {r.turnover_mean:>5.2f}  {halves}")
    if c.oos_start:
        lines += ["", f"Split at {c.oos_start} (chosen before this run): in-sample before, out-of-sample from that date. "
                  "The signals were first seen on the full history, so this split is not untouched evidence.",
                  f"{'signal':<10} {'in-sample IC':>12} {'net':>8} {'n':>4}   {'out-of-sample IC':>16} {'net':>8} {'n':>4}"]
        for n in SIGNALS:
            a, b = res.signals[n].in_sample, res.signals[n].out_of_sample
            if a and b:
                lines.append(f"{n:<10} {a.ic_mean:>12.3f} {_pct(a.net_excess_mean):>8} {a.periods:>4}   {b.ic_mean:>16.3f} {_pct(b.net_excess_mean):>8} {b.periods:>4}")
    lines += ["", "Caveats:"] + [f"- {x}" for x in CAVEATS] + ["", DISCLAIMER]
    return "\n".join(lines)


class TejPanelSource:
    """Back-adjusted NSE prices and the point-in-time liquid universe from TejHQ (cached locally)."""

    def __init__(self, store, years: range, top_n: int = 500):
        self.store, self.years, self.top_n = store, years, top_n
        self._uni = None

    def prices(self, start, end):
        frames = []
        for y in self.years:
            df = self.store.load(f"prices_adjusted/nse_{y}.parquet")[["date", "symbol", "series", "adj_close"]]
            frames.append(df[df["series"] == "EQ"])
        df = pd.concat(frames)
        df["date"] = pd.to_datetime(df["date"])
        px = df.pivot_table(index="date", columns="symbol", values="adj_close", aggfunc="last").sort_index()
        if start:
            px = px[px.index >= pd.Timestamp(start)]
        if end:
            px = px[px.index <= pd.Timestamp(end)]
        return px

    def members(self, as_of: date) -> list[str]:
        from indiafacts.tej import universe_members

        if self._uni is None:
            self._uni = self.store.load("universe/nse_liquid.parquet")
        return [m.symbol for m in universe_members(self._uni, as_of, self.top_n)]


def main(argv: list[str] | None = None, store=None) -> int:
    p = argparse.ArgumentParser(prog="indiafacts.backtest", description="Price-signal scorecard on TejHQ data (education only).")
    p.add_argument("--from-year", type=int, default=2016)
    p.add_argument("--to-year", type=int, default=date.today().year)
    p.add_argument("--horizon-days", type=int, default=21)
    p.add_argument("--cost-bps", type=float, default=30.0)
    p.add_argument("--top-n", type=int, default=500)
    p.add_argument("--oos-start", type=date.fromisoformat, default=None, help="YYYY-MM-DD: report in-sample and out-of-sample separately")
    a = p.parse_args(argv)
    if store is None:
        from indiafacts.tej import TejStore

        store = TejStore()
    src = TejPanelSource(store, range(a.from_year - 1, a.to_year + 1), a.top_n)
    res = run_backtest(src, BacktestConfig(horizon_days=a.horizon_days, cost_bps=a.cost_bps, oos_start=a.oos_start))
    print(render_backtest(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
