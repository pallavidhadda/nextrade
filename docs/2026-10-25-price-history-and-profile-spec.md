# Price history + investor profile — spec and test cases (DRAFT for approval)
Research/education only; not financial, investment or trading advice. Nothing is built.
Decision from you: the USER sets the holding horizon through a profile; the agent chooses factor weights and the evaluation horizon from it.
Build order I propose (each is a separate plan): A price history, then B profile, then D scoring (uses A and B), then C peer groups.

## A. Price history facts
Verified 2026-10-25 (Yahoo): RELIANCE.NS daily OHLCV from 1996-01-01 (7,730 rows); Nifty 50 index ^NSEI from 2007-09-17 (4,686 rows); ^BSESN from 1997; NIFTYBEES.NS (Nifty ETF) from 2009. `Close` is split-adjusted (Reliance's Oct-2024 bonus shows as split 2.0, no jump); `Adj Close` also adjusts dividends. 117 zero-volume days for RELIANCE (index volume is zero by nature).
Design (my calls):
- `PriceSeries` object (arrays of dates and prices, source, adjustment basis, retrieved_at, events list of splits/dividends). Row-level Facts would be huge, so Facts are the derived metrics only; each cites the series id, window and adjustment basis.
- Derived metrics (computed, no LLM): price return 1y/3y/5y (split-adjusted Close, dividends excluded, same basis for stock and Nifty 50), relative return vs Nifty 50, max drawdown over 1y/3y/5y, 52-week high/low and percent from each, annualised volatility (daily log returns x sqrt(252)), beta vs Nifty 50 (1y, 3y). Momentum score inputs (12-1 month return) for the pro view.
- Window rule: "N years" = N x 365 calendar days back to the nearest earlier trading day; insufficient history gives `unavailable("history shorter than N years")`.
- As-of: series is truncated to the as-of date (no look-ahead). Caveat printed: Yahoo adjusts past prices to today's share count, so price LEVELS for past dates differ from what was traded; returns and drawdowns are unaffected.
- Data-quality checks reported, never silent: zero-volume days, gaps > 5 consecutive weekdays, non-positive or NaN prices, duplicate dates, last bar older than 3 trading days vs as-of, listed splits/dividends.
- Raw price rows never go to an LLM.

Tests (A):
P1 1y/3y/5y returns match hand-computed values on a synthetic series.
P2 A 2-for-1 split in the raw series (price halves) leaves split-adjusted returns unchanged and lists the event.
P3 Return window starts at the nearest earlier trading day when the exact date is a holiday.
P4 History shorter than the window gives unavailable with reason.
P5 Max drawdown on a known up-down-up series equals the hand value; monotonic rising series gives 0.
P6 52-week high/low and percent-from-high correct; uses only last 365 days.
P7 Volatility of constant prices is 0; of a known alternating series matches hand value to 4 decimals.
P8 Beta of a series that is exactly 2x the benchmark's returns equals 2.0; of constant series is unavailable.
P9 Stock and benchmark are aligned on common dates only; non-overlapping data gives unavailable.
P10 As-of truncation: metrics at an earlier date ignore later bars (leakage test with a spike after as-of).
P11 NaN, zero or negative price rows are dropped, counted and reported; dedupe by date keeps last and flags conflicting duplicates.
P12 Gap detection flags a 10-weekday hole but not a 3-day weekend.
P13 Stale last bar flagged.
P14 Every metric Fact has source, window, adjustment basis and the not-advice disclaimer in rendered output; no keys in output.
P15 Live (marked) test: RELIANCE.NS and ^NSEI fetch, rows > 5000 and > 4000, last date within 7 days.

## B. Investor profile
Fields: goal (growth | income | preservation), horizon bucket (under 1y | 1-3y | 3-5y | 5y+), risk tolerance (low | medium | high), risk capacity (low | medium | high), max single-stock share (percent), liquidity need (can lock away | may need within 1y), experience (beginner | expert, sets default view). Effective risk = the LOWER of tolerance and capacity (SEBI-style "unwilling or unable"). Stored locally as a small JSON file, no personal identifiers, no server.
Profile drives: factor weights (versioned preset file; numbers are my proposals, not evidence-based, to be tuned and backtested), the evaluation horizon, which view shows, and the wording ("fits / does not fit this profile on these facts", never buy or sell).
No profile given: output uses a labelled default profile ("default: 5y+, medium risk, beginner view") and says so.
Open: preset weights per horizon (e.g. 5y+: quality 35, value 25, growth 25, risk 10, momentum 5; under 1y: momentum 35, risk 25, value 15, quality 15, growth 10) are proposals for you to edit.

Tests (B):
PR1 Effective risk is min(tolerance, capacity) for all 9 combinations.
PR2 Invalid enum or out-of-range percent is rejected with a clear message.
PR3 Every preset's weights sum to 1.0; a preset file that does not is rejected.
PR4 Horizon bucket maps to the evaluation horizon used by the scorecard (under 1y -> 63 trading days, 1-3y -> 504, 3-5y -> 1008, 5y+ -> 1260; proposals).
PR5 Profile hash appears in every output that used it; changing a field changes the hash.
PR6 Beginner profile selects the simple view, expert the pro view; override flag works.
PR7 Missing profile triggers the labelled default and the notice.
PR8 Rendered fit text contains none of the words buy, sell, hold-as-instruction; contains the disclaimer.
PR9 Two profiles with different horizons give different weights but identical facts (only weighting differs).

## Questions for you
1. Are the proposed horizon weight presets a fair starting point, or do you want to set them?
2. Benchmark: Nifty 50 price index (^NSEI) is what I verified; a total-return index is better for long periods but I have not found a free source. OK to use ^NSEI and label it?
3. Do you want the profile saved between runs (a local file) or asked each time?

## Next
On approval: plan A (price history) with tasks and signatures, build test-first, then B.
