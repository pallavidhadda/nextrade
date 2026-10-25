# Backlog

Phase 1 (in progress): Gemini free-tier baseline on RELIANCE.NS. See `run_baseline.py`.

## Token optimisation
- Compact tool output: digests instead of raw OHLCV tables and full articles (`fetch_digest.py`).
- ~300-token structured analyst summaries passed downstream instead of full reports.
- Rolling-summary debate instead of resending full history.
- Merge the 3-way risk debate into one structured call.
- Cap `max_tool_rounds` (already 4 in `.env`); lower news article limits.
- Prompt caching (shared report prefix first) when on Anthropic models.
- Optional Jev (TypeSafe) pre-filter for news/social classification.

## Claude plugin
- `.claude-plugin/plugin.json`, `/analyze TICKER` command.
- Subagents: analyst, debate, risk, portfolio (Haiku/Sonnet; Opus for final call).
- `scripts/fetch_digest.py` reusing `tradingagents/dataflows/`.
- Memory log as a file; compare against Phase 1 baseline.

## Data (do alongside plugin work)
- **World Bank macro vendor** (keyless; India priority, any country): add next to the FRED vendor in `tradingagents/dataflows/router.py`; FRED stays optional/US-only.
- Verify Indian fundamentals from Yahoo (SEC EDGAR is US-only).

## Environment notes
- macOS 12 / x86_64: `cryptography` has no source-buildable path without Rust; install with `uv pip install --only-binary cryptography .`
- Python 3.12 venv at `TradingAgents/.venv` (via uv).

## Findings from RELIANCE.NS baseline (2026-10-23)
- **P0: Indian fundamentals are blind.** Point-in-time guard withheld all Yahoo statements; analyst wrote generic filler. Need a dated source (Screener.in-style exports, NSE/BSE filings, or results-date-stamped data).
- Evidence enforcement: every claim in final report must cite a fetched number; "no data" must be explicit, not filler.
- Price target / stop must come from valuation + ATR/risk budget, not SMA/Bollinger levels.
- Use `--portfolio` so sizing is real; add relative strength vs Nifty 50 and sector peers.
- Replace 3-way risk debate with one structured risk check; run the repo's backtest over many dates before trusting signals.
- Per-agent token labels in `run_baseline.py`; then a true 4-analyst baseline.

## Product ideas from competitor research (see COMPETITIVE_BRIEF.md)
- Cited answers linking each figure to its source filing (Perplexity Finance / Fiscal.ai pattern).
- Deterministic stock score with explainable factors alongside the LLM view (Danelfin, Trendlyne DVM pattern).
- Screening + alerts layer for India (Screener.in / Trendlyne pattern) feeding the agents a shortlist.
- Investor-persona lenses (ai-hedge-fund pattern) as cheap single-call prompts, not full debates.
- Beginner mode: plain-English explanation + "what would change my mind" triggers.
- Compliance: personal research tool only; SEBI rules apply if recommendations go to others (verify).

## FUTURE TARGET (product vision, set 2026-10-25)
A public portfolio project: open git repo + front end that anyone can try, for **research and education only, not financial, investment or trading advice** (disclaimer on every screen and every exported report).
**Hard constraint: minimum LLM tokens.** Must be runnable on a free LLM API tier (e.g. Gemini free, 15 req/min) and as a Claude Code plugin. India-first (NSE/BSE), world data second.
Design rules (from reading ai-hedge-fund, FinRobot, TradingAgents, OpenBB source; details in RESEARCH_NOTES.md):
1. Numbers are code, narrative is LLM. All ratios, scores, valuation, sizing, stops come from deterministic Python; the LLM only explains.
2. One short LLM call per lens, strict JSON out (signal, confidence, 2-4 sentence reason). No free-form multi-round debates.
3. Cache every LLM call by hash(agent, model, prompt); reruns and backtests cost zero.
4. Deterministic funnel: code screens the universe down to a few names; LLM sees only the shortlist.
5. Risk limits are hard-coded clamps the LLM cannot override; every clamp is logged.
6. Evidence ledger: each number carries source + date; audit checks block or caveat bad numbers; missing data is stated, never filled.
7. Scorecard: log every call and grade it later (hit rate vs benchmark, rank IC) so users see if the tool has any skill.
8. Lazy tool exposure: small tool list with search/discovery (OpenBB MCP pattern) to avoid tool-schema token bloat.
9. Provider failover + cross-source checks on key figures (FinRobot validator pattern).
Proposed token budgets (to validate against our measured 39k-token / 13-call baseline for 2 analysts): quick screen <= 3k tokens per ticker; full analysis <= 15k; all LLM calls cacheable.

## M0 spike result (2026-10-25): free NSE/BSE scrapers
- dalal 0.2.1 (read source first; its fundamentals() calls api.bseindia.com TabResults_PAR): BSE returned HTTP 403 Access Denied (bot protection); lookup() returned 404. Not worked around on purpose.
- nsepython 2.101: not run. It drives NSE's website APIs by imitating a browser session; NSE terms page was unreachable (fetch timed out), so permission is unknown.
- Decision: Yahoo + deadline-estimate stays Tier 1. Do not build on unofficial exchange scrapers. Revisit: official XBRL files downloaded by the user, a documented exchange feed if one exists, or a licensed source later.

