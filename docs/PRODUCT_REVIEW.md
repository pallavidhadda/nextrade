# Product review and ranked action list (2026-10-31)
Research/education only; not financial, investment or trading advice.

**Evidence rules.** NexTrade scores come from what is built and measured in this repo. Competitor scores are my judgement from reading their source or docs (see `RESEARCH_NOTES.md`, `COMPETITIVE_BRIEF.md`); I did not run them except TradingAgents (one baseline run). Community size and release cadence were not measured, so "maturity" reflects what I could verify only. Treat the table as a hypothesis to check, not a ranking to quote.

## 1. Where NexTrade stands (1 weak to 5 strong)
| Dimension | NexTrade | TradingAgents (our base) | ai-hedge-fund | FinRobot | OpenBB |
|---|---|---|---|---|---|
| India coverage (NSE/BSE identity, filings, corporate actions) | 4 | 1 | 1 | 1 | 2 |
| Provenance and honesty about gaps | 5 | 2 | 2 | 4 | 3 |
| Token cost per report | 5 (about 1.6k with a model, 0 without) | 1 (about 39k measured) | 3 | 2 | 4 (platform) |
| Analytical depth (valuation, scenarios) | 2 | 3 | 3 | 5 | 3 |
| Evidence a signal works (backtest) | 2 (price-only, hint) | 2 | 4 | 1 | 2 |
| Usable UI | 4 (live app, early) | 2 (CLI) | 3 | 3 | 4 |
| Privacy and bring-your-own-key | 4 | 3 | 3 | 2 | 3 |
| Extensibility and ecosystem | 2 | 4 | 4 | 3 | 5 |
| Maturity (tests, review, community) | 2 (about 350 offline tests, no outside review, no users) | 4 | 4 | 3 | 5 |
| Setup ease | 3 | 3 | 3 | 1 | 3 |

**Versus the base repo (TradingAgents):** clearly ahead on India data, trust, cost, privacy and having a real UI; behind on depth of narrative analysis, agent-framework flexibility and community. It is a different product: facts and explanation, not an agent debate that ends in Buy/Hold/Sell.
**Versus the field:** ahead on provenance and India fit; far behind FinRobot on valuation depth and OpenBB on breadth; behind Screener.in/Tickertape/Trendlyne on history and screens (their years of fundamentals vs our about five quarters).

## 2. Ranked actions (impact x confidence / effort)
| Rank | Action | Why it matters | Effort | Needs you |
|---|---|---|---|---|
| 1 | Official annual and quarterly filing data (XBRL pages you save, parsed in the browser or CLI) | Unblocks growth, TTM, verified comparisons; the biggest data weakness | M | Yes: save pages |
| 2 | Deploy API + web as a live link, with rate limit and queue | Nothing is usable by anyone else until it runs somewhere | S | Yes: choose host |
| 3 | Valuation depth: relative valuation and reverse-DCF as code operators, shown as ranges with caveats, never targets | The main gap against FinRobot and screeners | M | No |
| 4 | Independent code review and a SEBI/legal check of wording ("research assistant", no advice) | Gate for going public | S | Yes: lawyer |
| 5 | Multi-year fundamentals: let users drop in several saved filings at once; merge with restatement notes | Fixes the thin-history problem without paid data | M | Some |
| 6 | Backtest the actual pool score; stitch renamed symbols by ISIN; add index benchmark | Turns "hint" into evidence either way | M | No |
| 7 | Holdings input kept in the browser: concentration and sector exposure against the profile | The "portfolio info" you wanted; high user value | M | No |
| 8 | API hardening: per-IP limits, timeouts, health, logs without payloads | Safety once public | S | No |
| 9 | Second brain S2-S3: thesis notes with kill criteria, decision journal | Differentiator no OSS project has for India | M | No |
| 10 | QA: phone, Safari, Firefox, keyboard, contrast audit; Hallmark finish review | Quality bar for a portfolio piece | S | No |
| 11 | Speed: TejHQ-based price metrics, parallel fetch, cap group size (Financial Services has 98 names) | 49 s is OK, 3 min is not | M | No |
| 12 | Public repo hygiene: README with GIF, CONTRIBUTING, issue templates, pinned deps, plugin icon | First impression | S | Icon art |
| 13 | Staleness canaries for Yahoo field changes | Free data breaks silently | S | No |
| 14 | Other data: TigZig/RBI macro, IMF via OpenBB | World data second, as you asked | M | No |

## 3. Cut line for a public launch
Ranks 1, 2, 4, 8, 10, 12 plus an honest "what this is not" page. Ranks 3, 5, 6, 7 make it competitive; 9 makes it distinctive.

## 4. Risks
Free data (Yahoo) is unofficial; label-based filing parser is fragile; NSE/TejHQ redistribution terms unverified; no independent review; no claim of predictive power is supported.
