# Head-to-head, 2026-11-06 (1 tickers with both systems complete)
Research/education only; not financial, investment or trading advice. Same Gemini key and model for both. TradingAgents ran with market, news and fundamentals analysts (social needs keys); NexTrade ran with the score, news and one Gemini narration. One run per ticker.

| | TradingAgents | NexTrade |
|---|---|---|
| Model calls per ticker (mean) | 16.0 | 1 |
| Tokens per ticker (mean / median) | 59,903 / 59,903 | 2,216 / 2,216 |
| Seconds per ticker (mean) | 72 | 14 (includes the shared pool fetch) |
| Ticker reports with no usable fundamentals | 1 of 1 | 0 of 1 have no business-health rows |
| Numbers in the final decision found in none of its own reports | 4 of 9 | not applicable: AI claims are machine-checked against the digest |
| Rating mix | Buy 0, Overweight 0, Hold 1, Underweight 0, Sell 0 | Buy 0, Overweight 0, Hold 1, Underweight 0, Sell 0 |
| Same direction (bullish, neutral, bearish) | 100% of tickers | |

Outcome quality is not judged here: record both ratings with `--record`, then run `--settle` after 21 trading sessions to score each system's ratings against the Nifty 50.
