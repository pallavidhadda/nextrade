# Backtest v1 result (price signals, TejHQ data) — 2026-10-26
Run: `python -m indiafacts.backtest --from-year 2016` (about 2.5 min with a warm cache). Data: TejHQ prices_adjusted + monthly top-500 universe (attribution: TejHQ; terms to verify before commercial use).

```
PRICE-SIGNAL SCORECARD (history only)
Window 2016-01-11 to 2026-09-10; 126 rebalances of 21 trading days (0 skipped for too few names); universe 470-500 names; carried returns: 284; one-way cost assumption 30 bps.
Excess = top-quintile mean minus equal-weight universe mean, per period. IC = rank correlation of signal and next-period return.

signal          IC   IC t    Q5-Q1   hit    gross      net  turn  halves (net)
mom_12_1     0.048    3.4   +1.64%   61%   +0.76%   +0.60%  0.27  +0.53% / +0.68%
low_vol      0.055    2.8   +0.17%   44%   -0.17%   -0.23%  0.10  +0.07% / -0.53%
near_high    0.048    3.0   +1.11%   59%   +0.47%   +0.18%  0.48  +0.21% / +0.15%
composite    0.070    3.9   +1.26%   55%   +0.43%   +0.28%  0.26  +0.49% / +0.07%

Caveats:
- In-sample history, a single path; nothing here was tuned on the results.
- Four signals were tested, so some apparent edge can appear by chance (multiple comparisons).
- Costs are an assumption (round trip on the replaced share of the top bucket); no taxes, market impact or liquidity limits.
- A name that stopped trading before the period ended keeps its last available price (carried), which can flatter or hurt results.
- Adjusted prices include splits, bonuses and dividends; a demerger or merger is not scaled, so such names can mislead.
- The benchmark is the equal-weight average of the same universe, not an index; symbols are matched by name, so renamed companies split into two series.

Not financial, investment or trading advice. A historical test of simple price signals is not evidence that any score predicts future returns.
```

## Reading it honestly
- All four signals had a small positive rank IC (0.05-0.07) with t-statistics 2.8-3.9 over 126 monthly samples. With four signals tested and a single in-sample path, treat this as a hint, not proof.
- `mom_12_1` was positive in both halves after the assumed cost (+0.53% / +0.68% per month versus the equal-weight universe). `low_vol` was not (negative second half, hit rate 44%). `composite` faded in the second half (+0.49% / +0.07%).
- The costs are an assumption and ignore tax, impact and liquidity limits; carried returns (284 name-periods) and unscaled demergers remain open issues.
- Nothing here has been tested out of sample, and nothing here supports a claim that the project's scores predict returns. The pool score itself (which also uses fundamentals) is NOT what was tested.
