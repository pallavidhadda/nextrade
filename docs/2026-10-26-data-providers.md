# Data provider evaluation (2026-10-26; from the providers' own pages and one data download; terms not legally reviewed)

| | TejHQ (tejhq.dev) | Stoxim (stoxim.com) | TigZig (api.tigzig.com) |
|---|---|---|---|
| Gives | EOD prices, adjusted prices, corporate actions (dividend, split, bonus, rights, buyback, demerger, merger), symbol history by ISIN, monthly top-500 liquidity universe (survivorship-bias-free), rolling returns/52w metrics | XBRL-parsed financials (P&L, balance sheet, cash flow, 40+ lines), ratios incl. EV/EBITDA and ROCE, shareholding, governance, announcements; keyed by ISIN | India macro (RBI etc.), Vigil BRSR/ESG red-flag data, MF NAV (AMFI), SIF, misc. No equity fundamentals or prices described |
| Access | Hugging Face parquet, no auth; REST keyless for prices/actions; some endpoints need a free key; universe/metrics/screener API = Pro | API key header; free 500 requests/day | No auth; limits per IP, read from headers |
| Licence/terms | Dataset tag MIT; card says source data public/redistributable, "verify exchange terms before commercial use"; Retail plan is "one person's own trading" | Not stated on page | "As is"; CC0 NOT stated on the page (only ODC-BY for the cricket data); per-API terms unread |
| Coverage caveats | EOD only; no fundamentals (listed as planned), no industry, no filing dates; demergers/mergers not price-adjusted | Page says both "20+ NSE companies, 3 yrs" and "every Indian company": must test; no point-in-time statement | Equity data not covered |
| Verified by me | YES, by downloading: symbol_history, actions_2025/26, universe parquet | NO (needs a key; I cannot sign up) | Page read only |

## Verified facts from the TejHQ download (2026-10-26)
- ZOMATO (ISIN INE758T01015) valid 2021-07-23 to 2025-04-08; ETERNAL, same ISIN, from 2025-04-09: matches NSE's symbolchange.csv.
- TATAMOTORS ISIN INE155A01022 until 2025-10-23; TMPV keeps INE155A01022 from 2025-10-24; TMCV new ISIN INE1TAE01010 from 2025-11-12.
- Actions: TMPV demerger ex_date 2025-10-14 (no ratio given); 28 demergers in 2025-26 files; types: dividend 3345, split 105, bonus 89, rights 86, buyback 41, demerger 28.
- Universe: top 500 by 63-day turnover, rebalanced monthly 2010-05 to 2026-10-01 (97,500 rows); RELIANCE rank 2; no industry column.
- RELIANCE ISIN INE002A01018 matches the NSE results filing.
- Correction made: price-return flags for demergers must use the ex-date (2025-10-14), not the legal effective date (2025-10-01).

## Decisions proposed
1. Adopt TejHQ parquet for identity (ISIN, symbol history), corporate action dates (ex-dates), and the pool/universe (top-500 point-in-time). Keep NSE symbolchange.csv as a cross-check. Attribute TejHQ; keep the redistribution/commercial caveat.
2. Test Stoxim with a free key on our pool before relying on it: compare Reliance Q1 FY27 net profit (Rs 20,946 cr), revenue, shareholding vs the NSE filing and Yahoo; check coverage count, history depth, filing-date fields.
3. TigZig: later, for RBI macro (replaces FRED) and red flags; read per-API licence first.
4. Industry classification is still missing: needs NSE index CSV (industry column) or Stoxim company master (sector).
