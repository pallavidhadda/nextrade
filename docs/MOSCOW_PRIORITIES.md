# Priorities by MoSCoW (2026-11-02)
Research/education only; not financial, investment or trading advice. Goal: an improved, token-cheap, factual version of TradingAgents for Indian stocks that works on free model tiers.
"Needs you" marks items blocked on an account, key, file, logs or a lawyer; I cannot finish those alone.

## Must have (the product is untrustworthy or unusable without these)
| # | Item | Status | Needs you |
|---|---|---|---|
| M1 | A chat result must not vanish when the free server restarts (auto-restart a lost job) | DONE 2026-11-02: `get_analysis` takes the ticker and restarts a lost job; tested offline, not yet seen on the live server | no |
| M2 | Self review of the API, connector, runner and web code for security and correctness; fix findings | DONE 2026-11-02: server runs no longer remember anything, secrets and tokens are stripped from the child, hung children are killed, caches are bounded, XBRL size cap. A review by someone else is still missing | no |
| M3 | Like-for-like token and quality measurement against TradingAgents on the same ticker, date and free Gemini model | DONE for tokens: `docs/TOKEN_COMPARISON.md` (43,025 vs 2,296 tokens, 16 vs 1 calls). Quality comparison still open | no |
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
