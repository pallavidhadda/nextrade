# Where AI is used, where code is used, and how this compares with TradingAgents (2026-11-07)
Research/education only; not financial, investment or trading advice. TradingAgents v0.7.1 (TauricResearch, Apache-2.0) read from its source in `TradingAgents/`; its results are the two logged runs in `~/.tradingagents/logs` (RELIANCE.NS 2026-10-23, TCS.NS 2026-10-30) and the token counts in `docs/TOKEN_COMPARISON.md`. One run per ticker: measurements, not a benchmark.

## 1. NexTrade: AI versus code, module by module
| Step | Who does it | Notes |
|---|---|---|
| Fetching prices, statements, filings, feeds | code | Yahoo, NSE XBRL and RSS, daily participant file, files you save |
| Identity, renames, demergers, fiscal calendar, gaps, TTM, reconciliation | code | typed facts with period, unit, source, basis, availability date |
| Ratios, growth, FCF, EV/EBITDA, ROCE, net debt, lender metrics | code | `fundamentals.py` |
| Indicators (SMA, RSI, MACD, Bollinger), returns, drawdown, volatility, beta | code | `indicators.py`, `pricemetrics.py` |
| Pool score, checklist, peer medians, price-implied valuation (reverse DCF) | code | percentile ranks, fixed bands, stated assumptions |
| Bull and bear lists, the five-point educational rating, confidence | code | rule-based; weights are proposals |
| Reference levels, risk lenses, position ceilings | code | volatility-based arithmetic |
| Shareholding, pledges, FII/DII, market flows | code | official files and feeds |
| News headlines and the sentiment hint | code | RSS, de-duplication, keyword hint (no model) |
| Claim checker ("was TCS EPS 142.66?") | code | looks the figure up in sourced facts |
| Decision journal, settlement against the Nifty 50, scoreboard | code | |
| Plain-English explanation | template by default; **optional AI** | one call on a ~2k-token digest; user's own key |
| Analyst panel (5 analysts and a manager) | **optional AI** | six calls, same digest, same checks; user's own key |
| Checking any AI answer | code | ids must exist, every number must appear in the digest, advice wording is rejected, bad claims are dropped |
So AI is never in the loop that produces a number, a score or the rating. It can only narrate facts that code already collected, and its output is machine-checked. By default a report uses zero model calls.

## 2. TradingAgents: where it uses AI
Four analysts (market, news, sentiment, fundamentals) each run a tool-calling loop (up to 20 rounds), then a bull and a bear researcher debate, a research manager rules, a trader proposes entry, stop and size, three risk debaters argue, and a portfolio manager decides. Roughly 13 to 16 model calls per run. The model fetches data through tools, does the arithmetic, writes prose, argues, and decides. Code only routes, parses the rating and keeps a memory log that settles past decisions and feeds lessons back into prompts.

## 3. Side by side
| | TradingAgents | NexTrade |
|---|---|---|
| Model calls per report | 13 to 16 | 0 by default; 1 with narration; 6 with the panel |
| Tokens (TCS.NS, same model, same day) | 43,025 | 2,296 for one narration (about 5%); the 6-call panel is about 15k |
| Source of every number | tool output pasted into prose; no provenance | typed fact with period, unit, source, basis; gaps stated |
| Fundamentals for Indian stocks | **empty in both logged runs**: its fundamentals report says the tools "withheld" the statements, so the decision rested on price indicators | annual and quarterly statements, ratios, official filing cross-checks, ownership |
| Same inputs, same output? | no (model sampling) | yes for everything except optional prose |
| Can the model invent a number? | yes, nothing checks it | no: unknown ids, unseen numbers and advice words are rejected |
| Final output | Overweight TCS "initiate a 30% position at 2502.60, stop 2330" | educational rating with confidence, reference levels and a position ceiling by risk lens; no target price |
| Result on the logged tickers | RELIANCE Hold; TCS Overweight | RELIANCE Hold; TCS moved to Hold after we stopped counting trivial checks as points |
| Decision tracking | memory log, settles against realised and alpha return | journal settles against the Nifty 50; scheduled rating job; scoreboard |
| Tests | about 1,000 | about 500 |

## 4. How NexTrade improves on it, and where it does not
Improvements, with evidence: about 19 times fewer tokens measured; India-aware data where TradingAgents was blind; provenance and honest gaps; reproducibility; machine-checked AI output; a cheaper optional panel for people who want agent-style reading.
Where TradingAgents is stronger, plainly: real multi-agent adversarial reasoning (the debate can surface a counter-argument no rule would), a wider tool set (SEC filings, macro series, prediction markets, Reddit and StockTwits), a trader proposal, checkpoint and resume, many LLM providers, a bigger test suite, and a reflection loop that feeds past outcomes into later runs. We chose not to copy the debate and the trader step because they cost tokens and produce ungrounded sizing.
What neither has: evidence that its rating predicts returns. Both rely on a settlement log that needs weeks of data; ours has started (five weeks to first settled rows).

## 5. What an AI product manager would do next
1. **Quality eval, not just cost:** run both systems on the same 30 tickers and dates and compare faithfulness (share of claims traceable to evidence), coverage of real fundamentals, and agreement of ratings with later 21-session outcomes.
2. **Judge the panel against the single narration:** use a different model as a blind judge on 50 reports; keep the panel only if it adds insight per extra token.
3. **Track AI failure modes:** rate of answers rejected by the checks, per provider and model; this is the product's trust metric.
4. **Cache and cap:** the digest is identical across the six panel calls, so provider prompt caching should cut the panel to well under 10k billable tokens.
5. **Close the loop:** feed settled outcomes into the threshold tuning of the rating, in code, not into a prompt.
