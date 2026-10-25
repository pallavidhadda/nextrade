# Research agenda (4 priorities) + experienced-investor result screen — DRAFT
Research/education only; not financial, investment or trading advice. Nothing built yet.

## Priority 1 findings so far: how TradingAgents handles RELIANCE.NS (read from code + live call, 2026-10-25)
| Question | What the app does | Gap |
|---|---|---|
| Symbol -> identifier | `normalize_symbol` is purely syntactic; `.NS` passes through unchanged (symbols.py). No ISIN, NSE symbol, BSE scrip code or CIN anywhere | No entity identity; renamed/demerged tickers (TATAMOTORS.NS, ZOMATO.NS returned empty) cannot be resolved or flagged |
| Statements | yfinance CSV, columns = period-end dates, raw numbers | No unit/currency line on statements; no period-type tag (Q vs FY vs TTM); no consolidated/standalone tag |
| Periods | Live call returned quarters Jun-26, Mar-26, Dec-25, Jun-25, Mar-25: **Sep-25 silently missing** | Gap not flagged, so a TTM sum from the table would be wrong without anyone noticing |
| Currency | Overview labels INR on money fields; D/E converted (46.278% = 0.46x) | Statement CSVs unlabeled; no check that statement currency = quote currency |
| Missing values | Overview omits None fields (ROE, ROA, current ratio, FCF absent from output); empty statement raises | Absence is silent, never "unavailable: reason" |
| Filing dates | Yahoo has none; SEC EDGAR path carries filed-date per fact but is US-only (non-filers raise NoMarketDataError and fall through) | EDGAR is the model to copy; no India equivalent found yet |
| Internal consistency | P/E 21.55 x EPS 55.22 = 1190.0 matches price: good. Yahoo 50/200-day averages (1243.42/1327.73) differ from the indicator tool (1250.00/1335.36): different as-of dates/definitions, unreconciled | Two sources for one number with no provenance note |

### Target data model (every reported number is a Fact)
fact_id, entity (ISIN, NSE symbol, BSE code, name), metric, value, unit, currency, period_start, period_end, period_type (Q|H|FY|TTM|point), basis (consolidated|standalone|unknown), source, source_field, retrieved_at, available_from + availability_kind (filed|deadline_estimate), status (ok|unavailable|stale|conflict), reason.
Success: every number in any output resolves to a fact_id with a period, or prints "unavailable: <reason>". Test: property test that no output number lacks a fact_id.

## Priority 2 — Screening and factor scoring (to study; success criteria)
Study: filter representation, metric normalisation (winsorise, z-score vs percentile, sector-relative), missing-data policy, ranking. Reproducible scores, explicit weights in a versioned file, tests that perturb inputs (inject a bad value, a missing value, a unit error) and assert ranking changes are caught/flagged. Known so far: ai-hedge-fund blends conviction with explicit model weights in YAML (read); nothing on normalisation yet.

## Priority 3 — Theses and evidence linking
Each claim typed Fact | Inference | Hypothesis, linked to fact_ids; conflicting sources shown side by side with the spread; every thesis lists invalidation conditions with numeric triggers. FinRobot's NumericClaim/Finding ledger (read) is the closest reference; TradingAgents debates carry no evidence links.

## Priority 4 — Signal tracking and backtesting (assumptions to record)
Timestamp alignment (signal on close vs next open), availability dates for fundamentals (P1), corporate actions (splits/bonus/demergers, adjusted vs unadjusted prices), Indian transaction costs (brokerage, STT, GST, stamp duty, slippage; rates to be sourced and dated), benchmark = Nifty 50 / TRI, out-of-sample split fixed before looking, multiple-testing caution. Result is always labelled with assumptions; a persuasive report is not evidence of a profitable strategy. Not yet inspected: TradingAgents backtest module, ai-hedge-fund backtesting.

## Experienced-investor result screen: RELIANCE.NS (values from 25 Oct 2026 Yahoo fetch; `unav` = unavailable)
```
RELIANCE INDUSTRIES  NSE:RELIANCE  ISIN unav  | ₹1,190.00 (23 Oct) | Mcap ₹16.10 lakh cr | basis: unknown (Yahoo)
DATA QUALITY: 3 conflicts/gaps  [Sep-25 quarter missing] [basis unlabeled] [ROE, FCF unav]
---------------------------------------------------------------------------------------------
VALUATION (source, as-of)                          TTM-verified?
 P/E 21.55  Fwd P/E 16.75  P/B 1.78  PEG 0.82      P/E x EPS = price: OK
 EPS TTM ₹55.22 (Yahoo)  vs sum of last 4 qtrs: cannot verify (Sep-25 qtr missing)
QUARTERLY (₹ crore, Yahoo, period end)      Jun-26   Mar-26  Dec-25  Sep-25  Jun-25
 Net income                                 20,946   16,971  18,645   unav   26,994
 EBITDA                                     38,967   33,780  36,310   unav   44,182
 Interest expense                            8,337    6,585   6,613   unav    7,036
 Diluted EPS (₹)                             15.48    12.54   13.78   unav    19.95
 YoY PAT Jun-26 vs Jun-25: -22.4% headline; base qtr holds ₹8,924 cr unusual item
 (Yahoo field, pre-tax, no tax effect applied): adjusted comparison needs verification.
 Interest expense YoY +18.5% (Jun-26 vs Jun-25).
TECHNICAL (calc from OHLCV, 23 Oct): RSI 44.35 | SMA50 1250.00 | SMA200 1335.36 | ATR 26.00
 note: Yahoo's own SMA50/200 (1243.42/1327.73) differ: definitions/as-of unreconciled
FACTOR SCORES: not built. weights file: unav. peers/Nifty 50 relative: unav
THESIS LEDGER
 H1 (hypothesis) Downtrend persists below SMA200. Evidence: F-price, F-sma200.
    Invalidates if: close > 1,250 (SMA50) for 3 sessions.
 F1 (fact) Interest expense up 18.5% YoY. Evidence: F-int-jun26, F-int-jun25.
 I1 (inference) Earnings quality unclear; needs segment data (O2C/Retail/Jio): unav.
BACKTEST / TRACK RECORD: none run. No claim of edge.
```
