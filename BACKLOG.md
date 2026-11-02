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
- Security master data sources found 2026-10-26: NSE "Changes in Symbols (.csv)" + EQUITY_L.csv (ISIN master) on NSE "Securities available for Trading" page; per-change NSE circulars. Needs user to download both CSVs into samples/ (scripted fetch blocked). Seeds: ZOMATO->ETERNAL (rename, ticker change 2025-04-09), TATAMOTORS->TMPV+TMCV (demerger, effective 2025-10-01, CV listed 2025-11-12). Details in the price-history/profile spec section A0.

## Provider leads pasted by user 2026-10-26 (UNVERIFIED: web search found nothing on these by name)
NPCI/RBI/data.gov.in (macro, free datasets), TigZig (macro/credit/red flags), TejHQ (prices/screening, Rs 599/mo retail), Stoxim (financials/governance/shareholding, Rs 2,999/mo), DalalOS (MCP; Pro Rs 399/mo), IndianAPI.in (free 500 requests/month). Search did find BharatStock (free: 25 requests/day, 1-year history, full endpoint set per its site) and TrueData (sandbox request). Verify coverage, terms and public-use rights one by one before depending on any.
## Visuals gap (2026-10-26)
Report is text/tables only. Add charts (price vs Nifty 50 line, drawdown, quarterly bars, score bars) in an HTML report; terminal gets sparklines. Use the dataviz skill; no invented numbers.

## Source tiers pasted by user 2026-10-26 (leads, UNVERIFIED; check terms and public-use rights before use)
Tier 1 free primary: NSE/BSE announcements, results, shareholding, corporate actions (already our direction); RBI DBIE (banking/credit/macro: candidate replacement for FRED/World Bank for India macro); NPCI UPI stats; data.gov.in.
Tier 2 free structured APIs: TigZig (claims unauthenticated, CC0), TejHQ, Stoxim. Not found by web search; verify coverage, limits, licence.
Tier 3 digital-demand signals (Google Trends, Play Store, careers pages): own time series from repeated observations; no reliable historical DAU/MAU; low priority; check scraping/ToS.

## Visual HTML report (promoted to roadmap item 5b, 2026-10-26)
Single self-contained HTML (no server): price vs Nifty 50 line with drawdown shading; quarterly profit/revenue bars with missing quarters shown as gaps; factor score bars with coverage; checklist strip; segment revenue/result bars; peer dot plot. Light/dark safe colours (dataviz skill). Every plotted number is an existing Fact; data-age banner; disclaimer. Terminal: text sparklines. After peers (5).
## Peer group needs a bigger pool
A 30-name pool gives few true peers (Reliance sits in Energy with ONGC and Coal India only). Ask user to download an NSE index constituents CSV (e.g. Nifty 500; columns believed: Company Name, Industry, Symbol, Series, ISIN Code; unverified) and add a reader. Conglomerates (Reliance): single-industry peers are approximate; sum-of-the-parts from filing segments is a later item.

## Providers evaluated 2026-10-26 (see docs/2026-10-26-data-providers.md)
- Adopt TejHQ HF parquet: ISIN symbol history, corporate-action ex-dates, top-500 point-in-time universe (also unlocks a survivorship-bias-free backtest universe). Needs pyarrow dependency.
- Test Stoxim free key (user signs up): coverage vs claims, ratios incl. EV/EBITDA, shareholding, announcements, filing dates.
- TigZig for RBI macro and BRSR red flags later; licence per API unread; CC0 claim not found.

## TO FIND: faster bulk source OR smaller sector-targeted pool (added 2026-10-26)
Problem: scoring/peers need many companies' facts; Yahoo is per-ticker and slow (500 names stalled at ~80 in 40+ min; 30 names 1.5-5 min).
Ideas to evaluate, cheapest first:
1. Smaller sector-targeted pool: for a target, load only its NSE industry group from the index CSV (a few dozen names) plus nearest by size. Also enables sector-relative scoring (deferred S13). Needs a test that scores stay meaningful with small groups.
2. Take prices off Yahoo entirely: TejHQ parquet (prices_adjusted, metrics tree with returns and 52-week high/low) is a bulk file download, so returns/drawdown/volatility for all 500 need zero per-ticker calls. Halves the Yahoo calls.
3. Longer cache lifetimes by data type: fundamentals/statements 7 days (quarterly data), prices 1 day; incremental refresh; a pre-built cache for the default pool.
4. Parallel fetch with a small thread pool and polite backoff; measure Yahoo throttling first.
5. Bulk fundamentals source: none verified yet (Stoxim signup failed; TejHQ fundamentals planned; NSE XBRL manual). Re-check TejHQ for fundamentals, BharatStock free tier (25 requests/day, 1-year history), other providers; also ask whether a shared snapshot file of the pool's facts could be generated nightly and published with the repo (check data licences first).
Acceptance: peers/score for a target in under about 60 seconds on a cold cache, and fewer than 100 Yahoo calls.

