# India fundamentals layer — design, dev spec, roadmap (DRAFT for approval)

Status: draft, nothing built. Educational/research tool only; not financial, investment or trading advice.

## 1. Why
The RELIANCE.NS baseline produced a fundamentals report with no numbers. Root cause (verified in code, correcting my earlier explanation): `withhold_undated_statements` (tradingagents/dataflows/date_window.py) withholds Yahoo statements for ANY run dated before today, for any country, because Yahoo dates statements by period end, not filing date. I ran 2026-10-23 on 2026-10-25, so it fired. It was not India-specific. A run dated today does get data.
That exposes the real problem: Yahoo cannot support dated history, and Yahoo India coverage is patchy. Probe on 2026-10-25 (periods returned): RELIANCE.NS quarterly income 5 / balance sheet 3; TCS.NS 5/6; INFY.NS 6/6; ITC.NS 5/2; HDFCBANK.NS (bank) 2/4, no quarterly cash flow; TATAMOTORS.NS and ZOMATO.NS returned nothing (possibly renamed/demerged tickers — unverified).

## 2. Goals / non-goals / anti-goals
Goals: usable, dated, labelled India fundamentals for NSE/BSE tickers; explicit "no data" instead of filler; compact output (~600 tokens digest per ticker); free to run; deterministic (no LLM) computation of ratios.
Non-goals: real-time data, trading/execution, advice to third parties, paid-data redistribution.
Anti-goals: a report that reads confidently while data is missing; scraping a site whose terms forbid it in a public repo; silently mixing consolidated and standalone figures.

## 3. Source options (evidence is thin; secondary sources unless stated)
| Source | Status | Verdict |
|---|---|---|
| Yahoo via yfinance | Works today, free, patchy, consolidated-ish, no filing dates (verified by probe) | Tier 1 for prototype |
| NSE "Integrated Filing - Financial" XBRL / BSE filings | Official and dated; NSE circular says XBRL mandatory, PDF-only discontinued from 1 Apr 2025. I found no documented public API; a listing said some NSE endpoints are no longer publicly accessible | Tier 2: spike to test; use for filing dates and cross-checks |
| Screener.in | Terms (2018) allow personal, non-commercial viewing; prohibited-activities list not read | Do NOT scrape. Maybe accept a user's own export file. Read full terms first |
| dalal / BharatStock / others | dalal: free, 3-period financials (listing claim); BharatStock: keyed, price unknown | Evaluate in spike; unofficial endpoints can break |
| EODHD / FMP | India coverage and free limits NOT verified | Check pricing pages before considering |

## 4. Point-in-time approach (my call)
Each period gets `available_from = period_end + lag`, lag from SEBI LODR Reg 33 deadlines as reported by secondary sources: 45 days for Q1–Q3, 60 days for year-end (verify against current LODR text). Use deadline as a CONSERVATIVE availability date (a company may file earlier, never later without breach). Where a real filing date is found (Tier 2) it overrides. Output states "availability approximated" so users know. Periods with `available_from` after the run date are dropped, not withheld wholesale.

## 5. Dev spec
Module `india_fundamentals` (new vendor beside yahoo in tradingagents/dataflows/vendors; registered in router.py for tickers ending .NS/.BO).
- `fetch_statements(ticker, as_of) -> StatementSet` (periods, line items, currency INR, basis consolidated|standalone|unknown, source, fetched_at).
- `apply_availability(StatementSet, as_of) -> StatementSet` (section 4).
- `compute_metrics(StatementSet) -> Metrics` deterministic: revenue/PAT growth YoY, margins, ROE/ROCE where inputs exist, debt/equity, interest cover, FCF; each metric lists input fields + period, or `null` with reason.
- `cross_check(a, b)`: revenue, net income within 15% else warning (FinRobot validator pattern; skip fields with differing definitions).
- `digest(Metrics, warnings) -> str` <= 600 tokens: table of numbers with period + source, coverage line, warnings, and the line "No data for: ...".
- Sector handling: banks/NBFC flagged `sector_model=financial`; skip EBITDA/EV metrics, show NII, NIM only if present.
- Ticker normalisation reuse `symbols.normalize_symbol`; renamed/delisted tickers return `unavailable` with reason.
- Config: `TRADINGAGENTS_INDIA_FUNDAMENTALS=yahoo,exchange` order; failover per source.
- Every output ends with the not-advice disclaimer.

## 6. Roadmap (full-stack product plan, each step gated by tests in the test plan)
M0 Spike (1–2 days): probe NSE/BSE filing access, dalal, Yahoo gaps across ~30 Nifty names; decide Tier 2. Throwaway code.
M1 Data layer + digest CLI (sections 4–5), RELIANCE.NS replay passes.
M2 Deterministic score + hard risk limits (ai-hedge-fund pattern), scorecard logging.
M3 One cached JSON LLM call per lens; token budget enforced in tests; Gemini free-tier throttle built in.
M4 Claude Code plugin (/analyze) over the same core.
M5 Web front end + public repo: thin FastAPI over the core, simple web UI (stack to be chosen with you), disclaimer on every page, no keys stored server-side (bring-your-own-key in browser or local).
M6 Backtest + public scorecard page.

## 7. Calls I made (check these)
Yahoo as Tier 1; deadline-based availability; 600-token digest; no Screener scraping; FastAPI + thin UI for M5; new vendor instead of patching Yahoo guard.

## 8. Open questions for you
1. Front-end stack preference (React/Next.js vs simple server-rendered)?
2. Open-source licence for your public repo (MIT?), given reused code must be licence-compatible.
3. Willing to pay for a data API if free sources fail the M0 spike? Budget?
4. Consolidated or standalone as default for Indian companies? (I suggest consolidated, labelled.)
