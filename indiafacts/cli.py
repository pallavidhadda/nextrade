from __future__ import annotations

import argparse
import sys
import threading
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
         llm_client=None, brain=None, news_client=None, journal=None) -> int:
    p = argparse.ArgumentParser(prog="indiafacts", description="Source-linked facts for an NSE/BSE ticker.")
    p.add_argument("ticker", help="e.g. RELIANCE.NS")
    p.add_argument("--as-of", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    p.add_argument("--filing", type=Path, action="append", default=None,
                   help="saved NSE results page (.html/.mhtml) or raw XBRL file (.xml); repeat it for other quarters or a revised filing")
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
    p.add_argument("--filings-dir", type=Path, default=None,
                   help="folder of saved NSE results pages; every page for this company is used (others are skipped with a notice)")
    p.add_argument("--labels", type=Path, default=None, help="NSE index CSV used only for industry labels and ISINs")
    p.add_argument("--explain", action="store_true", help="add an evidence-linked plain-English explanation (deterministic template by default)")
    p.add_argument("--llm", choices=["gemini", "openai", "anthropic"], default=None, help="let an LLM narrate the digest (needs a key in the environment); implies --explain")
    p.add_argument("--llm-model", default=None)
    p.add_argument("--no-remember", action="store_true", help="do not save this run to the local snapshot store (~/.indiafacts/brain.db)")
    p.add_argument("--changes", action="store_true", help="always show the what-changed block, even on a first run")
    p.add_argument("--digest", action="store_true", help="print only the compact evidence digest and narration rules (for Claude Code or any LLM; zero API tokens here)")
    p.add_argument("--changes-only", action="store_true", help="print only the what-changed block")
    p.add_argument("--sector-pool", action="store_true", help="with an NSE index CSV: compare only against the target's NSE industry group (faster, sector-relative scores)")
    p.add_argument("--news", action="store_true", help="also fetch recent headlines (extra network call; shown as unverified text with a keyword sentiment hint)")
    p.add_argument("--comparison", choices=("auto", "pool"), default="auto", help="auto (default): rank inside the target's NSE Market Lens sector using the published comparison data; pool: always fetch and rank the pool file")
    p.add_argument("--pool-size", type=int, default=None, help="use only the first N companies of the pool (plus the target): faster, a smaller comparison")
    p.add_argument("--shareholding", type=Path, action="append", default=None,
                   help="shareholding-pattern XBRL file saved from NSE (Corporate Filings > Shareholding Pattern); repeat for earlier quarters")
    p.add_argument("--no-feed", action="store_true", help="do not look in the exchange's latest shareholding feed")
    p.add_argument("--no-marketlens", action="store_true", help="do not use NSE Market Lens (the exchange's screener) for figures and peers")
    p.add_argument("--no-nse-api", action="store_true", help="do not fetch official shareholding and quarterly results from NSE's website API")
    p.add_argument("--flows", action="store_true", help="also show market-wide FII/DII/Pro/Client index-futures positioning from the exchange's daily file")
    p.add_argument("--announcements", action="store_true", help="also list this company's latest filings from the exchange's public RSS feed (links to the filings)")
    p.add_argument("--json", type=Path, default=None, help="also write a compact JSON summary (used by the web app)")
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
                           filing_path=_filing_paths(args), skip_other_filings=bool(args.filings_dir), symbol_changes=args.symbol_changes,
                           prices=not args.no_prices, price_client=price_client,
                           tej=not args.no_tej, tej_store=tej_store,
                           shareholding_paths=_shp_paths(args), shareholding_feed=(client is None and not args.no_feed), marketlens=not getattr(args, "no_marketlens", False),
                           nse_api=not getattr(args, "no_nse_api", False))
    except AmbiguousSymbol as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from indiafacts.models import Status as _S

    if not any(f.status == _S.ok for f in fs.facts) and not fs.not_yet_public:
        from indiafacts.companies import resolve

        _, sugg = resolve(args.ticker)
        hint = ("The ticker may be mistyped. Did you mean: " + ", ".join(m.label for m in sugg[:3]) + "? ") if sugg else ""
        print(f"fetch detail: {fs.entity.resolution_reason}", file=sys.stderr)          # the vendor error, for the server log
        print(f"error: could not fetch any data for {fs.entity.ticker}. {hint}Otherwise this usually means this machine cannot reach "
              "Yahoo Finance (no network, a proxy or a sandbox), or the ticker has changed. Nothing was analysed. "
              "If the NexTrade connector is available, use it instead; otherwise retry with network access.", file=sys.stderr)
        return 5
    scorecard = None
    if args.score or args.universe:
        try:
            scorecard = _scorecard(args, fs, profile, client, sleep, price_client, tej_store)
            fs = scorecard.pop("target_fs", fs)          # the same facts, now carrying NSE labels and ISIN
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    changes = changes_note = None
    if not args.no_remember:
        from datetime import datetime as _dt, timezone as _tz

        from indiafacts.brain import Brain

        b = brain or Brain()
        run_id = b.safe_record_run(fs, scorecard, profile, _dt.now(_tz.utc))
        if run_id is None:
            fs = fs.model_copy(update={"notices": fs.notices + [f"could not save the snapshot ({b.last_error}); the report is unaffected"]})
        else:
            try:
                changes = b.changes(fs.entity.ticker)
                changes_note = None if changes else "no changes since the previous run" if b.stats()["runs"] > 1 else "first run: nothing to compare yet"
            except Exception as exc:
                fs = fs.model_copy(update={"notices": fs.notices + [f"could not read earlier snapshots ({type(exc).__name__})"]})
    elif args.changes:
        changes_note = "snapshot store is off (--no-remember): nothing to compare"
    if changes_note is None and args.changes and not changes:
        changes_note = "first run: nothing to compare yet"
    from indiafacts.debate import build_debate

    news, news_note = [], ""
    if args.news:
        from indiafacts.news import fetch_news
        from indiafacts.nsefeed import recent_for

        news, news_note = fetch_news(fs.entity.ticker, news_client, nse=recent_for if news_client is None else None)
        if news_note:
            fs = fs.model_copy(update={"notices": fs.notices + [news_note]})
    from indiafacts.riskpanel import build_risk_panel
    from indiafacts.tradeplan import reference_levels

    flows = None
    if args.flows:
        from indiafacts import flows as _flows

        flows = _flows.combined()
    debate = build_debate(fs, scorecard)
    levels = reference_levels(fs, debate.stance.label)
    panel = build_risk_panel(fs, profile, levels)
    from indiafacts.narrative import case_prose
    from indiafacts.scenario import build_scenario

    scenario = build_scenario(fs, debate, levels, panel, today=args.as_of)
    prose = case_prose(debate, scorecard)
    from indiafacts.debate import has_direction

    if not args.no_remember and has_direction(debate.stance.label) and not debate.stance.partial:
        try:
            from indiafacts.journal import Journal

            (journal or Journal()).record(fs.entity.ticker, args.as_of or date.today(), debate.stance.label, debate.stance.confidence,
                                          scorecard["result"].overall if scorecard and scorecard.get("result") else None,
                                          levels.last_close, profile.profile_hash)
        except Exception as exc:                                         # the journal must never break a report
            fs = fs.model_copy(update={"notices": fs.notices + [f"could not record the rating in the decision journal ({type(exc).__name__})"]})
    explanation = digest = None
    if args.explain or args.llm or llm_client is not None:
        from indiafacts.digest import build_digest
        from indiafacts.llm import explain as explain_report

        digest = build_digest(fs, scorecard, profile, news=news, debate=debate, levels=levels, panel=panel)
        explanation = explain_report(digest, scorecard, fs, client=llm_client if (args.llm or llm_client) else None)
    if args.changes_only:
        from indiafacts.render import _changes_block

        print("\n".join(_changes_block(changes, changes_note or "first run: nothing to compare yet")).strip() or "no changes since the previous run")
    elif args.digest:
        from indiafacts.digest import build_digest as _bd
        from indiafacts.llm import NARRATION_RULES

        dg = digest or _bd(fs, scorecard, profile, news=news, debate=debate, levels=levels, panel=panel)
        print(f"DIGEST for {fs.entity.ticker} (about {dg.est_tokens} estimated tokens; cite the ids F1, F2...)\n{dg.text}\n\n{NARRATION_RULES}")
    else:
        print(render(fs, as_of=args.as_of, profile=profile, profile_is_default=is_default,
                 view=args.view or profile.view, scorecard=scorecard, explanation=explanation, digest=digest,
                 changes=changes, changes_note=changes_note if (args.changes or not changes) else None, debate=debate, news=news, levels=levels, panel=panel, flows=flows, scenario=scenario, prose=prose))
    if args.announcements and not (args.digest or args.changes_only):
        from indiafacts.nsefeed import recent_for

        items, why = recent_for(fs.entity.ticker)
        print("\nRECENT EXCHANGE FILINGS (NSE public feed; the last day or two only)")
        print("\n".join(f"  {a.published:%d %b %Y %H:%M} | {a.subject} | {a.url}" for a in items) if items else f"  none: {why}")
    if args.json:
        import json as _json

        from indiafacts.digest import build_digest as _build_digest
        from indiafacts.stamp import report_stamp
        from indiafacts.summary import summarize_run

        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(_json.dumps(summarize_run(fs, scorecard, explanation, profile, changes, digest or _build_digest(fs, scorecard, profile, news=news, debate=debate, levels=levels, panel=panel), news=news, debate=debate, levels=levels, panel=panel, flows=flows, scenario=scenario, prose=prose, as_of=args.as_of, news_fetched=args.news,
                                                    stamp=report_stamp(fs.entity.ticker, args.as_of or fs.retrieved_at.date(),
                                                                       (scorecard or {}).get("members") or [], getattr(llm_client, "model", None))), default=str), encoding="utf-8")
    if args.html:
        from indiafacts.htmlreport import build_html

        page = build_html(fs, profile, is_default, args.view or profile.view, scorecard, args.as_of, explanation=explanation, digest=digest, changes=changes,
                          debate=debate, news=news, levels=levels, panel=panel, flows=flows, scenario=scenario, prose=prose)
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
        self.lock = threading.Lock()

    def history(self, symbol):
        with self.lock:
            hit = self.memo.get(symbol)
        if hit is None:
            hit = self.inner.history(symbol)
            with self.lock:
                self.memo.setdefault(symbol, hit)
        return hit


