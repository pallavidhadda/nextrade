# Valuation depth: research, methods side by side (2026-10-31)
Research/education only; not financial, investment or trading advice. This is a design proposal; nothing here is built yet.

## Principle
Show what a price implies and how sensitive that is, never a "fair value" or target. "At today's price the market is pricing roughly X% growth for N years under these assumptions" is a fact about arithmetic; "the stock is worth Y" is an opinion and sits closer to regulated research (see LEGAL_WORDING_REVIEW.md). All maths in code; the model only narrates.

## What others do (from our source reading)
- FinRobot: 32 code operators (DCF, DDM, LBO, WACC, comps, Monte Carlo, SOTP), each number a claim with provenance; bad inputs withhold that figure, not the whole report. Produces price targets (we will not).
- ai-hedge-fund: persona prompts over fundamentals; valuation is mostly LLM judgement on a data snapshot (weak, unauditable).
- OpenBB: data and quantitative extensions, no opinionated valuation.
- Screener-style sites: peer and historical multiples, long history (which we lack).
- Sources on method (blogs and vendor pages, not primary): reverse DCF solves for the growth that makes a DCF equal today's price, is sensitive to the discount rate, and is meaningless without positive cash flow; justified P/B for banks is about ROE divided by cost of equity (or (ROE - g) / (r - g)); P/B and EV/EBITDA suit asset-heavy sectors, ROE and P/E suit asset-light ones. Michael Mauboussin's Expectations Investing is the professional version of reverse DCF (not read by me).

## Methods side by side
| Method | Answers | Inputs we have today | Missing | Fit for | Risk of misleading | Build size | Show as |
|---|---|---|---|---|---|---|---|
| Relative multiples vs peers (P/E, P/B, margin) | Cheaper or dearer than peers? | Yes (built; peer group tiers, median) | EV/EBITDA needs net debt | all, but small groups are weak | High if peers differ; we show group size | Done | Table with peer count and caveat |
| Own-history multiple range | Cheap or dear vs its own past? | Price history yes; EPS history only about 5 quarters | Multi-year EPS (official filings) | stable earners | Medium | M, blocked on data | Percentile band, only with 3+ years |
| Reverse DCF on earnings or FCF | What growth does the price imply? | Price, market cap, net income, EPS | Free cash flow, share count history | non-financials with positive cash flow | Medium: sensitive to discount rate and fade | M | Grid: implied growth by discount rate (rows) and years (columns) |
| Justified P/B from ROE | What P/B does the ROE support? | P/B yes; ROE often "not provided by Yahoo" | ROE from filings, cost of equity assumption | banks, NBFCs, insurers | Medium: book quality (bad loans) | S once ROE exists | Range of justified P/B vs actual, with ROE and r shown |
| Dividend discount | Value of the dividend stream | dividend yield partly | payout history | mature payers | High for low payers | M | Only if dividends exist |
| Full DCF with forecasts | Intrinsic value | no | forecasts, margins, capex | analysts | Very high: assumptions dominate | L | Not planned (becomes a target price) |
| Monte Carlo / scenarios | Spread of outcomes | no | assumption distributions | sensitivity | High: false precision | M | Only as sensitivity grid |
| Sum of the parts | Conglomerate segment value | Reliance segments parsed from NSE page | segment multiples | Reliance-type groups | High | L | Later, for segment-rich filings |

## Recommended order
1. **Sector-aware method selector** (S): decide per company which methods apply (banks: P/B and ROE, no EV/EBITDA; asset-light: P/E and ROE; asset-heavy: P/B and EV/EBITDA). Show "not applicable" with the reason, in line with our gap culture.
2. **Reverse DCF on earnings** (M): solve implied growth with a two-stage fade (explicit years, then terminal growth capped by an assumption such as long-run nominal growth). Output a sensitivity grid across discount rates, never a single number. Withhold when earnings are negative or inputs are unverified. Tests: known closed-form cases (a growing perpetuity), monotonic in price, no result with negative cash flow, grid labelled as assumptions with `review_by`.
3. **Justified P/B for financials** (S after ROE exists): range from ROE and a cost-of-equity band.
4. **EV/EBITDA vs peers** once net debt and the EBITDA-is-EBIT guard are wired (M).
5. **Own-history percentile bands** after multi-year filings land (rank 1 and 5 in PRODUCT_REVIEW).
6. Skip full DCF and price targets.

## Data dependency
Rank 1 (official filings) unlocks free cash flow, ROE, multi-year EPS and cleaner EBITDA. Until then, only relative multiples and a reverse DCF on trailing earnings are honest.

## Guardrails
Every assumption (discount rate band, fade years, terminal growth) is a config entry with `reviewed_on` and `review_by`, shown beside the output. A claim like "the price implies about 14% a year for 10 years at a 12% discount rate" is a fact about the model; the narrative must not say whether that is achievable.
