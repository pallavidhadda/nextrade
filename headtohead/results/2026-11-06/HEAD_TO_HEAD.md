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