## XBRL question (2026-10-25)
- Exists and is public in principle (NSE/BSE mandate XBRL results; NSE says filings are downloadable in XBRL for investors). No documented API or bulk download found; file links sit behind the Integrated Filing - Financials page; nsearchives.nseindia.com/corporate/ file names look like SYMBOL_DDMMYYYYHHMMSS_suffix (observed, undocumented). BSE API returned 403 to a script.
- Plan: (1) draft email to nsexbrl@nse.co.in asking for a supported programmatic/bulk method and terms; (2) build "import XBRL file" (user downloads, app parses: gives period, units, scale, consolidated/standalone, and submission date) as Tier 2 in the fact model; (3) automate only if NSE confirms it is permitted.

## NSE Market Data MCP (official, prices only) — 2026-10-25
- Page: nseindia.com/nse-mcp (could not open directly; details from search + a third-party tutorial). Servers: nse-bhavcopy (5y EOD), cm-market (1-3 min delayed). 15+ price/breadth tools, no fundamentals. Disclaimer: educational, not commercial deployment (confirm wording before public launch).
- Use as official price source with provenance. Token rule: call it from code (Python MCP client or HTTP), compute indicators in code, pass the LLM a digest. Do not let raw OHLCV tool output flow into the model context. Measure tool-list size and a typical response before adopting inside the Claude plugin.
- Next: user downloads one Reliance XBRL results file by hand; parse it to prove the fact-model import.

## Findings from the official NSE Q1 FY27 filing (RELIANCE, consolidated, unaudited; board meeting 17-07-2026)
- Verified: filing net profit to owners (Rs 20,946 cr), finance costs (Rs 8,337 cr), diluted EPS (15.48) equal Yahoo exactly. Revenue: filing Rs 3.12 lakh cr (its own note: Rs 311,850 cr) vs Yahoo Rs 3.09 lakh cr, 0.8% apart (cause unknown).
- Yahoo's "EBITDA" for this quarter (Rs 38,967 cr) equals profit before tax + finance costs (30,630 + 8,337), i.e. EBIT with no depreciation add-back (filing depreciation Rs 15,100 cr). One company-quarter only; do not use Yahoo EBITDA for Indian names without a check. TODO: compute EBITDA from filing lines and flag the mismatch.
- Real filing date 17 Jul 2026 vs the 45-day deadline estimate (14 Aug): the estimate is conservative by ~4 weeks here.
- Filing gives ISIN, BSE scrip code, consolidated flag, audit status, segment revenue/result, company-reported D/E 0.40, DSCR 3.12, ICR 4.67.
- Sample file had no ix: tags: parsing is label-based and fragile. Ask whether the raw iXBRL (View Source) is obtainable.
- TODO: only the 3-month column is read; YTD, prior-year columns and balance sheet/cash flow pages not parsed yet. Mixed-source YoY (filing vs Yahoo) is unlabeled.

## Price history + investor profile + peer comparison (2026-10-25)
- Verified: Yahoo gives RELIANCE.NS daily OHLCV from 1996-01-01 (7,730 rows to 2026-10-23) with dividends and split events. `Close` is already split-adjusted (the 28-Oct-2024 bonus appears as a 2.0 split with no price jump); `Adj Close` also adjusts dividends; 117 zero-volume days. Price-history Facts must carry adjustment basis; raw OHLCV never goes to an LLM.
- Holding period is the USER's input (profile: goal, horizon bucket, risk tolerance AND capacity, concentration limit, liquidity need), not an agent's guess. The PM agent chooses factor weights and evaluation horizon from the profile; it may suggest a default for beginners, shown and editable. Backtest/scorecard horizon must follow the profile (upstream default holding_period_days=5 does not fit long-term).
- Two views, one engine: Simple (long-term default, fundamentals-led, 1/3/5y return vs Nifty 50, max drawdown, 52-week position, checklist) and Pro (momentum, volatility, beta, rolling returns, valuation vs own history, editable weights).
- Peer comparison design: deterministic tiered peer group (industry, then sector, size-proximity), matched multiples (EV with EBITDA, equity with earnings; P/B for banks), median not mean, own-history percentile, ROIC vs cost of capital, benchmark-relative returns. Conglomerates (Reliance): sum-of-the-parts using filing segments.
- Compliance: SEBI requires registered advisers to risk-profile clients before advice. A profile that drives recommendations may look like advice: keep outputs framed as research fit ("matches/doesn't match a long-term profile on these facts"), not buy/sell; verify with a lawyer before a public launch.

## Staleness controls (2026-10-26)
Data-age banner on every report; review_by dates on all assumptions (test fails when overdue); canary fixtures per source; scheduled live checks; scorecard watches for fading accuracy; cache AI text by input hash; record upstream versions and licences studied.

## Security master (2026-10-26)
Needed: deterministic symbol/rename/demerger knowledge (ZOMATO->ETERNAL rename; TATAMOTORS -> TMPV + TMCV demerger). See docs/2026-10-25-price-history-and-profile-spec.md section A0. Ask user for the list of changes they know; verify dates/ISINs against NSE/BSE circulars.
