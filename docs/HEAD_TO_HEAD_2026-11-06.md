# Head-to-head, 2026-11-06 (29 tickers with both systems complete)
Research/education only; not financial, investment or trading advice. Same Gemini key and model for both. TradingAgents ran with market, news and fundamentals analysts (social needs keys); NexTrade ran with the score, news and one Gemini narration. One run per ticker.

| | TradingAgents | NexTrade |
|---|---|---|
| Model calls per ticker (mean) | 16.3 | 1 |
| Tokens per ticker (mean / median) | 59,181 / 60,415 | 2,291 / 2,246 |
| Seconds per ticker (mean) | 89 | 17 (includes the shared pool fetch) |
| Ticker reports with no usable fundamentals | 28 of 29 | 0 of 29 have no business-health rows |
| Numbers in the final decision found in none of its own reports | 74 of 194 | not applicable: AI claims are machine-checked against the digest |
| Rating mix | Buy 0, Overweight 17, Hold 12, Underweight 0, Sell 0 | Buy 4, Overweight 8, Hold 14, Underweight 2, Sell 0 |
| Same direction (bullish, neutral, bearish) | 41% of tickers | |

Outcome quality is not judged here: record both ratings with `--record`, then run `--settle` after 21 trading sessions to score each system's ratings against the Nifty 50.


## Reading the numbers (added by hand, 2026-11-07)
**Status (updated 2026-11-16):** 29 of 30 tickers have a complete pair. TECHM.NS and JSWSTEEL.NS were finished on 2026-11-16 with the same analysis date; their NexTrade side ran on the newer code (sector comparison), so those two are not strictly like-for-like with the other 27. M&M.NS can never complete: TradingAgents refuses any symbol containing "&" as an invalid file-path name. The analysis below was written on the 27 pairs; the table above is the 29-pair result and moves only slightly. All 58 ratings were recorded in the local journals on 2026-11-16 (`report.py --record`); settle with `report.py --settle` on or after 8 December 2026.

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

## Follow-up: confidence label fixed (2026-11-07)
The rating's confidence now comes from six visible ingredients instead of only counting factors: factors with data, size of the comparison pool (25 or more is strong, 12 or more is passable), checks that could be measured, distance from a rating boundary, whether the score and the evidence points agree, and whether annual business-health data is present. Fewer than four factors is always Low. The reason line states which ingredients decided it (for example "close to a rating boundary, the score and the evidence points disagree"). Re-running the deterministic part on a sample of 12 of the 27 tickers gave 6 High and 6 Medium, against 26 of 27 High before. This is a label of how well-supported the reading is; it is not a probability of being right, and it will only be validated once the journal settles.

## Head to head on the 27 complete pairs: verdict (2026-11-07)
No outcome data yet, so "better" below means better on what can be measured today, not better at picking stocks.

| Question | TradingAgents | NexTrade | Edge |
|---|---|---|---|
| Cost per ticker | 16.3 calls, about 59k tokens, 90 s | 1 call, about 2.3k tokens, 18 s | NexTrade |
| Real company fundamentals used | keyword check: "unable to get statements" on 26 of 27; about 12 numbers in its fundamentals report | statements, ratios, ownership present on all 27 | NexTrade |
| Handles every Indian ticker | no: refuses M&M.NS (the "&" is rejected) | yes | NexTrade |
| Can show where a number came from | no | yes, period, unit, source | NexTrade |
| Repeatable | no (model sampling) | yes, apart from optional prose | NexTrade |
| Balanced calls | 16 Overweight, 11 Hold, 0 negative | 4 Buy, 8 Overweight, 13 Hold, 2 Underweight | NexTrade (but 4 Buys unverified) |
| Concrete action plan (entry, stop, size) | yes, every ticker | reference levels only for bullish ratings, no sizing advice | TradingAgents, by design |
| Debating both sides in prose | yes | rule-based lists | TradingAgents (more readable; unproven value) |
| Predicts returns | unknown | unknown | tie until 21-session settlement |

