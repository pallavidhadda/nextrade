# Priorities by MoSCoW (2026-11-02)
Research/education only; not financial, investment or trading advice. Goal: an improved, token-cheap, factual version of TradingAgents for Indian stocks that works on free model tiers.
"Needs you" marks items blocked on an account, key, file, logs or a lawyer; I cannot finish those alone.

## Must have (the product is untrustworthy or unusable without these)
| # | Item | Status | Needs you |
|---|---|---|---|
| M1 | A chat result must not vanish when the free server restarts (auto-restart a lost job) | doing now | no |
| M2 | Self review of the API, connector, runner and web code for security and correctness; fix findings | doing now | no |
| M3 | Like-for-like token and quality measurement against TradingAgents on the same ticker, date and free Gemini model | doing now | no (key already in TradingAgents/.env) |
| M4 | Find why the free Render server restarts | logging added; needs the Render logs | yes |
| M5 | Securities-lawyer answers to the five questions before any public launch | questions written | yes |
| M6 | Docs and README claims match what is built and measured | ongoing | no |

## Should have (high value, not blocking)
| # | Item | Status | Needs you |
|---|---|---|---|
| S1 | Claim checker: verify a claim such as "TCS EPS was 142.66" against the facts, with sources | doing now | no |
| S2 | Official annual and quarterly NSE pages (confirms year figures, fixes growth) | parser ready | yes: save the FY2025-26 and FY2024-25 pages |
| S3 | EV/EBITDA versus peers | after S2 data | partly |
| S4 | Free cash flow in the valuation | blocked on S2 confirming year-to-date values | yes (via S2) |
| S5 | Marketaux per-ticker sentiment trial (5 Indian tickers) | needs a free key | yes |
| S6 | Deploy the Streamlit app and the Next.js app | guides written | yes: accounts |

## Could have (nice, later)
C1 Reddit mention counts, Market Mood Index, Google Trends. C2 Tune rating thresholds from settled outcomes (needs weeks of decisions). C3 Persistent report storage (Supabase or R2; needs credentials). C4 Precomputed comparison-pool snapshot for speed. C5 Holdings input kept in the browser. C6 Thesis notes and journal views.

## Won't have (for now, on purpose)
W1 Order placement, broker links, accounts and logins (regulatory and security surface). W2 Multi-round language-model debates (cost; rules plus one narration call do the job). W3 A TradingAgents adapter (owner decision: standalone). W4 Full forecast DCF with a fair-value target (assumption-driven; we show what the price implies and reference levels).
