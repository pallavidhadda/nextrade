# Priorities by MoSCoW (2026-11-02; updated 2026-11-16)
Research/education only; not financial, investment or trading advice. Goal: an improved, token-cheap, factual version of TradingAgents for Indian stocks that works on free model tiers.
"Needs you" marks items blocked on an account, key, file, logs or a lawyer; I cannot finish those alone.

## Must have (the product is untrustworthy or unusable without these)
| # | Item | Status | Needs you |
|---|---|---|---|
| M1 | A chat result must not vanish when the free server restarts (auto-restart a lost job) | DONE 2026-11-02: `get_analysis` takes the ticker and restarts a lost job; tested offline, not yet seen on the live server | no |
| M2 | Self review of the API, connector, runner and web code for security and correctness; fix findings | DONE 2026-11-02: server runs no longer remember anything, secrets and tokens are stripped from the child, hung children are killed, caches are bounded, XBRL size cap. A review by someone else is still missing | no |
| M3 | Like-for-like token and quality measurement against TradingAgents on the same ticker, date and free Gemini model | DONE: tokens in `docs/TOKEN_COMPARISON.md`; quality head-to-head on 29 of 30 tickers in `docs/HEAD_TO_HEAD_2026-11-06.md` (M&M cannot run in TradingAgents). Outcome accuracy: both systems' 58 ratings recorded; settle on or after 8 Dec 2026 with `headtohead/report.py --date 2026-11-06 --settle` | no (a date) |
| M4 | Find why the free Render server restarts | logging added; needs the Render logs | yes |
| M5 | Securities-lawyer answers to the five questions before any public launch | owner decision 2026-11-07: research/education project, legal review deferred; disclaimers stay on every surface | no |
| M6 | Docs and README claims match what is built and measured | ongoing | no |

## Should have (high value, not blocking)
| # | Item | Status | Needs you |
|---|---|---|---|
| S1 | Claim checker: verify a claim such as "TCS EPS was 142.66" against the facts, with sources | DONE 2026-11-02: `python -m indiafacts.claims` and the connector tool `check_claim` | no |
| S2 | Annual year figures and growth | DONE 2026-11-07 via Yahoo annual statements, verified against official FY24 XBRL (net profit and operating cash flow exact, revenue 1.5% apart); official pages still welcome | no |
| S3 | EV/EBITDA versus peers | DONE 2026-11-07 (peer median table and score) | no |
| S4 | Free cash flow | DONE 2026-11-07 (FCF, margin, yield in Business health, rating points) | no |
| S5 | Marketaux per-ticker sentiment trial (5 Indian tickers) | needs a free key | yes |
| S6 | Deploy the Next.js app | live on Vercel; Streamlit app removed 2026-11-10 (the Vercel app replaces it) | no |

## Could have (nice, later)
C1 Reddit mention counts, Market Mood Index, Google Trends. C2 Tune rating thresholds from settled outcomes (needs weeks of decisions). C3 Persistent report storage (Supabase or R2; needs credentials). C4 Precomputed comparison-pool snapshot for speed. C5 Holdings input kept in the browser. C6 Thesis notes and journal views.

## Won't have (for now, on purpose)
W1 Order placement, broker links, accounts and logins (regulatory and security surface). W2 Multi-round language-model debates (cost; rules plus one narration call do the job). W3 A TradingAgents adapter (owner decision: standalone). W4 Full forecast DCF with a fair-value target (assumption-driven; we show what the price implies and reference levels).

## Added 2026-11-07
Business-health block and lender metric set; NSE RSS announcements; journal `log` / `export` / `import` and a weekday GitHub Action; company-name search, At a glance strip and plainer progress in the web app; rating no longer inflated by trivial checks. Open: bank NIM and NPA, shareholding pattern and FII/DII, Marketaux sentiment, real-user tests, a quality comparison with TradingAgents.

## Added 2026-11-07 (later)
Official shareholding pattern (files, NSE feed, accumulating store, 4-hourly workflow) and market-wide FII/DII/Pro/Client index-futures positioning: DONE. Not possible for free: cash-market FII/DII net flows (cookie-protected NSE API) and per-stock FII flow. Open: bank NIM and NPA.

## Added 2026-11-16
Done: NSE archive links moved to `nsearchives.nseindia.in` and every official results and shareholding download had been refused; fixed. Bank NPA (gross and net), CET1 and net interest income to assets from the official filing; lenders get a bad-loans check instead of debt-to-equity and interest cover. Head-to-head finished (29 of 30) and the four Buys re-checked inside their sector (AXISBANK falls to Overweight). Vague AI wording ("strong growth" with no figure) is rejected. Backtest joins renamed companies by ISIN and compares with the Nifty 50. NSE filing copies older than 10 days are ignored and orphaned copies pruned. One test covers every parameter file's review date. Web app: glossary tips, companies saved in the browser, a one-time reading guide, wide tables scroll on phones.

Still open and needs you or time: M4 Render restart logs; S5 Marketaux key; live test of the Anthropic and OpenAI adapters (keys); five sessions with real users; settlement on 8 Dec 2026; an outside code review. Job state on disk was considered and dropped: Render's free disk is wiped on every restart, so it would not keep a job; the existing auto-restart (M1) is the fix that works there. Still open in code but blocked on data: returns for delisted names, the Nifty 50 total-return series, and a backtest of the full score (needs a fundamentals history).