What drives each rating (checked against prices up to 6 Nov 2026):
- TradingAgents follows short-term trend: 75% of its bullish names were above their 200-day average against 36% of the rest. Its rating correlates 0.39 with "above the 200-day average" and 0.21 with one-year return relative to the Nifty.
- NexTrade follows one-year relative performance plus fundamentals: its bullish names beat the Nifty by 12.7% over a year on average and the rest lagged by 5.0%; correlation 0.52. That is partly built in (momentum and the "beats the Nifty" check are inputs), so it is not evidence of skill.
- The two ratings are almost uncorrelated (0.06). They are answering different questions: TradingAgents asks "is the chart healthy", NexTrade asks "are the business and the price record healthy".

Cases that show the difference: ADANIENT.NS. TradingAgents said Overweight on chart levels alone (RSI 54.7, 50-day average), with no fundamentals. NexTrade said Underweight because quality and risk scored 3 of 100 in the pool and profit fell 54.8% in the last financial year, evidence TradingAgents could not see. The reverse worry applies to NexTrade's Buys (AXISBANK, SBIN, ICICIBANK, COALINDIA): all four are up 11% to 21% against the Nifty over a year, so their ratings may be mostly momentum from a 12-company pool.

Bottom line: NexTrade is clearly better on cost, coverage of Indian fundamentals, honesty about data, reliability and repeatability. TradingAgents is better at producing a readable action plan and a two-sided argument. Whether either rating is useful is settled only by the outcome run around 8 December; until then neither can be called more accurate.


## Follow-up: closing the two gaps TradingAgents led on (2026-11-07)
1. **A readable plan for every ticker.** New scenario plan (`indiafacts/scenario.py`) for every rating, not only bullish ones: reference levels (entry area, confirmation, invalidation, or upside and downside triggers for a neutral rating), a staged exposure ceiling (thirds of the risk-lens ceiling, halved when confidence is low, a third at most for a cautious rating), the next results date, and what would turn the view more positive or more cautious. All arithmetic on measured prices and stated limits; no price targets; it avoids the words in the advice filter, and a test enforces it.
2. **A two-sided argument that reads well.** New `indiafacts/narrative.py` joins the bull and bear points into short paragraphs grouped by theme, names the side that carries most weight and says how the rating was weighed. No model needed. For readers who want a real debate there is an optional three-call mode (bull advocate, bear advocate who answers it, referee) with the user's own key, validated like every other answer; about 8k tokens against about 59k for TradingAgents.
Not yet tested against a live model: Gemini returned a 429 quota error today, so the debate mode is tested with a fake model only. The scenario plan and prose are deterministic and were checked on real data (TCS.NS).


## Follow-up: the four Buys checked (2026-11-16)
The worry was that AXISBANK, SBIN, ICICIBANK and COALINDIA scored Buy only because of the mixed 12-company pool. Re-run with today's code, which ranks each company inside its NSE Market Lens sector (40 banks; 20 energy companies with full data):

| Ticker | 6 Nov (12-name mixed pool) | 16 Nov (sector pool) | What changed |
|---|---|---|---|
| AXISBANK | Buy 65.6, value 92 | Overweight 51.3, value 27 | The value score was the artefact: banks look cheap on P/E and P/B next to consumer and IT names |
| SBIN | Buy 64.1, value 100 | Buy 56.9, value 36 | Value fell; still Buy on quality 72 and risk 80 inside the banks, plus 9 supporting points and none against |
| ICICIBANK | Buy 72.3, value 54 | Buy 64.2, value 11 | Still Buy, now on quality 91 and risk 96; it is the most expensive bank in the group |
| COALINDIA | Buy 64.5, value 94 | Buy 65.4, value 64 | Holds up inside the energy group: quality 72, risk 90, free cash flow 12.5% of market value |

Findings: (1) the mixed-pool value artefact was real and the sector comparison removes it; (2) one more artefact was found and fixed: SBIN earned a supporting point for "debt is lower than equity (debt-to-equity 0.00)", which means nothing for a bank, so the debt check is now not applicable for lenders; (3) official quarterly results and shareholding had silently stopped downloading because NSE's listings moved their file links to `nsearchives.nseindia.in`; fixed, and lenders now get gross and net NPA, CET1 and net interest income from the standalone filing. The remaining Buys are sector-relative readings, not proven calls; the 8 December settlement is the first real test.
