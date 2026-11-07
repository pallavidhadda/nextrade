# Quality, analyst and UX review (2026-11-07)
Research/education only; not financial, investment or trading advice. Reviewed as a small team: product manager, investment analyst, UX designer, developer.

## 1. Where official NSE data comes from, for free
| Source | Use | Status |
|---|---|---|
| Pages and XBRL files you save from nseindia.com | Official quarter and year figures | works; parser exists. Your two Reliance Q4 FY24 XBRL files (standalone and consolidated) load, and are now **cross-checked against Yahoo's annual figures** |
| NSE public RSS feed on `nsearchives.nseindia.com/content/RSS/Online_announcements.xml` | What a company filed in the last day or two, with PDF links | **new**: `--announcements`, module `indiafacts/nsefeed.py`. Plain HTTP, no cookies, soft failure |
| Yahoo annual income statement, balance sheet, cash flow (4-5 years) | Year figures, free cash flow, net debt, EV/EBITDA, ROCE | **new**: `indiafacts/fundamentals.py` |
| NSE website JSON APIs | per-company results history | **not used**: they need a browser-style session (cookie warm-up). That is bot-check circumvention and not allowed here. If you want it, use the manual save route above |
| BSE API | same | returns 403 to scripts; not used |

Bottom line: there is no free, supported, per-company results feed from NSE. The honest free stack is Yahoo annual statements for depth, NSE RSS for freshness, and saved official files for verification.

## 2. Analyst findings and what changed
Cross-check on Reliance FY24 (official consolidated XBRL against Yahoo annual): net profit identical, operating cash flow identical, revenue 1.5% apart, interest expense 5.8% apart (flagged as a conflict, not hidden). So Yahoo's annual statements are usable, with the interest line the weakest.

| # | Finding | Fix |
|---|---|---|
| A1 | Only about 5 quarters; year growth was unavailable because Yahoo is missing the Sep-2025 quarter | Annual statements added; checklist falls back to last-financial-year growth and says so; growth factor can be carried by 3-year averages |
| A2 | No free cash flow, net debt, EV/EBITDA, ROCE, promoter proxy | New **Business health** block in terminal, HTML, JSON, Streamlit and Next.js; ratios are computed from facts with source rows |
| A3 | Lenders got non-comparable metrics | Banks and NBFCs get their own set (ROE, ROA, P/B, leverage); EBITDA, EV, cash flow marked not applicable; NIM and gross NPA stated as unavailable in free data, never invented |
| A4 | Score ignored the new evidence | EV/EBITDA, FCF yield, ROCE, net debt/EBITDA and 3-year growth join the score as **optional** metrics (absence never lowers coverage); EV/EBITDA and ROCE added to peer medians |
| A5 | Rating inflated by trivial checks ("profit is positive", "EPS is positive" counted as two bull points) | Trivial checks no longer count as points; few points can no longer swing the rating to an extreme. TCS moved from Overweight to Hold on the same data |
| A6 | Promoter holding | Yahoo "insiders" shown as an unverified proxy with a note to confirm in the exchange shareholding pattern |

Still open for the analyst: official shareholding pattern, FII/DII flows, pledging, concall text, NIM and NPA for lenders (all need saved official files or a licensed source), and a quality comparison against TradingAgents output.

## 3. UX review (user flow)
Walked through: land, enter company, wait, read the summary.
| # | Problem | Fix |
|---|---|---|
| U1 | You had to know the ticker | Search box accepts a company name or ticker (Nifty 500 list shipped with the app) |
| U2 | The first screen of results was a 0-100 pool score. A beginner's question is "so, is this OK?" | New **At a glance** strip: rating and confidence, score, checks passed, gaps, then three reasons for and three against |
| U3 | Waiting screen said "step [4/30] BAJFINANCE.NS" and echoed what was typed | Plain progress ("4 of 30 done, the first run is slowest") and the resolved ticker |
| U4 | Header showed only the ticker | Company name shown |
| U5 | Business quality was missing from the summary | Health card placed right after the score and rating |
Still open: a mobile pass with real devices, a glossary tooltip on terms such as ROCE, saving a favourite list in the browser, and a first-run walkthrough. Not tested with real users yet: do five sessions before trusting any of this.
