# Identity, Price History and Profile Implementation Plan

> **For agentic workers:** Execute inline with superpowers:executing-plans; TDD on every task (failing test first, watch it fail, minimal code, full suite green, commit).

**Goal:** Add a security master (renames/demergers), price-history metrics, and a local investor profile to `indiafacts`.

**Architecture:** New pure modules (`securitymaster`, `prices`, `pricemetrics`, `profile`) feed the existing `build_factset` pipeline; results stay typed Facts and render through the fact-only renderer. No LLM calls.

**Tech Stack:** Python 3.12, pydantic v2, pandas, yfinance (existing venv `.venv`), pytest. JSON for data files (no new dependency).

**Specs:** `docs/2026-10-25-price-history-and-profile-spec.md` (A0, A, B, tests SM/P/PR). Parent plan: `docs/superpowers/plans/2026-10-25-fact-model.md`.

## Global Constraints
- Research/education only; disclaimer on every rendered output; fit wording, never buy/sell.
- Real NSE files (`samples/`) are never committed; offline tests use synthetic CSV/series.
- Every assumption/config entry carries `reviewed_on` and `review_by`; a test fails once `review_by` is past.
- No look-ahead: price series truncated to `as_of`. Windows: N years = N x 365 calendar days back to the nearest earlier trading day.
- Prices are Yahoo split-adjusted Close; returns are price returns (dividends excluded) on both stock and ^NSEI; always labelled.
- Raw price rows never reach an LLM; no secrets in outputs.
- Symbol-change CSV columns: `NAME OF THE COMPANY,OLD SYMBOL,NEW SYMBOL,EFFECTIVE DATE` (date format `DD-MON-YYYY`).

## Review Focus
- Old symbol reused by a different company later (retired rule: a symbol is retired only if its latest event is as OLD) — T1.
- Rename chains (A->B->C) and cycles (A->B->A) — T1.
- Empty/one-row price history, missing benchmark, tz-aware Yahoo index (Asia/Kolkata) — T3/T4.
- Window start on a weekend/holiday; history shorter than window — T4.
- Missing/corrupt profile file, unknown enum, weights not summing to 1 — T6.

## Files
`indiafacts/securitymaster.py`, `indiafacts/data/security_master.json` (curated), `indiafacts/prices.py`, `indiafacts/pricemetrics.py`, `indiafacts/profile.py`, `indiafacts/data/weight_presets.json`; modify `models.py` (FactSet.notices), `pipeline.py`, `cli.py`, `render.py`. Tests: `tests/test_securitymaster.py`, `test_prices.py`, `test_pricemetrics.py`, `test_profile.py`, plus integration cases in `test_pipeline.py`.

---
### T1: Security master core
**Interfaces — Produces:** `load_symbol_changes(path: Path) -> list[SymbolChange]` (name, old, new, effective: date); `load_curated(path: Path | None = None, today: date | None = None) -> list[CuratedChange]` (raises ValueError if `source_urls` empty or `review_by < today`); `resolve_symbol(raw: str, changes, curated) -> Resolution` with `kind` in {direct, renamed, split, unknown}, `symbols: list[str]`, `chain: list[SymbolChange]`, `notice: str`.
**Tests:** SM1 rename redirects (ZOMATO->ETERNAL, notice contains date 2025-04-09); chain TELCO->TATAMOTORS->TMPV resolves to TMPV; SM2 curated demerger TATAMOTORS returns kind split with [TMPV, TMCV] and never picks; SM3 unknown symbol notice "not in security master"; SM7 lower case/spaces/.NS suffix handled; SM8 cycle rejected at load; reuse case (X retired 2010, X new again 2018 -> direct); SM5 curated entry without source or overdue review fails validation; unparseable date row skipped and counted, blank-name rows kept.
- [ ] Write failing tests; run (FAIL); implement; run (PASS); commit.

### T2: Wire identity into pipeline/CLI/render
**Interfaces — Consumes:** T1. **Produces:** `FactSet.notices: list[str]`; `build_factset(..., symbol_changes: Path | None)`; CLI `--symbol-changes PATH` (default `~/.indiafacts/symbolchange.csv`); exit code 3 with successor list for `split`.
**Tests:** renamed input fetches the new symbol and prints a NOTICES line; split exits 3 and prints both successors, makes no vendor call; unknown without CSV prints "symbol-change list not loaded"; direct symbol unchanged (regression).
- [ ] Failing tests; implement; full suite; commit.