## Explanation layer: measured and open items (2026-10-26)
- Live Gemini (gemini-3.1-flash-lite) on the real Reliance report: digest ~583-610 estimated tokens; real call 1,144-1,174 in (system prompt + digest) and 412-435 out, about 1.6k tokens total; all claims passed validation (numbers copied exactly). TradingAgents baseline was ~39k tokens for a 2-analyst run (different product, not like-for-like).
- Fixed from the live run: cache-vs-fresh mismatch (target now always uses the just-fetched facts), output truncation handling (cap 700, <=5 claims), template wording, mixed-source YoY caveat added by code.
- Open: the validator cannot catch loose language ("strong revenue growth"); consider banning intensity adjectives or requiring numbers in inference claims; Anthropic/OpenAI-compatible adapters untested live; token estimate undercounts (system prompt ~500 tokens not in the digest estimate); digest budget not yet tuned; no evaluation of explanation quality beyond validation rules.
- Browser verification done in Brave's Chromium engine via the browser-scenario tool (Claude in Chrome tools were not available in this session): crosshair, bar and chip tooltips, theme toggle (auto/light/dark) work; no JS errors. Not tested: real touch devices, Safari/Firefox, print.

## Observation metadata and the comparability gate (pasted guidance, 2026-10-26)
Every observation should carry: metric, period, basis, unit, source, restated (yes/no/unknown), evidence (URL and page/table), validation status. Before any growth figure: same metric, comparable periods, same basis and units, restatement checked, evidence traceable.
Have: metric, period (start/end/type/fiscal label), basis (consolidated/standalone/unknown), unit, source + source_field, status (ok/unverified/conflict/unavailable/gap/stale), fact ids.
Missing: `restated` (unknown everywhere today), `evidence` (filing URL and table/row; we only keep a label), explicit verified / needs-review flag, units checked on both sides.
Gap found by the live run: growth_yoy compares filing (consolidated) with Yahoo (basis unknown) and still returns ok (+28.0% revenue). Fix: a `comparability_check(cur, base)` returning issues; any issue makes the growth Fact `unverified` with the reasons, so checklist and score treat it as unavailable/unverified instead of ok.

## Second brain (see docs/SECOND_BRAIN.md): slices S1 snapshot store and "what changed", S2 thesis notes with kill criteria, S3 decision journal with automatic outcome review, S4 portfolio import and risk view, S5 watch digest, S6 markdown vault export.
## Verify growth on one basis: allow --filing to be given twice (current quarter and the year-earlier quarter) so year-on-year uses same source and basis and can be verified; the NSE results page we parse has no prior-year column. Confirmed on 2026-10-26: with the comparability gate, Reliance's profit and revenue growth are 'unverified' (filing vs Yahoo, basis differs), the checklist shows 2 unavailable and the growth factor is unavailable.

## ChatGPT can read NSE's rendered iXBRL pages; why we cannot (2026-10-26)
ChatGPT fetched the FY2025-26 Reliance consolidated results page (INTEGRATED_FILING_INDAS_152826_24042026225714_iXBRL_WEB.html) through its own browsing tool. From this project: curl gets an HTTP/2 error or a timeout, the web-fetch tool times out, and a headless-browser attempt was refused by the safety check as bot-check circumvention (correctly). We do not work around NSE's blocking.
Legitimate routes, in order: (1) user saves pages in their own browser (works today); `--filings-dir` now loads a whole folder, merges versions, flags restatements; (2) ask NSE for supported access (draft in docs/drafts/email-to-nse-xbrl.md, not sent); (3) raw XBRL instance (.xml) parser once the user supplies one sample; (4) parse the annual page's balance sheet, cash flow and prior-year columns once the user saves the FY2025-26 and FY2024-25 pages (our parser reads only the first value column of the quarterly page).