FULL_DATA_MIN = 8          # smallest comparison set worth ranking in


def _full_data_members(symbols: list[str], target: str, store: dict, policy: dict) -> tuple[list[str], bool]:
    """(members, narrowed). When too few sector members have our own comparison data for quality, growth and cash-flow measures
    to qualify (below the policy's min_coverage), rank inside the members that do, if there are at least FULL_DATA_MIN of them;
    otherwise keep the whole sector (scored on Market Lens measures only)."""
    have = set((store or {}).get("metrics") or {})
    full = [s for s in symbols if s + ".NS" in have or s == target]
    need = float((policy or {}).get("min_coverage", 0.6))
    if len(full) < len(symbols) and len(full) / max(len(symbols), 1) < need and len(full) >= FULL_DATA_MIN:
        return full, True
    return symbols, False


def _sector_scorecard(args, fs, profile) -> dict | None:
    """Rank the target inside its NSE Market Lens sector (sub-sector if the sector has fewer than 8) from the published comparison
    data: nothing is fetched per member. One source per metric for every member (data/source_policy.json). None means 'use the pool':
    Market Lens off or unavailable, the target not in it, or no comparison data published."""
    from indiafacts import marketlens, poolstore
    from indiafacts.peers import marketlens_peers
    from indiafacts.profile import weights_for
    from indiafacts.scoring import factsets_from_sources, load_source_policy

    if getattr(args, "no_marketlens", False) or not marketlens.enabled():
        return None
    try:
        rows, _ = marketlens.universe_with_reason()
        sym = fs.entity.ticker.split(".")[0]
        got = marketlens.sector_members(sym, rows) if rows else None
        store = poolstore.load()
        if got is None or store is None:
            return None
        symbols, kind, name = got
        policy = load_source_policy()
        total, symbols, narrowed = len(symbols), *_full_data_members(symbols, sym, store, policy)
        row, _origin, _why = marketlens.target_row(sym)
        if row is not None:
            rows = {**rows, sym: row}
        now, as_of = datetime.now(timezone.utc), args.as_of or date.today()
        cfg = load_score_config(strict=False)
        nifty = ((store.get("metrics") or {}).get(poolstore.NIFTY) or {}).get("return_1y") or poolstore.nifty_return_1y(fs)
        try:
            store_at = datetime.fromisoformat(store["meta"]["generated_at"])
        except (KeyError, ValueError, TypeError):
            store_at = None
        factsets, sources = factsets_from_sources(
            [s + ".NS" for s in symbols], fs, store, rows, policy, cfg, as_of, now,
            nifty_1y=(nifty or {}).get("value"), store_at=store_at)
    except Exception:
        return None
    results = score_universe(factsets, weights_for(profile), cfg, as_of, now)
    target = fs.entity.ticker
    try:
        peers = marketlens_peers(fs, rows)
    except Exception:
        peers = None
    group, comparisons = peers if peers is not None else (select_peers(fs, {target: fs}), [])
    label = f"NSE Market Lens {'sector' if kind == 'sector' else 'sub-sector'} '{name}' ({len(factsets)} companies)"
    if narrowed:
        label = (f"NSE Market Lens {'sector' if kind == 'sector' else 'sub-sector'} '{name}': the {len(factsets)} companies with full "
                 f"comparison data (of {total} in the sector)")
    return {"peers": group, "peer_comparisons": comparisons, "result": results.get(target), "n": len(factsets), "failed": {},
            "pool": label, "checklist": checklist(fs), "checklist_summary": summarize(checklist(fs)), "target_fs": fs,
            "members": sorted(factsets), "config_overdue": cfg.overdue, "default_pool": False, "pool_label": label,
            "comparison": "sector", "metric_sources": sources, "set_name": name, "set_kind": kind}


