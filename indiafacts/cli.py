from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from indiafacts.checklist import checklist, summarize
from indiafacts.pipeline import AmbiguousSymbol, build_factset
from indiafacts.profile import InvestorProfile, ProfileError, default_path, default_profile, load_profile, save_profile
from indiafacts.prices import YfinancePriceClient
from indiafacts.render import render
from indiafacts.scoring import load_score_config, score_universe
from indiafacts.universe import DEFAULT_POOL, build_universe, read_tickers


def main(argv: list[str] | None = None, client=None, sleep=time.sleep, price_client=None) -> int:
    p = argparse.ArgumentParser(prog="indiafacts", description="Source-linked facts for an NSE/BSE ticker.")
    p.add_argument("ticker", help="e.g. RELIANCE.NS")
    p.add_argument("--as-of", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    p.add_argument("--filing", type=Path, default=None, help="saved NSE results page (.html/.mhtml) for official figures")
    p.add_argument("--symbol-changes", type=Path, default=None, help="NSE symbolchange.csv (default ~/.indiafacts/symbolchange.csv)")
    p.add_argument("--no-prices", action="store_true", help="skip price-history metrics")
    p.add_argument("--profile", type=Path, default=None, help="profile JSON (default ~/.indiafacts/profile.json)")
    p.add_argument("--goal", choices=["growth", "income", "preservation"])
    p.add_argument("--horizon", choices=["<1y", "1-3y", "3-5y", "5y+"])
    p.add_argument("--risk-tolerance", choices=["low", "medium", "high"])
    p.add_argument("--risk-capacity", choices=["low", "medium", "high"])
    p.add_argument("--max-single-stock-pct", type=float)
    p.add_argument("--liquidity", choices=["can_lock_away", "may_need_within_1y"])
    p.add_argument("--experience", choices=["beginner", "expert"])
    p.add_argument("--save-profile", action="store_true", help="save the profile (after any overrides)")
    p.add_argument("--view", choices=["simple", "pro"], help="override the view chosen by experience")
    p.add_argument("--score", action="store_true", help="rank against a comparison pool (default: built-in pool of 30)")
    p.add_argument("--universe", type=Path, default=None, help="file with one ticker per line; implies --score")
    args = p.parse_args(argv)
    try:
        profile, is_default = _profile(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        fs = build_factset(args.ticker, as_of=args.as_of, client=client, sleep=sleep,
                           filing_path=args.filing, symbol_changes=args.symbol_changes,
                           prices=not args.no_prices, price_client=price_client)
    except AmbiguousSymbol as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    scorecard = None
    if args.score or args.universe:
        try:
            scorecard = _scorecard(args, fs, profile, client, sleep, price_client)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    print(render(fs, as_of=args.as_of, profile=profile, profile_is_default=is_default,
                 view=args.view or profile.view, scorecard=scorecard))
    return 0


def _profile(args) -> tuple[InvestorProfile, bool]:
    path = args.profile or default_path()
    is_default = not Path(path).exists()
    base = default_profile() if is_default else load_profile(path)
    overrides = {k: v for k, v in {
        "goal": args.goal, "horizon": args.horizon, "risk_tolerance": args.risk_tolerance,
        "risk_capacity": args.risk_capacity, "max_single_stock_pct": args.max_single_stock_pct,
        "liquidity_need": args.liquidity, "experience": args.experience}.items() if v is not None}
    profile = InvestorProfile(**{**base.model_dump(), **overrides}) if overrides else base
    if overrides or args.save_profile:
        is_default = False if overrides else is_default
    if args.save_profile:
        save_profile(profile, path)
        is_default = False
    return profile, is_default


class _MemoPrices:
    """Fetch each price series once per run (the benchmark is shared by every pool member)."""

    def __init__(self, inner):
        self.inner, self.memo = inner, {}

    def history(self, symbol):
        if symbol not in self.memo:
            self.memo[symbol] = self.inner.history(symbol)
        return self.memo[symbol]


def _scorecard(args, fs, profile, client, sleep, price_client) -> dict:
    from indiafacts.profile import weights_for

    path = args.universe or DEFAULT_POOL
    tickers = read_tickers(path)
    target = fs.entity.ticker
    if target not in tickers:
        tickers.append(target)
    prices = not args.no_prices
    memo = _MemoPrices(price_client or YfinancePriceClient()) if prices else None
    done = {"n": 0}

    def builder(t):
        done["n"] += 1
        print(f"[{done['n']}/{len(tickers)}] {t}", file=sys.stderr)
        if t == target:
            return fs
        return build_factset(t, as_of=args.as_of, client=client, sleep=sleep, symbol_changes=args.symbol_changes,
                             prices=prices, price_client=memo)

    universe, failed = build_universe(tickers, builder)
    cfg = load_score_config(strict=False)
    results = score_universe(universe, weights_for(profile), cfg, args.as_of or date.today(), datetime.now(timezone.utc))
    return {"result": results.get(target), "n": len(universe), "failed": failed, "pool": str(path.name),
            "checklist": checklist(fs), "checklist_summary": summarize(checklist(fs)),
            "config_overdue": cfg.overdue, "default_pool": args.universe is None}