## Official NSE/BSE XBRL extractor spec (pasted 2026-10-26) vs this project
Done: comparability gate, version retention (sqlite), restatement detection across supplied filings (latest by filing date wins, superseded kept, both dates cited), filing metadata records (document, filing date, basis, audit status, rounding, currency, revision note or "not stated"), original reported number/unit/dimension on each figure, unit normalisation (lakhs to rupees, INR check), segment facts with dimension, folder ingestion.
Blocked: automatic discovery and download from NSE/BSE (scripts blocked; do not circumvent); BSE API returned 403 earlier.
Needs user-supplied files: (a) saved FY2025-26 and FY2024-25 annual pages for Reliance (the FY2025-26 URL from ChatGPT: .../INTEGRATED_FILING_INDAS_152826_24042026225714_iXBRL_WEB.html) to parse all value columns, comparatives, total comprehensive income, balance sheet and cash flow; (b) one raw XBRL instance (.xml) from the filing's XBRL link to read concept tags, contexts (instant vs duration) and dimensions. Neither is built yet; no tag-level data exists today (concept is empty for rendered pages).
Then: official-only Reliance FY2025-26 vs FY2024-25 comparison with exact citations and a cross-check of extracted totals against the page's visible statements.

## Claude Code plugin (2026-10-26)
Built: `.claude-plugin/plugin.json`, `commands/analyze.md`, `commands/changes.md`; CLI `--digest`, `--changes-only`. Tested end to end with `claude -p "/indiafacts:analyze RELIANCE.NS ..." --plugin-dir .`: ran in about 50 s and produced a cited explanation. Marginal tokens for our part: ~1.2k in (digest + rules), ~1.7k out; the session's own context (~32k cached) is separate and not ours.
Findings: command bash injection silently returns nothing (no model call) when the command uses `${VAR:-default}`, `$PATH`, or an unpermitted `cd`; plain `${CLAUDE_PLUGIN_ROOT}` and `$ARGUMENTS` work; compound commands need every part in allowed-tools. `uv` must be installed.
Open: `claude plugin validate` says the directory requires a LICENSE file (or `license` in plugin.json) and suggests author info and a README install line; the licence choice is the user's (recommendation: Apache-2.0 because TradingAgents, FinRobot and OpenBB are Apache-2.0). No marketplace.json yet (needs owner/repo).
## Sector-targeted pool: DONE `--sector-pool` (NSE industry group from an index CSV; sector-relative scores; loads only that group). Measure cold-cache time on the real Nifty 500 file and tune (still per-ticker Yahoo calls).

## Sector pool measured on real data (2026-10-26)
`--sector-pool --universe samples/ind_nifty500list.csv` for RELIANCE.NS: NSE group "Oil Gas & Consumable Fuels" = 19 companies, 16 fetched, 48.8 s total (acceptance was under ~60 s, under 100 Yahoo calls: met for this group). Real peers appeared (IOC, BPCL, HINDPETRO, AEGISLOG, PETRONET): P/E 21.6 vs peer median 10.3 (+110.9%), P/B 1.79 vs 1.37, net margin 6.7% vs 2.7%; sector-relative score 42.5/100, rank 13 of 19; growth unscored (unverified mixed-source). Larger groups (Financial Services 98, Capital Goods 70) will be slower: measure and consider capping to the N closest by size.

## Backtest v1 (done 2026-10-26)
`indiafacts/backtest.py`, spec `docs/2026-10-26-backtest-spec.md`, result `docs/2026-10-26-backtest-result.md`. Open: out-of-sample split fixed in advance, delisting returns from actions data, benchmark vs Nifty 50 TRI, symbol-chain stitching by ISIN, test the actual pool score (needs fundamentals history), plugin command, volatility-matched comparison.

## Deploy to Render (decided 2026-10-31; do later, needs the user's Render login)
`render.yaml` and `Dockerfile` are ready. Steps are in `docs/DEPLOY.md` and the chat of 2026-10-31: sign up with GitHub, New > Blueprint, pick the repo, apply, check `/api/health`, set `INDIAFACTS_MCP_HOSTS` and `INDIAFACTS_CORS`, put the URL in `.mcp.json` (copy `connector/mcp.json.example`), add the marketplace `pallavidhadda/nextrade` on claude.ai Customize > Plugins. Untested: the Docker build (no Docker on the dev Mac). Then Vercel: set `NEXT_PUBLIC_API_BASE`.

