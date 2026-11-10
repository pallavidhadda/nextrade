from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from indiafacts.analysis import add_gaps, check_ebitda, cross_check, growth_yoy, margin_latest, prefer_sources, reconcile_price, ttm
from indiafacts.availability import filter_as_of
from indiafacts.models import AvailabilityKind, Basis, Entity, Fact, FactSet, Identifier, PeriodType, Status
from indiafacts.nsefiling import facts_from_nse_filing, merge_filings
from indiafacts.xbrl import facts_from_nse_xbrl
from indiafacts.pricemetrics import price_metrics
from indiafacts.prices import YfinancePriceClient, chart_data, load_series
from indiafacts.tej import TejStore, TejUnavailable, isin_for, price_affecting_dates, symbol_changes_from_history
from indiafacts.securitymaster import Resolution, corporate_action_dates, load_curated, load_symbol_changes, normalize_symbol, resolve_symbol
from indiafacts.yahoo import fetch_facts

FLOW_METRICS = ("net_income", "ebitda", "interest_expense", "eps_diluted")


def default_symbol_changes() -> Path:
    return Path.home() / ".indiafacts" / "symbolchange.csv"


class AmbiguousSymbol(ValueError):
    """The symbol maps to several successor companies; the user must choose."""

    def __init__(self, resolution: Resolution):
        super().__init__(resolution.notice)
        self.resolution = resolution


def _merge_entity(entity: Entity, filing: Entity) -> Entity:
    return entity.model_copy(update={
        "nse_symbol": filing.nse_symbol, "bse_code": filing.bse_code, "isin": filing.isin,
        "name": filing.name, "resolution": "resolved", "resolution_reason": "",
    })


