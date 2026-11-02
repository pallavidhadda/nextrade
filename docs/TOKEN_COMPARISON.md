# Like-for-like token test against TradingAgents (2026-11-02)
Research/education only; not financial, investment or trading advice. One run each, so treat this as a measurement, not a benchmark.

**Setup.** Ticker TCS.NS, decision date 2026-10-30, same model for both (Gemini `gemini-3.1-flash-lite` on the free tier, same key), same day. TradingAgents v0.7.1 with analysts market, fundamentals and news (social excluded: it needs Reddit or StockTwits keys), 1 debate round, 1 risk round, tool rounds capped at 4, output capped at 4,096 tokens, via our `run_baseline.py` that counts tokens per call. NexTrade: `python -m indiafacts TCS.NS --score --pool-size 12 --news --llm gemini --as-of 2026-10-30`, which includes the score against a 12-company pool, bull and bear lists, the rating, reference levels, risk lenses, headlines and one model call that narrates the digest.

| | TradingAgents | NexTrade |
|---|---|---|
| Model calls | 16 | 1 |
| Input tokens | 36,875 | 1,902 |
| Output tokens | 6,149 | 394 |
| Total tokens | 43,025 | 2,296 (about 5% of TradingAgents, 19 times fewer) |
| Final call | Overweight | Educational rating Underweight, confidence Medium |

**Caveats, stated plainly**
- The two ratings disagree. Neither is known to be right; the decision journal will settle ours against the Nifty 50 after 21 sessions, and TradingAgents' own memory log does the same for its decisions.
- With a past decision date NexTrade correctly refuses today's live overview, so valuation ratios, ROE and trailing EPS were unavailable; quality and value factors could not be scored (3 of 5 factors had data). TradingAgents has a similar guard for undated statements, so both were limited, but I did not inspect which numbers TradingAgents' analysts actually saw. The token comparison holds; a quality comparison would need a full read of both reports.
- The score is a percentile inside a pool of 10 comparison companies after failures; with a pool that small the rank is weak evidence.
- TradingAgents ran with 3 of its 4 analysts. A full run would cost more.
- Wall-clock: the TradingAgents run was slowed by our 4.5-second rate limiter between calls; not compared.
- Where the NexTrade tokens go: a digest of about 1,700 estimated tokens plus 294 of instructions. The model writes a short explanation; every number comes from code.