## Valuation depth (started 2026-10-31)
Done: sector-aware method choice, reverse DCF on trailing earnings (discount x years grid), justified P/B for banks (needs ROE). Next: EV/EBITDA vs peers, own-history percentile bands (needs multi-year filings), ROE from filings, banks' book value quality.

## Raw XBRL samples received 2026-10-31 (samples/, git-ignored)
`INDAS_104633_...xml` (Reliance standalone) and `INDAS_104634_...xml` (consolidated): filed 2024-04-22, Q4 FY2024 (quarter Jan-Mar 2024) with the full-year FY2023-24 in the same file; old `in-bse-fin` taxonomy (2020-03-31 entry point), contexts OneD (quarter) and FourD (year), ISIN-free but scrip code 500325, rounding Crores. Example values: consolidated FY24 revenue 9,144,720 crore, PBT 1,043,400 crore, profit 790,200 crore, EPS 102.90. Next: instance parser (contexts, dimensions, concept to metric map) and the FY2025-26 / FY2024-25 pages still needed from NSE.

## Live API measured 2026-10-31 (https://nextrade-api-7z41.onrender.com, Render free, Singapore)
`/api/health` and the MCP handshake pass (checked from the dev Mac). A real TCS.NS analysis with the default 30-company pool had reached only 16/30 after 490 s: about 30 s per company on the free CPU. The `INDIAFACTS_POOL_SIZE=12` setting from render.yaml was evidently not applied (progress counted /30). Actions: set `INDIAFACTS_POOL_SIZE` to 6 in the Render dashboard; speed work (TejHQ-based price metrics, cheaper per-company fetch, precomputed pool snapshot); show "waking up" in the UI.

## XBRL parser design notes (from the two raw files, 2026-11-02)
Instance uses taxonomy prefix `in-bse-fin`; contexts `OneD` (quarter) and `FourD` (year, by BSE id convention: the context dates in the file are both 2024-01-01..2024-03-31, so the year meaning rests on the id and on the values: consolidated FY24 revenue 9,144,720 cr and EPS 102.90 match public figures; treat as unverified until checked against the results page). Dimension contexts (39 of 46) carry segment and expense detail. Numeric concepts without dimensions include P&L lines (RevenueFromOperations, FinanceCosts, Depreciation..., ProfitBeforeTax, TaxExpense, ProfitLossForPeriod, EPS basic/diluted), ratios (DebtEquityRatio, InterestServiceCoverageRatio), and a FULL-YEAR CASH FLOW (CashFlowsFromUsedInOperatingActivities 1,587,880 cr, PurchaseOfPropertyPlantAndEquipment 1,528,830 cr), which gives free cash flow for a reverse DCF. Balance sheet items are likely instant contexts (not yet inspected). Values are in rupees (rounding 'Crores' only labels the display). Map to Facts with source `nse_xbrl`, filing id from the file name (INDAS_<id>_<id>_<DDMMYYYY><time>), basis from NatureOfReportStandaloneConsolidated, audit status from WhetherResultsAreAuditedOrUnaudited.
## Connector run log 2026-11-02
Live run 1 (TCS.NS, Render): reached 6/7 comparison companies (so INDIAFACTS_POOL_SIZE=6 is applied), then the job id became unknown (server restart or sleep, in-memory jobs lost). Live run 2: still running with no progress text after 10+ minutes. Likely causes: 0.1 CPU share, 4 parallel workers on 512 MB, Singapore to Yahoo latency. Try INDIAFACTS_WORKERS=1, persist job state on disk, show progress in the target phase.

## XBRL instance parser (done 2026-11-02)
`indiafacts/xbrl.py`: `--filing FILE.xml` and `--filings-dir` accept raw NSE XBRL. Quarter (OneD) and balance sheet (OneI) facts are ok; year-to-date (FourD) P&L, cash flow and EPS are `unverified` until a results page confirms the year meaning. Adds operating_cash_flow, capex_ppe, investing/financing cash flow, total_assets, total_liabilities, total_equity, equity_owners, cash_and_equivalents. Real check: Reliance consolidated FY24 EPS 102.90, total assets 17.56 lakh cr. Next: confirm FourD against the FY2023-24 results page, then use free cash flow in the valuation; extend to the newer integrated-filing taxonomy once a FY2025-26 file is available (taxonomy prefix may differ).
Live connector status 2026-11-02: three jobs (TCS, TCS, INFY) all became "unknown or expired" before finishing: server restarts continue.
