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