### T3: PriceSeries and quality checks
**Produces:** `PriceSeries` (symbol, dates list[date], close list[float], volume list[float], events list[Event], source, basis="split_adjusted_close", retrieved_at, quality: QualityReport); `PriceClient` protocol `history(symbol) -> DataFrame`; `load_series(symbol, client, as_of=None) -> PriceSeries`; `QualityReport` (zero_volume_days, gaps list[(start,end)], dropped_rows, duplicate_conflicts, stale_days, events).
**Tests:** P11 NaN/zero/negative rows dropped, counted; duplicate dates deduped, conflicting duplicates flagged; P12 10-weekday hole flagged, 3-day weekend not; P13 stale last bar flagged (> 3 trading days before as_of); P10 as-of truncation ignores a later spike; tz-aware index converted to dates; P2 split event listed, closes untouched; empty/one-row history gives series with `usable=False`.
- [ ] Failing tests; implement; commit.

### T4: Price metrics
**Produces:** `price_metrics(series, benchmark, as_of, security_events=()) -> list[Fact]` with metrics `return_{1,3,5}y`, `benchmark_return_{1,3,5}y`, `relative_return_{N}y`, `max_drawdown_{N}y`, `high_52w`, `low_52w`, `pct_from_52w_high`, `volatility_1y`, `beta_{1,3}y`; unavailable Facts with reasons.
**Tests:** P1 hand-computed returns; P3 window start on holiday uses earlier trading day; P4 short history -> unavailable "history shorter than N years"; P5 drawdown known series and monotonic rising = 0; P6 52w uses last 365 days only; P7 constant series vol 0, alternating series to 4 dp; P8 beta of 2x-returns series = 2.0, constant -> unavailable; P9 only common dates, no overlap -> unavailable; missing benchmark -> relative/beta unavailable, rest computed; demerger/merger inside window -> status `unverified` "spans corporate action".
- [ ] Failing tests; implement; commit.

### T5: Integrate prices into pipeline/render
**Produces:** `build_factset(..., prices: bool = True, price_client=None, benchmark="^NSEI")`; render section PRICE HISTORY (returns, relative vs Nifty 50 price index, drawdown, 52w, vol, beta, quality line, caveat that levels are split-adjusted to today); CLI `--no-prices`.
**Tests:** P14 every price Fact has source_field with series id, window, basis; disclaimer present; offline acceptance with fake client; `@live` P15 RELIANCE.NS rows > 5000 and ^NSEI rows > 4000.
- [ ] Failing tests; implement; run live once; commit.

### T6: Investor profile
**Produces:** `InvestorProfile` (goal, horizon in {"<1y","1-3y","3-5y","5y+"}, risk_tolerance, risk_capacity, max_single_stock_pct 1-100, liquidity_need, experience); `.effective_risk` (min of tolerance, capacity); `.profile_hash`; `default_profile()`; `load_profile(path)`/`save_profile(profile, path)` (default `~/.indiafacts/profile.json`); `weights_for(profile) -> dict[str, float]` from `data/weight_presets.json` (validated to sum 1.0, with reviewed_on/review_by); `eval_horizon_days(profile)` = {63, 504, 1008, 1260}.
**Tests:** PR1 min-of-two for 9 combos; PR2 invalid enum/percent rejected; PR3 presets sum to 1.0, bad file rejected; PR4 horizon->days; PR5 hash changes with any field; PR6 beginner->simple view, expert->pro, override flag; PR7 no profile -> labelled default + notice; PR8 rendered fit text has no buy/sell instruction words and has disclaimer; PR9 different horizons give different weights, identical facts; corrupt JSON gives clear error not a crash.
- [ ] Failing tests; implement; render profile line + hash; CLI `--profile PATH`, `--horizon/--risk-tolerance/--risk-capacity/--experience` to create+save; commit.

## Self-review
Coverage: SM1-SM8 (T1-T2), P1-P15 (T3-T5), PR1-PR9 (T6). Staleness: review_by on curated table and presets (T1, T6), data-age/stale-bar flags (T3). Scoring (D) and peers (C) are separate plans.
