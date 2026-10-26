# Price-signal scorecard (backtest v1) — spec and test cases
Research/education only; not financial, investment or trading advice. A historical test of simple price signals is NOT evidence that any score predicts future returns.

## Intent
Answer one question honestly: did cheap, rule-fixed price signals rank NSE stocks' next-period returns better than chance, after costs, against an equal-weight benchmark of the same point-in-time universe? Fundamentals history is too thin (about 5 quarters), so v1 is price-only.

## Data
TejHQ `prices_adjusted/nse_YYYY.parquet` (`adj_close` includes splits, bonuses, dividends; demergers/mergers not scaled), TejHQ `universe/nse_liquid.parquet` (monthly top-500 by liquidity, survivorship-bias-free). Cached under `~/.indiafacts/tej`. Attribute TejHQ; verify exchange terms before commercial use.

## Method (fixed before looking at results)
- Rebalance every `horizon` trading days (default 21). At each date t, eligible = universe members at t with a valid signal and a price at t.
- Signals use data up to and including t only: `mom_12_1` (price t-21 / price t-252 - 1), `low_vol` (minus std of daily returns over 252 days), `near_high` (price / 252-day max - 1), `composite` (mean of the three cross-sectional rank percentiles).
- Forward return = adj_close(t+h)/adj_close(t) - 1. A name with no price at t+h (delisted/suspended) takes its last available price before t+h and is counted in `carried`; never silently dropped.
- Buckets: quintiles by signal; Q5 = best. Metrics per signal: mean forward return per bucket, spread Q5-Q1, rank IC (Spearman) mean and its t-statistic, share of periods with Q5 > universe mean, net long-Q5 excess over the equal-weight universe after cost (replaced share of the Q5 set x 2 x `cost_bps`, default 30 bps one-way; an ASSUMPTION, shown), sub-period split (first half / second half).
- No parameters are tuned on the results. Four signals tested = multiple comparisons; the report says so.

## Reported caveats (always printed)
In-sample history; overlapping-free but single path; costs are assumptions; no taxes, impact or liquidity limits; carried returns for delisted names; demerger/merger not adjusted; benchmark is equal-weight universe, not an index; past results do not predict future ones.

## Tests
B1 `mom_12_1` on a synthetic panel equals hand-computed value; B2 signals at t never read prices after t (changing future prices does not change signal at t); B3 forward return matches hand value; B4 delisted name: carried return used, `carried` counts it; B5 quintile assignment sizes (n=10 -> 2 each; n<quantiles -> period skipped, counted); B6 perfectly predictive synthetic signal gives IC ~ 1, Q5-Q1 spread > 0, positive net excess; B7 random-noise signal gives |IC| small and Q5-Q1 spread not significant (seeded); B8 cost: zero turnover costs nothing, full turnover costs 2 x cost_bps x ... as stated; B9 universe membership is point-in-time (a symbol joining later is excluded earlier); B10 sub-period split sums to full; B11 caveats and disclaimer present in rendered output; B12 no key/secret in output; B13 (not built) CLI test on a fake store; entry point is `python -m indiafacts.backtest`. Built tests: B1-B12 in `tests/test_backtest.py`. Spearman IC is computed as Pearson on ranks (no scipy).
