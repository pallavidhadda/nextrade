from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from indiafacts.checklist import checklist, summarize
from indiafacts.peers import compare_peers, select_peers
from indiafacts.pipeline import AmbiguousSymbol, build_factset
from indiafacts.profile import InvestorProfile, ProfileError, default_path, default_profile, load_profile, save_profile
from indiafacts.prices import YfinancePriceClient
from indiafacts.render import render
from indiafacts.scoring import load_score_config, score_universe
from indiafacts.universe import DEFAULT_POOL, build_universe, read_pool


def main(argv: list[str] | None = None, client=None, sleep=time.sleep, price_client=None, tej_store=None,
         llm_client=None) -> int:
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
    p.add_argument("--universe", default=None, help="file with one ticker per line, or tej / tej:N for the top-N liquid names; implies --score")
    p.add_argument("--labels", type=Path, default=None, help="NSE index CSV used only for industry labels and ISINs")
    p.add_argument("--explain", action="store_true", help="add an evidence-linked plain-English explanation (deterministic template by default)")
    p.add_argument("--llm", choices=["gemini", "openai", "anthropic"], default=None, help="let an LLM narrate the digest (needs a key in the environment); implies --explain")
    p.add_argument("--llm-model", default=None)
    p.add_argument("--html", type=Path, default=None, help="also write a self-contained HTML report with charts")
    p.add_argument("--no-tej", action="store_true", help="do not use TejHQ open data (identity, corporate actions, universe)")
    args = p.parse_args(argv)
    try:
        profile, is_default = _profile(args)
        if args.llm and llm_client is None:
            from indiafacts.llm import make_client

            llm_client = make_client(args.llm, args.llm_model)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        fs = build_factset(args.ticker, as_of=args.as_of, client=client, sleep=sleep,
                           filing_path=args.filing, symbol_changes=args.symbol_changes,
                           prices=not args.no_prices, price_client=price_client,
                           tej=not args.no_tej, tej_store=tej_store)
    except AmbiguousSymbol as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    scorecard = None
    if args.score or args.universe:
        try:
            scorecard = _scorecard(args, fs, profile, client, sleep, price_client, tej_store)
            fs = scorecard.pop("target_fs", fs)          # the same facts, now carrying NSE labels and ISIN
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    explanation = digest = None
    if args.explain or args.llm or llm_client is not None:
        from indiafacts.digest import build_digest
        from indiafacts.llm import explain as explain_report

        digest = build_digest(fs, scorecard, profile)
        explanation = explain_report(digest, scorecard, fs, client=llm_client if (args.llm or llm_client) else None)
    print(render(fs, as_of=args.as_of, profile=profile, profile_is_default=is_default,
                 view=args.view or profile.view, scorecard=scorecard, explanation=explanation, digest=digest))
    if args.html:
        from indiafacts.htmlreport import build_html

        page = build_html(fs, profile, is_default, args.view or profile.view, scorecard, args.as_of, explanation=explanation, digest=digest)
        args.html.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.html.with_suffix(args.html.suffix + ".tmp")
        tmp.write_text(page, encoding="utf-8")
        tmp.replace(args.html)
        print(f"wrote {args.html} ({len(page) // 1024} KB, self-contained)")
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


def _scorecard(args, fs, profile, client, sleep, price_client, tej_store=None) -> dict:
    from indiafacts.profile import weights_for

    uni = args.universe
    if uni and str(uni).startswith("tej"):
        from indiafacts.tej import TejStore, TejUnavailable, universe_members

        n = int(str(uni).split(":")[1]) if ":" in str(uni) else 100
        try:
            members = universe_members((tej_store or TejStore()).load("universe/nse_liquid.parquet"),
                                       args.as_of or date.today(), n)
        except TejUnavailable as exc:
            raise ValueError(f"TejHQ universe unavailable: {exc}") from exc
        tickers = [m.symbol + ".NS" for m in members]
        labels = read_pool(args.labels).labels if args.labels else {}
        label = f"TejHQ top-{n} by liquidity (point-in-time)"
    else:
        path = Path(uni) if uni else DEFAULT_POOL
        pool = read_pool(path)
        tickers, labels = pool.tickers, pool.labels
        if args.labels:
            labels = {**read_pool(args.labels).labels, **labels}
        label = path.name
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
                             prices=prices, price_client=memo, tej=not args.no_tej, tej_store=tej_store)

    universe, failed = build_universe(tickers, builder, labels=labels, fresh={target: fs})
    cfg = load_score_config(strict=False)
    results = score_universe(universe, weights_for(profile), cfg, args.as_of or date.today(), datetime.now(timezone.utc))
    tgt = universe.get(target, fs)
    group = select_peers(tgt, universe)
    comparisons = compare_peers(tgt, group, universe) if group.picks else []
    return {"peers": group, "peer_comparisons": comparisons,
            "result": results.get(target), "n": len(universe), "failed": failed, "pool": label,
            "checklist": checklist(fs), "checklist_summary": summarize(checklist(fs)), "target_fs": tgt,
            "config_overdue": cfg.overdue, "default_pool": args.universe is None, "pool_label": label}