def _scorecard(args, fs, profile, client, sleep, price_client, tej_store=None) -> dict:
    from indiafacts.profile import weights_for

    uni = args.universe
    if not uni and not getattr(args, "sector_pool", False) and getattr(args, "comparison", "auto") == "auto":
        sector = _sector_scorecard(args, fs, profile)
        if sector is not None:
            return sector
    target = fs.entity.ticker
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
        if getattr(args, "sector_pool", False):
            if pool.kind != "nse_index_csv" and not args.labels:
                raise ValueError("--sector-pool needs an NSE index CSV (give it with --universe FILE or --labels FILE)")
            group = labels.get(target, {}).get("industry")
            if not group:
                raise ValueError(f"{target} is not in the index file, so its industry group is unknown")
            tickers = [t for t in tickers if labels.get(t, {}).get("industry") == group]
            label = f"NSE industry group '{group}' (from {(args.labels or path).name})"
    if getattr(args, "pool_size", None):
        tickers = [t for t in tickers if t != target][: args.pool_size]
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
                             prices=prices, price_client=memo, tej=not args.no_tej, tej_store=tej_store,
                             marketlens=not getattr(args, "no_marketlens", False), marketlens_live=False, nse_api=False)

    universe, failed = build_universe(tickers, builder, labels=labels, fresh={target: fs})
    cfg = load_score_config(strict=False)
    results = score_universe(universe, weights_for(profile), cfg, args.as_of or date.today(), datetime.now(timezone.utc))
    tgt = universe.get(target, fs)
    group = select_peers(tgt, universe)
    comparisons = compare_peers(tgt, group, universe) if group.picks else []
    if not getattr(args, "no_marketlens", False):
        from indiafacts import marketlens
        from indiafacts.peers import marketlens_peers

        try:
            ml_rows, _ = marketlens.universe_with_reason()
            got = marketlens_peers(tgt, ml_rows) if ml_rows else None
        except Exception:
            got = None
        if got is not None:
            group, comparisons = got
    return {"peers": group, "peer_comparisons": comparisons,
            "result": results.get(target), "n": len(universe), "failed": failed, "pool": label,
            "checklist": checklist(fs), "checklist_summary": summarize(checklist(fs)), "target_fs": tgt,
            "members": sorted(universe), "config_overdue": cfg.overdue, "default_pool": args.universe is None, "pool_label": label,
            "comparison": "pool", "metric_sources": None}


def _filing_paths(args) -> list[Path] | None:
    paths = list(args.filing or [])
    if args.filings_dir:
        if not args.filings_dir.is_dir():
            raise ValueError(f"filings folder not found: {args.filings_dir}")
        paths += sorted(p for p in args.filings_dir.iterdir() if p.suffix.lower() in (".html", ".htm", ".mhtml", ".mht", ".xml")
                        and not p.name.upper().startswith("SHP_"))
    return paths or None


def _shp_paths(args) -> list[Path] | None:
    """Shareholding files: the ones named with --shareholding plus any SHP_*.xml found in --filings-dir."""
    paths = list(args.shareholding or [])
    if args.filings_dir and args.filings_dir.is_dir():
        paths += sorted(p for p in args.filings_dir.iterdir() if p.name.upper().startswith("SHP_") and p.suffix.lower() == ".xml")
    return paths or None
