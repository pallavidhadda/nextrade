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
    "Excess is measured against the equal-weight average of the same universe; the Nifty 50 line (when shown) is the price index, "
    "which leaves out dividends (roughly 1 to 1.5% a year), so it flatters every bucket by about that much.",
    "Renamed companies are joined into one series by ISIN; a join is refused when the price jumps more than 20% at the rename "
    "(the two names were adjusted differently), and those pairs stay split.",
)
JOIN_MAX_JUMP = 0.20


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
    top_vs_benchmark: float = float("nan")     # top-quintile mean minus the benchmark's return, per period
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
    joined: int = 0
    join_refused: list[str] = field(default_factory=list)
    benchmark: str = ""


def stitch_by_isin(px: pd.DataFrame, history: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """Join the price columns of one ISIN's successive symbols into its newest symbol. Returns (prices, old->new aliases, refused pairs).
    A join is refused when the first new close is more than JOIN_MAX_JUMP away from the last old close."""
    px = px.copy()
    alias: dict[str, str] = {}
    refused: list[str] = []
    for _, g in history.groupby("isin"):
        syms = [str(x) for x in g.sort_values("valid_from")["symbol"]]
        syms = [x for i, x in enumerate(syms) if x in px.columns and x not in syms[:i]]
        if len(syms) < 2:
            continue
        new = syms[-1]
        for old in reversed(syms[:-1]):
            a, b = px[old].dropna(), px[new].dropna()
            if a.empty or b.empty:
                continue
            first_new = b[b.index > a.index[-1]]
            if first_new.empty or abs(first_new.iloc[0] / a.iloc[-1] - 1) > JOIN_MAX_JUMP:
                refused.append(f"{old}->{new}")
                continue
            px[new] = px[new].combine_first(px[old])
            px = px.drop(columns=[old])
            alias[old] = new
    return px, alias, refused


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


def run_backtest(source: PanelSource, cfg: BacktestConfig, aliases: dict[str, str] | None = None,
                 benchmark: pd.Series | None = None, benchmark_label: str = "") -> BacktestResult:
    """`aliases` maps a member's old symbol to the joined column (see stitch_by_isin); `benchmark` is an index level series."""
    px = source.prices(cfg.start, cfg.end)
    aliases = aliases or {}
    bench = benchmark.reindex(px.index).ffill() if benchmark is not None else None
    sigs = compute_signals(px)
    rows: dict[str, list[dict]] = {k: [] for k in SIGNALS}
    prev: dict[str, set] = {k: set() for k in SIGNALS}
    sizes: list[int] = []
    used = skipped = carried_total = 0
    first = last = None
    min_names = 2 * cfg.quantiles
    for i in range(LOOKBACK, len(px) - cfg.horizon_days, cfg.horizon_days):
        d = px.index[i].date()
        mem = {aliases.get(m, m) for m in source.members(d)} & set(px.columns)
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
            row = {"date": d, "ic": ic, "means": means, "gross": gross, "net": gross - cost, "turn": replaced}
            if bench is not None:
                b0, b1 = bench.iloc[i], bench.iloc[i + cfg.horizon_days]
                if b0 == b0 and b1 == b1 and b0 > 0:
                    row["vs_bench"] = means[-1] - (b1 / b0 - 1)
            rows[name].append(row)
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
            vb = [x["vs_bench"] for x in rs if "vs_bench" in x]
            r.top_vs_benchmark = float(np.mean(vb)) if vb else float("nan")
            h = len(rs) // 2
            r.halves = [_half(rs[:h]), _half(rs[h:])]
            if cfg.oos_start:
                r.in_sample = _half([x for x in rs if x["date"] < cfg.oos_start])
                r.out_of_sample = _half([x for x in rs if x["date"] >= cfg.oos_start])
        out[name] = r
    return BacktestResult(cfg, first, last, used, skipped, carried_total, sizes, out,
                          benchmark=(benchmark_label or "Nifty 50 price index") if bench is not None else "")


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
    if res.joined or res.join_refused:
        lines.append(f"Renamed companies joined by ISIN: {res.joined}; joins refused for a price jump: {len(res.join_refused)}"
                     + (f" ({', '.join(res.join_refused[:6])}{'...' if len(res.join_refused) > 6 else ''})" if res.join_refused else "") + ".")
    if res.benchmark:
        lines += ["", f"Top quintile against the {res.benchmark} (excludes dividends, so this flatters the top quintile by about "
                  "1 to 1.5% a year, roughly 0.1% a month), mean per period:",
                  "  " + "   ".join(f"{n}: {_pct(res.signals[n].top_vs_benchmark)}" for n in SIGNALS)]
    if c.oos_start:
        lines += ["", f"Split at {c.oos_start} (chosen before this run): in-sample before, out-of-sample from that date. "
                  "The signals were first seen on the full history, so this split is not untouched evidence.",
                  f"{'signal':<10} {'in-sample IC':>12} {'net':>8} {'n':>4}   {'out-of-sample IC':>16} {'net':>8} {'n':>4}"]
        for n in SIGNALS:
            a, b = res.signals[n].in_sample, res.signals[n].out_of_sample
            if a and b:
                lines.append(f"{n:<10} {a.ic_mean:>12.3f} {_pct(a.net_excess_mean):>8} {a.periods:>4}   {b.ic_mean:>16.3f} {_pct(b.net_excess_mean):>8} {b.periods:>4}")
    comp = res.signals.get("composite")
    if comp and comp.bucket_means and len(comp.bucket_means) == 5:
        ratings = ["Sell", "Underweight", "Hold", "Overweight", "Buy"]
        lines += ["", "Rating buckets (price-only composite sorted into fifths, a stand-in for the five educational ratings; not the full rating, "
                  "which also uses fundamentals that have no usable history):",
                  "  " + "   ".join(f"{r}: {_pct(m)}" for r, m in zip(ratings, comp.bucket_means)),
                  f"  mean forward {c.horizon_days}-session return per bucket; a useful ordering would rise from left to right."]
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

    def joined_prices(self, start, end):
        """(prices, aliases, refused) with renamed companies joined by ISIN."""
        return stitch_by_isin(self.prices(start, end), self.store.load("symbol_history/nse.parquet"))

    def members(self, as_of: date) -> list[str]:
        from indiafacts.tej import universe_members

        if self._uni is None:
            self._uni = self.store.load("universe/nse_liquid.parquet")
        return [m.symbol for m in universe_members(self._uni, as_of, self.top_n)]


class _Fixed:
    def __init__(self, px, members):
        self._px, self.members = px, members

    def prices(self, start, end):
        return self._px


def _nifty_levels(client=None) -> pd.Series | None:
    """Daily Nifty 50 closes (^NSEI, price index) from Yahoo, or None when unavailable."""
    from indiafacts.prices import YfinancePriceClient

    try:
        df = (client or YfinancePriceClient()).history("^NSEI")
    except Exception:
        return None
    if df is None or df.empty or "Close" not in df:
        return None
    s = df["Close"].copy()
    s.index = pd.DatetimeIndex([pd.Timestamp(t).tz_localize(None) if pd.Timestamp(t).tzinfo else pd.Timestamp(t) for t in s.index]).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def main(argv: list[str] | None = None, store=None, price_client=None) -> int:
    p = argparse.ArgumentParser(prog="indiafacts.backtest", description="Price-signal scorecard on TejHQ data (education only).")
    p.add_argument("--from-year", type=int, default=2016)
    p.add_argument("--to-year", type=int, default=date.today().year)
    p.add_argument("--horizon-days", type=int, default=21)
    p.add_argument("--cost-bps", type=float, default=30.0)
    p.add_argument("--top-n", type=int, default=500)
    p.add_argument("--oos-start", type=date.fromisoformat, default=None, help="YYYY-MM-DD: report in-sample and out-of-sample separately")
    p.add_argument("--no-join", action="store_true", help="do not join renamed companies by ISIN")
    p.add_argument("--benchmark", action="store_true", help="also compare the top quintile with the Nifty 50 price index (Yahoo ^NSEI)")
    a = p.parse_args(argv)
    if store is None:
        from indiafacts.tej import TejStore

        store = TejStore()
    src = TejPanelSource(store, range(a.from_year - 1, a.to_year + 1), a.top_n)
    aliases, refused = {}, []
    if not a.no_join:
        px, aliases, refused = src.joined_prices(None, None)
        src = _Fixed(px, src.members)
    bench = None
    if a.benchmark:
        bench = _nifty_levels(price_client)
    res = run_backtest(src, BacktestConfig(horizon_days=a.horizon_days, cost_bps=a.cost_bps, oos_start=a.oos_start),
                       aliases=aliases, benchmark=bench)
    res.joined, res.join_refused = len(aliases), refused
    print(render_backtest(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
