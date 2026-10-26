# Roadmap report (2026-10-26)
Research/education only; not financial, investment or trading advice.

## Goal
A public portfolio project: enter an NSE/BSE ticker, get a profile-aware research report built from source-linked facts; India first; minimum LLM tokens (free API tier or Claude Code plugin); front end later.

## Built (82 offline tests pass, 1 live test, 19 local commits, nothing pushed)
| Area | Status |
|---|---|
| Baseline | TradingAgents run on Gemini free tier: 13 calls, ~39k tokens, Hold. Found its gaps (blind fundamentals, shallow debate). |
| Research | Reviewed ai-hedge-fund, FinRobot, OpenBB, TradingAgents source; competitor landscape; licences (Apache-2.0 x3, MIT x1). |
| Fact engine (`indiafacts`) | Typed Facts with period, unit, source, basis, availability date; fiscal calendar; gap detection (caught the missing Sep-25 quarter); TTM only from 4 consecutive quarters; reconciliation (price = P/E x EPS); fact-only renderer; CLI. |
| Official filing import | Parses a saved NSE results page: ISIN, BSE code, consolidated flag, real filing date, P&L, EPS, ratios, segments. Cross-checks vs Yahoo (net profit, interest, EPS match exactly; revenue 0.8% apart). |
| EBITDA guard | Derives EBITDA from filing; flags Yahoo "EBITDA" that equals EBIT and demotes that series. |
| Specs and test lists written | Fact model (22 tests), factor scoring (20), price history (15), investor profile (9), security master (8). |
| Verified data facts | Yahoo prices from 1996, Nifty 50 from 2007; prices split-adjusted; FinBridge MCP checked (below). |

## Not built yet
| # | Item | Size | Blocked on |
|---|---|---|---|
| 1 | DONE 2026-10-26: Security master (renames from NSE symbolchange.csv, curated TATAMOTORS demerger) | S | equity list CSV optional, not needed yet |
| 2 | DONE 2026-10-26: Price history and metrics (returns, drawdown, vol, beta vs Nifty 50, corporate-action flags) | M | none |
| 3 | DONE 2026-10-26: Investor profile (user sets horizon; presets drive weights; simple/pro view) | S | none |
| 4 | DONE 2026-10-26: Factor scoring + 9-point checklist + bad-data tests (sector-relative groups and bank metric set partly deferred) | M | 2, 3 |
| 5 | IN PROGRESS: Peer groups (deterministic tiers: industry then sector, size band, positive P/E gate, median with not-meaningful cap) and relative valuation table | M | 1 (done) |
| 5b | DONE 2026-10-26 (v1): Visual HTML report: price vs Nifty 50, drawdown, quarterly bars with visible gaps, score and checklist strips, segment bars, peer dot plot; terminal sparklines. Use the dataviz skill; only computed numbers | M | 4, 5 |
| 6 | DONE 2026-10-26 (v1): evidence-linked claims typed fact/inference/hypothesis, deterministic triggers, code-side validation | M | 4 |
| 7 | DONE 2026-10-26: one cached LLM call (Gemini live-tested; OpenAI-compatible and Anthropic adapters tested with fake HTTP); measured 1,174 in + 435 out tokens for a full Reliance report | S | 6 |
| 8 | Backtest and scorecard (out of sample, costs, benchmark) | L | 2; fundamentals history is thin (about 5 quarters), so first version is price-based only |
| 9 | DONE 2026-10-26: Claude Code plugin (/indiafacts:analyze, /indiafacts:changes), tested end to end | S | 4-7 |
| 10 | Staleness controls (review_by dates, canary tests, data-age banner) | S | runs through all |
| 11 | Independent code review, CI, README/licence/disclaimer, push to public repo | S | licence choice |
| 12 | Web front end (Next.js + thin API), simple and pro views | M | 4-7 |

## Added 2026-10-26
- HTML report with charts (price vs Nifty 50, quarterly bars with visible gaps, score bars, checklist strip, segment bars); terminal sparklines. Use the dataviz skill.
- Security-master equity list (ISIN master) importer; sector field exists on Entity; sector-relative scoring groups.

## Provider-driven additions 2026-10-26
- 5c: DONE 2026-10-26: TejHQ adapter (ISIN symbol history, rename detection, merger/demerger ex-dates, point-in-time top-N universe `--universe tej:N`); curated demerger table kept for successor lists. TejHQ history starts 2010; NSE symbolchange.csv covers older renames.
- 5d: Stoxim PARKED (signup not working). Dated fundamentals stay: Yahoo + saved NSE results pages.
- 5e: TigZig RBI macro and red flags (later).

## Second brain (docs/SECOND_BRAIN.md), added 2026-10-26
S1 snapshot store and what-changed; S2 thesis notes with kill criteria; S3 decision journal and outcome review; S4 portfolio import and risk view; S5 watch digest; S6 markdown vault export. Also: two-filing growth verification.

## Done 2026-10-26 (later)
Claude Code plugin; --sector-pool; --digest and --changes-only.
S1 snapshot store and what-changed (sqlite); comparability gate; multi-filing merge with restatement notes; filing metadata records; --filings-dir.
Next for official data: annual pages (all columns, balance sheet, cash flow) and raw XBRL instance parser, both waiting on user-saved files.

## Cut line for a first public demo (v0.1)
Items 1-7 and 9, in the terminal and as a Claude plugin. Backtest (8) and web UI (12) come after; the demo will state plainly that no performance claim is made.

## How to go faster (my recommendations)
1. One combined plan for items 1-3 and build it in one run; stop writing a separate approval document for every step.
2. Ask you only at four points: the two CSV downloads, the licence choice, weight presets (done), and the v0.1 cut line.
3. Parallel work: items 1, 2 and 3 are independent. I can run them as three parallel workers if you allow subagents (I only start them when you ask).
4. Peers v1 = same sector plus size band; skip fancy tiers until later.
5. Keep TDD but trim fixtures to what each test needs.
6. Do the LLM layer last; it is the least risky and the cheapest to change.

## Honest status and risks
No independent review yet; no CI; free data is unofficial (Yahoo) and has quirks; label-based filing parser is fragile; no backtest evidence, so no claim that any score predicts returns; SEBI advice rules unverified with a lawyer; deadline-based availability dates are estimates.

## FinBridge MCP (checked 2026-10-26)
Its own docs list Korea (OpenDART), US (SEC EDGAR), Japan (EDINET), Taiwan (TWSE/TPEx) and European (ESEF) filers; India (NSE/BSE) is not mentioned. Free plan: 10 tool calls/day, last 4 fiscal years of statements, 130 trading sessions of prices; point-in-time support not stated; use terms not stated. Not a fit for India. The claim you pasted that it covers India point-in-time was not supported.