def build_factset(ticker: str, as_of: date | None = None, client=None, sleep=time.sleep,
                  filing_path: Path | list[Path] | None = None, symbol_changes: Path | None = None,
                  prices: bool = False, price_client=None, benchmark: str = "^NSEI",
                  tej: bool = False, tej_store: TejStore | None = None, skip_other_filings: bool = False,
                  shareholding_paths: list[Path] | None = None, shareholding_feed: bool = False,
                  marketlens: bool = True, marketlens_rows: dict | None = None) -> FactSet:
    """Resolve identity, fetch, flag gaps, optionally merge an official NSE filing, then append computed facts."""
    notices: list[str] = []
    store = (tej_store or TejStore()) if tej else None
    ticker, loaded, tej_hist = _resolve_identity(ticker, symbol_changes, notices, store)
    paths = [] if not filing_path else (list(filing_path) if isinstance(filing_path, (list, tuple)) else [filing_path])
    entity = Entity.from_ticker(ticker)
    parsed = []
    for p in paths:
        try:
            pf = facts_from_nse_xbrl(p) if Path(p).suffix.lower() == ".xml" else facts_from_nse_filing(p)
        except ValueError as exc:
            if not skip_other_filings:
                raise
            notices.append(f"skipped filing {Path(p).name}: {exc}")
            continue
        if entity.ticker.split(".")[0] != pf.entity.nse_symbol.value:
            if skip_other_filings:
                notices.append(f"skipped filing {Path(p).name}: it is for {pf.entity.nse_symbol.value}, not {entity.ticker}")
                continue
            raise ValueError(f"filing is for {pf.entity.nse_symbol.value}, not {entity.ticker}")
        parsed.append(pf)
    filing = None
    if parsed:
        filing, merge_notes = merge_filings(parsed)
        notices.extend(merge_notes)
    filing_dates = {f.period_end: f.available_from for f in filing.facts
                    if f.source == "nse_filing" and f.availability_kind == AvailabilityKind.filed and f.available_from} if filing else None

    fs = add_gaps(fetch_facts(ticker, as_of=as_of, client=client, sleep=sleep, filing_dates=filing_dates))
    if fs.entity.resolution != "resolved":
        reason = ("no data at Yahoo and not in security master; not found at Yahoo under this symbol" if loaded
                  else "no data at Yahoo; symbol-change list not loaded, so a rename cannot be ruled out")
        if fs.entity.resolution_reason:
            reason += f" [{fs.entity.resolution_reason}]"                       # keep the vendor's own error for the server log
        fs = fs.model_copy(update={"entity": fs.entity.unresolved(reason)})
    if fs.entity.resolution != "resolved" and not filing:
        return fs.model_copy(update={"notices": notices})

    facts, pending = list(fs.facts), list(fs.not_yet_public)
    if filing:
        public, later = (filter_as_of(filing.facts, as_of) if as_of else (filing.facts, []))
        facts += public
        pending += later
        fs = fs.model_copy(update={"entity": _merge_entity(fs.entity, filing.entity), "filings": filing.filings})
    if tej_hist is not None and fs.entity.resolution == "resolved" and fs.entity.isin.value is None:
        isin = isin_for(tej_hist, normalize_symbol(fs.entity.ticker), as_of)
        if isin:
            fs = fs.model_copy(update={"entity": fs.entity.model_copy(update={"isin": Identifier(value=isin, status=Status.ok)})})

    extra = []
    if filing:
        new, demote = check_ebitda([f for f in facts if f.source == "nse_filing"],
                                   [f for f in facts if f.source == "yahoo"])
        facts = [demote.get(f.fact_id, f) for f in facts]
        extra += new
    primary = prefer_sources(facts)
    for metric in FLOW_METRICS:
        ok_q = [f for f in primary if f.metric == metric and f.period_type == PeriodType.Q and f.status == Status.ok]
        if not ok_q:
            continue
        latest = max(f.period_end for f in ok_q)
        extra.append(ttm(primary, metric, latest))
        if metric == "net_income":
            extra.append(growth_yoy(primary, metric, latest))
    rev_ok = [f for f in primary if f.metric == "revenue" and f.period_type == PeriodType.Q and f.status == Status.ok]
    if rev_ok:
        extra.append(growth_yoy(primary, "revenue", max(f.period_end for f in rev_ok)))
    margin = margin_latest(primary, "net_income", "revenue", "net_margin_q")
    if margin is not None:
        extra.append(margin)
    elif any(f.metric == "net_income" and f.status == Status.ok for f in primary):
        ref = next(f for f in primary if f.metric == "net_income" and f.status == Status.ok)
        extra.append(Fact.make(entity_key=ref.entity_key, metric="net_margin_q", value=None, unit="ratio",
                               period_end=ref.period_end, period_type=PeriodType.Q, source="computed",
                               retrieved_at=ref.retrieved_at, status=Status.unavailable,
                               reason="revenue unavailable for the same quarter"))
    pt = {f.metric: f for f in facts if f.period_type == PeriodType.point}
    if all(k in pt for k in ("price", "pe_ttm", "eps_ttm")):
        extra.append(reconcile_price(pt["price"], pt["pe_ttm"], pt["eps_ttm"]))
    if filing:
        yahoo = {(f.metric, f.period_end): f for f in facts
                 if f.source == "yahoo" and f.period_type == PeriodType.Q and f.status == Status.ok}
        for f in facts:
            y = yahoo.get((f.metric, f.period_end))
            if f.source == "nse_filing" and y is not None and y.unit == f.unit:
                extra.append(cross_check(f, y))
    price_facts, price_notes, charts = _price_facts(fs.entity.ticker, as_of, prices, price_client, benchmark, notices,
                                            _tej_action_dates(store, tej_hist, fs.entity.ticker, as_of, prices, notices))
    from indiafacts.valuation import valuation_facts

    lc = next((f for f in price_facts if f.metric == "last_close" and f.status == Status.ok), None)
    if lc is not None and not any(f.metric == "price" and f.status == Status.ok for f in facts):
        extra.append(Fact.make(entity_key=lc.entity_key, metric="price", value=lc.value, unit="INR", period_end=lc.period_end,
                               period_type=PeriodType.point, source="computed:chart", source_field="last close from the price history",
                               retrieved_at=lc.retrieved_at, status=Status.ok, related_fact_ids=[lc.fact_id]))
        notices.append("Yahoo's company overview returned no price, so the price is the last close from the price history; "
                       "ratios that need the overview (P/E, P/B, ROE, market value) may be unavailable")
    base_facts = facts + extra + price_facts
    base_facts += _fundamental_facts(fs, base_facts, client, notices)
    base_facts += _ownership_facts(fs, shareholding_paths or [], shareholding_feed, notices)
    from indiafacts.selfvalue import self_valuation_facts

    base_facts += self_valuation_facts(base_facts)
    if marketlens:
        base_facts += _marketlens_facts(fs, base_facts, marketlens_rows, notices)
    val_facts = valuation_facts(fs.model_copy(update={"facts": base_facts}), today=as_of or fs.retrieved_at.date(), now=fs.retrieved_at)
    return fs.model_copy(update={"facts": base_facts + val_facts, "not_yet_public": pending,
                                 "notices": notices, "price_notes": price_notes,
                                 "charts": ({"price": charts} if charts else {})})


