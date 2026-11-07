# Head-to-head, 2026-11-06 (27 tickers with both systems complete)
Research/education only; not financial, investment or trading advice. Same Gemini key and model for both. TradingAgents ran with market, news and fundamentals analysts (social needs keys); NexTrade ran with the score, news and one Gemini narration. One run per ticker.

| | TradingAgents | NexTrade |
|---|---|---|
| Model calls per ticker (mean) | 16.3 | 1 |
| Tokens per ticker (mean / median) | 58,923 / 60,279 | 2,293 / 2,246 |
| Seconds per ticker (mean) | 90 | 18 (includes the shared pool fetch) |
| Ticker reports with no usable fundamentals | 26 of 27 | 0 of 27 have no business-health rows |
| Numbers in the final decision found in none of its own reports | 68 of 175 | not applicable: AI claims are machine-checked against the digest |
| Rating mix | Buy 0, Overweight 16, Hold 11, Underweight 0, Sell 0 | Buy 4, Overweight 8, Hold 13, Underweight 2, Sell 0 |
| Same direction (bullish, neutral, bearish) | 44% of tickers | |

Outcome quality is not judged here: record both ratings with `--record`, then run `--settle` after 21 trading sessions to score each system's ratings against the Nifty 50.


## Reading the numbers (added by hand, 2026-11-07)
**Status:** 27 of 30 tickers have a complete pair. Not finished: M&M.NS (TradingAgents rejected the ticker: it refuses any symbol containing "&" as an invalid file-path name, so it cannot analyse Mahindra & Mahindra at all; NexTrade handled it), TECHM.NS (TradingAgents run hit the Gemini free-tier quota) and the last ticker in the list (not started). Rerun `python headtohead/orchestrate.py --date 2026-11-06` after the quota resets or with another key to finish.

**What the run supports**
- Cost: TradingAgents used about 16 calls and 59k tokens per ticker, NexTrade 1 call and 2.3k (about 26 times fewer tokens, 5 times faster).
- TradingAgents' fundamentals analyst reported it could not obtain statements on 26 of 27 Indian tickers, so its ratings rest mostly on price indicators. (The test is a keyword check on the first 700 characters of its fundamentals report, so it can miss; LT.NS was the one that passed.)
- TradingAgents never gave Underweight or Sell: 16 Overweight and 11 Hold. A bullish lean with no negative call is worth watching.
- The two systems agree on direction for only 44% of tickers. Neither is known to be right yet.

**What it does not show, and where NexTrade looks weak**
- "Numbers in the decision found in none of its reports" (68 of 175) is a proxy: some are legitimately derived levels such as a stop calculated from ATR, so it is not a count of invented numbers.
- NexTrade's confidence is "High" on 26 of 27 tickers. That label is only counting how many score factors had data, so it carries almost no information. This needs fixing before anyone reads meaning into it.
- NexTrade scores against a 12-company pool, so ranks are coarse; four Buys (AXISBANK, SBIN, ICICIBANK, COALINDIA) deserve a look for pool or metric artefacts before they are believed.
- One run per ticker, one model, one day. No outcome data yet: after 21 trading sessions (about 8 December) run `report.py --record` once and `report.py --settle` to score both systems' ratings against the Nifty 50.
