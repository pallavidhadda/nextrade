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

## 4. Shareholding pattern and FII/DII (added later the same day)
| What | Source | How it works | Honest limit |
|---|---|---|---|
| Official shareholding pattern: promoter, pledged share of promoter holding, foreign institutions, domestic institutions, mutual funds, public, small retail, change since the previous filing | NSE shareholding-pattern XBRL | `--shareholding FILE`, or `SHP_*.xml` in your filings folder, or found automatically in NSE's public RSS feed `Shareholding_Pattern.xml` | The feed lists only the newest filings, so a company is found only shortly after it files. Every snapshot seen is stored (`~/.indiafacts/shareholding.csv`, and the repo's `data/shareholding.csv` via the `shareholding` workflow, every 4 hours), so quarter-on-quarter history builds up from now. Yahoo's holder lists are empty for India |
| FII, DII, Pro and Client index-futures positioning, 6-session trend | NSE daily participant-wise open interest file | `--flows` (always on in the web app); cached per day | Whole-market derivatives positioning, **not** one stock's flows and **not** the cash-market FII/DII net buy/sell figure. That number sits behind NSE's cookie-protected API, which this project does not use. Shown as context only and never fed into a rating |

Rating: official data only can add bear points (promoter pledge of 25% or more of their shares; promoter holding down 2 points or more). Yahoo's proxy never creates a point and is labelled as a vendor estimate, with instructions for getting the official file.
Checked live: the poll stored 5 real filings; ONEPOINT shows promoter 52.3%, 39.4% of promoter shares pledged (flagged high), FPI 5.1%.

## 5. Cash-market FII/DII importer, smart search, Streamlit fix (later the same day)
- **Cash-market FII/FPI and DII (rupees crore):** NSE publishes this only on its website and behind a bot check, so the supported route is a file you save yourself. `python -m indiafacts.fiidii import FILE` reads NSE's JSON or a CSV (long layout with a Category column, or wide layout with FII/DII columns, title lines and thousand separators tolerated), merges it into `~/.indiafacts/fiidii.csv` without duplicates, and the report shows the latest net, net over the last 10 sessions and the current run of net buying or selling. Never used in a rating.
- **Smart company search:** typing "infosis" now offers Infosys, in both the Streamlit app (suggestion buttons) and the Next.js app (chips), with brand aliases (SBI, Zomato, HUL). A mistyped name no longer ends in a "cannot reach Yahoo" message: the CLI and API now say "Did you mean ...". A bare symbol outside the Nifty 500 still goes through, since smaller listed companies are not in that list.
- **Streamlit crash (`webui has no attribute ownership_html`):** the cloud app builds the package once and a later "Updated app" pulls new files without rebuilding, so a new page called functions the old installed copy lacked. The app now puts the checked-out source first on the import path and drops any stale copy; a test checks that every `webui.` function the app calls exists. `data/*` is declared as package data, and the removed `components.html` has a fallback.

## 6. Downloads, dropdown search, AI analyst panel (later the same day)
- **Download:** Streamlit has "Download report (HTML)" and "Download data (JSON)"; the web app has "Download report" (the API sets a file name such as `nextrade_INFY_2026-11-07.html`) and "Print or save PDF". The HTML report is one self-contained file with charts and sources.
- **Web search box:** now a proper dropdown (arrow keys, Enter, Escape, screen-reader roles) that forgives typos. Checked in a browser: "infosis" offers Infosys, picking it runs INFY.NS.
- **AI analyst panel (needs the person's own key):** `indiafacts/agents.py` runs five focused analysts (fundamentals, price, ownership and flows, news, risk) and a research manager over the same 2k-token digest, in the same strict JSON as the single narration. Every answer is checked: ids must exist, numbers must appear in the digest, no advice wording; a bad answer is dropped, one failure never stops the rest. About 15k tokens for 6 calls, against about 43k for the 16-call TradingAgents baseline. Streamlit sends the key through the server for that one call (not stored, logged or returned, field cleared; use a key with a spending limit); the web app calls the model straight from the browser, so the key never reaches the server.
- **Gaps noise:** a year Yahoo lists but has no data for at all is no longer reported as a dozen gaps (Infosys showed 23).