def _tej_action_dates(store, hist, ticker: str, as_of: date | None, enabled: bool, notices: list[str]) -> list[date]:
    if store is None or hist is None or not enabled:
        return []
    import pandas as pd

    end = (as_of or date.today()).year
    frames = []
    for y in range(end - 6, end + 1):
        try:
            frames.append(store.load(f"actions/nse_{y}.parquet"))
        except TejUnavailable:
            continue
    if not frames:
        notices.append("TejHQ data unavailable: corporate actions not loaded, so mergers/demergers are not flagged")
        return []
    return price_affecting_dates(pd.concat(frames), hist, normalize_symbol(ticker))


def _resolve_identity(ticker: str, symbol_changes: Path | None, notices: list[str], store=None):
    default = default_symbol_changes()
    path = symbol_changes or (default if default.exists() else None)
    changes = load_symbol_changes(path) if path else None
    tej_hist = None
    if store is not None:
        try:
            tej_hist = store.load("symbol_history/nse.parquet")
        except TejUnavailable as exc:
            notices.append(f"TejHQ data unavailable: {exc}")
        if changes is None and tej_hist is not None:
            changes = symbol_changes_from_history(tej_hist)
            changes.source = "TejHQ symbol history"
    curated = load_curated(strict=False)
    if curated.overdue:
        notices.append("security master review overdue: " + ", ".join(curated.overdue))
    res = resolve_symbol(ticker, changes, curated)
    if res.kind == "split":
        raise AmbiguousSymbol(res)
    suffix = ticker.strip().upper()[len(normalize_symbol(ticker)):] or ".NS"
    if res.kind == "renamed":
        notices.append(res.notice)
        return res.symbols[0] + suffix, changes is not None, tej_hist
    if changes is None and store is None:
        notices.append(res.notice)
    return ticker, changes is not None, tej_hist


def _price_facts(ticker: str, as_of: date | None, enabled: bool, client, benchmark: str, notices: list[str],
                 extra_action_dates=()):
    if not enabled:
        return [], [], {}
    client = client or YfinancePriceClient()
    try:
        series = load_series(ticker, client, as_of=as_of)
    except Exception as exc:  # network/vendor errors must not kill the fundamentals report
        notices.append(f"price history unavailable: {type(exc).__name__}")
        return [], [], {}
    try:
        bench = load_series(benchmark, client, as_of=as_of)
    except Exception as exc:
        bench = None
        notices.append(f"benchmark {benchmark} unavailable: {type(exc).__name__}")
    q = series.quality
    note = (f"{len(series.dates)} daily bars {series.dates[0]} to {series.dates[-1]}; source Yahoo; basis split-adjusted close "
            f"(levels adjusted to today's share count); benchmark {benchmark} Nifty 50 price index, dividends excluded"
            if series.dates else "no price bars returned")
    notes = [note, f"quality: {q.zero_volume_days} zero-volume days, {len(q.gaps)} gaps, {q.dropped_rows} dropped rows, "
                   f"{q.duplicate_conflicts} duplicate conflicts"
                   + (f", last bar {q.stale_days} weekdays old" if q.stale_days else "")]
    notes += [f"event: {e}" for e in q.events]
    actions = sorted(set(corporate_action_dates(ticker, load_curated(strict=False))) | set(extra_action_dates))
    from indiafacts.indicators import indicator_facts

    return (price_metrics(series, bench, as_of or date.today(), corporate_actions=actions) + indicator_facts(series), notes,
            chart_data(series, bench))


def _fundamental_facts(fs, facts, client, notices: list[str]):
    """Annual statements, ownership proxies and the ratios built from them. Never raises: a failure becomes a notice."""
    from indiafacts.fundamentals import annual_facts, holding_facts, ratio_facts
    from indiafacts.yahoo import YfinanceClient

    ann = client if client is not None and hasattr(client, "annual") else (YfinanceClient(fs.entity.ticker) if client is None else None)
    if ann is None:
        return []
    try:
        statements = ann.annual()
        info = client.info() if client is not None and hasattr(client, "info") else ann.info()
    except Exception as exc:                                    # network or vendor failure must not sink the report
        notices.append(f"annual statements could not be fetched ({type(exc).__name__}); year figures, free cash flow and EV/EBITDA are unavailable")
        return []
    new = annual_facts(fs.entity.ticker, statements, fs.entity.sector, fs.entity.industry, now=fs.retrieved_at)
    new += holding_facts(fs.entity.ticker, info or {}, now=fs.retrieved_at)
    probe = fs.model_copy(update={"facts": list(facts) + new})
    checks = []
    yfy = {(f.metric, f.period_end): f for f in new if f.status == Status.ok and f.period_type == PeriodType.FY}
    for f in facts:                                              # official year figure against Yahoo's, consolidated only
        if f.source in ("nse_filing", "nse_xbrl") and f.period_type == PeriodType.FY and f.value is not None and f.basis == Basis.consolidated:
            y = yfy.get((f"fy_{f.metric}", f.period_end))
            if y is not None and y.unit == f.unit:
                checks.append(cross_check(f, y))
    return new + ratio_facts(probe, now=fs.retrieved_at) + checks


def _ownership_facts(fs, paths: list[Path], feed: bool, notices: list[str]):
    """Official shareholding pattern: saved files, the exchange's latest feed, and the snapshots stored on earlier runs."""
    from indiafacts.shareholding import fetch_latest, history, parse_shp, save_snapshot, shareholding_facts

    sym = fs.entity.ticker.split(".")[0]
    for p in paths:
        try:
            sh = parse_shp(Path(p), source=Path(p).name)
        except (ValueError, OSError) as exc:
            notices.append(f"shareholding file {Path(p).name} was not used: {exc}")
            continue
        if sh.symbol and sh.symbol != sym:
            notices.append(f"shareholding file {Path(p).name} is for {sh.symbol}, not {sym}; skipped")
            continue
        sh.symbol = sh.symbol or sym
        save_snapshot(sh)
    if feed:
        sh, note = fetch_latest(sym, fs.entity.name)
        if sh is not None:
            sh.symbol = sh.symbol or sym
            save_snapshot(sh)
    snaps = history(sym)
    if not snaps:
        return []
    return shareholding_facts(fs.entity.ticker, snaps, now=fs.retrieved_at)


ML_CHECKED = ("market_cap", "pe_ttm", "pb", "debt_to_equity", "sh_promoter")


def _marketlens_facts(fs, facts, rows: dict | None, notices: list[str]):
    """NSE Market Lens figures for the target when it is in the universe, plus checks against the other sources. Never raises."""
    from indiafacts import marketlens

    try:
        if rows is None:
            if not marketlens.enabled():
                return []
            rows, why = marketlens.universe_with_reason()
            if not rows:
                notices.append(f"NSE Market Lens not used: {why}")
                return []
        sym = fs.entity.ticker.split(".")[0]
        row = rows.get(sym)
        if row is None:
            return []
        new = marketlens.facts_for(sym, row, now=fs.retrieved_at)
    except Exception as exc:
        notices.append(f"NSE Market Lens not used ({type(exc).__name__})")
        return []
    have_ok = {f.metric for f in facts if f.status == Status.ok and f.value is not None}
    keep = []
    for f in new:
        if f.metric in ("sh_promoter", "sh_public") and f.metric in have_ok:
            continue              # an official shareholding file with its own quarter-end date stays the reference
        if f.metric in ("high_52w", "low_52w") and f.metric in have_ok:
            continue
        keep.append(f)
    checks = []
    for f in new:
        if f.metric not in ML_CHECKED or f.status != Status.ok:
            continue
        others = [g for g in facts if g.metric == f.metric and g.status == Status.ok and g.value is not None and g.unit == f.unit
                  and g.period_type == PeriodType.point and g.source != marketlens.SOURCE]
        if not others:
            continue
        best = min(others, key=lambda g: (analysis_rank(g), -g.period_end.toordinal()))
        checks.append(cross_check(f, best))
        rest = [g for g in others if g.source not in (best.source,) and g.source in ("yahoo", "computed:selfvalue")]
        for g in rest:
            c = cross_check(f, g)
            m = f"{f.metric}_source_check_{g.source.split(':')[-1]}"
            checks.append(c.with_(metric=m, fact_id=Fact.compute_id(c.entity_key, m, c.period_end, str(c.period_type), c.source)))
    return keep + checks


def analysis_rank(f):
    from indiafacts.analysis import SOURCE_RANK

    return SOURCE_RANK.index(f.source) if f.source in SOURCE_RANK else len(SOURCE_RANK)
