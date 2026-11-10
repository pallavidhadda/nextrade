# Data permissions

Education only; not financial advice. This file records permissions the project relies on and how the code stays inside them.

## NSE Market Lens (https://marketlens.nseindia.com)

**Permission.** The owner states they have permission from NSE to use NSE Market Lens, NSE's own screener, for educational purposes (recorded 2026-11-10). The owner is to add the reference or correspondence here: `TODO (owner): correspondence reference`.

Owner confirmed on 2026-11-10 that the permission covers publishing derived figures (snapshots branch, public repo); correspondence reference to be added by the owner.

**How we access it** (`indiafacts/marketlens.py`):

- Plain HTTP GET with the honest User-Agent `NexTrade-research/0.1 (education; permitted use of NSE Market Lens)`.
- No browser impersonation, no cookie handling, no key extraction or token decryption.
- One request at a time, at least 1 second apart (the client enforces a floor of 1 s); 20 s timeout; size cap.
- Endpoints: `GET /api/sectors` and `GET /api/sectors/{id}/stocks`. About 58 sector requests build the whole universe.
- Cached on disk for one day (`~/.indiafacts/marketlens.json`). The scheduled snapshot job fetches once per run and publishes the file as `marketlens.json` on the `snapshots` branch; Render reads that file (`INDIAFACTS_MARKETLENS_URL`) for the universe and peers; for a live analysis it also makes one direct request for the target's sector, falling back to that file. Failures never raise: the run continues without Market Lens and says why.
- Switch off with `--no-marketlens` or `INDIAFACTS_MARKETLENS=0`.

**Fields used** (percent fields converted to ratios, so 0.45 means 45%; same units as the Yahoo and shareholding facts):

| Market Lens field | Metric | Unit / note |
| --- | --- | --- |
| `marketCap` | `market_cap` | rupees; matches our own price x shares figure for RELIANCE (17.92 lakh crore) |
| `peRatio` | `pe_ttm` | ratio; on a different EPS basis from ours, so differences are flagged as source conflicts |
| `pbRatio` | `pb` | ratio |
| `debtToEquity` | `debt_to_equity` | plain ratio (0.41; company filing 0.40). Yahoo's percent-style figure is already divided by 100 in `yahoo.py` |
| `roce` | `ml_roce` | percent to ratio; status `unverified` (definition unpublished, not our `fy_roce`) |
| `divYield` | `dividend_yield` | percent to ratio |
| `promoterHolding`, `publicHolding` | `sh_promoter`, `sh_public` | percent to ratio; used only if they add to 100 and no official shareholding file is present. As-of is the Market Lens `lastUpdated` date, not the quarter end |
| `week52High`, `week52Low` | `high_52w`, `low_52w` | rupees; only when price history gave none |
| `sector`, `subSector` | peer group | `sector` is the fine group (for example "Petroleum Products"), `subSector` the broad one ("Energy") |

Each fact's evidence names the endpoint, field and `lastUpdated` stamp.

**Fields skipped, and why:**

- `returnOnEquity`, `revenueGrowth`, `industryPe`, `avgVolume`: observed as 0 on RELIANCE, a placeholder. A 0 on any placeholder field gives no fact.
- `patGrowth`: equals `netProfit` (a bug upstream).
- `netProfit`, `revenue`, `opRevenue`, `totalEquity`, `totalAssets`, borrowings and cash-flow lines: units are mixed (for example `opRevenue` is ten times `revenue`; RELIANCE `revenue` 1,086,181 does not match any single plausible rupee scale). Not used as facts unless the unit is proven by cross-checking several companies against filed figures.
- `eps`: 12.54 for RELIANCE, which does not reconcile with price / P/E, so the basis is unknown.

**Open point for the owner.** Snapshots publish figures derived from Market Lens (and the raw `marketlens.json` universe file) on a public branch. The owner confirmed on 2026-11-10 that the permission covers this. Add the correspondence reference above.

**Live analyses.** For the target only, a live run first makes one direct request for the target's sector (`/api/sectors/{id}/stocks`, 10 s timeout, cached 1 h in the process; the sector id comes from the stored copy). If that fails it uses the published daily copy (`INDIAFACTS_MARKETLENS_URL`), then the local cache. The origin ("live", "daily copy as of <date>", "local cache as of <date>") is written into each fact's evidence and into the run notices. Peers always come from the stored copy. `INDIAFACTS_MARKETLENS_LIVE=0` disables the direct call (the snapshot job sets it, so it makes one fetch per run, not one per ticker).

## NSE website data API (https://www.nseindia.com/api)

**Permission.** The owner states they have NSE's permission to use NSE's website data API for educational purposes, including publishing figures derived from it (recorded 2026-11-10). `TODO (owner): correspondence reference`.

**How we access it** (`indiafacts/nseapi.py`, our own client; no third-party NSE package is used):

- Plain HTTP GET with the honest User-Agent `NexTrade-research/0.1 (education; permitted use of NSE data)` and `Referer: https://www.nseindia.com/`. No cookies. (The home page answers 403 to this agent, but the API paths answer 200 without cookies.)
- One request at a time, at least 1 second apart; 15 s timeout; 20 MB cap per response; retries only on HTTP 429/503, at most two, with backoff. Anything else (403, timeouts, bad JSON) is not retried and never raises: the run continues without NSE's figures and a notice says "official NSE filings not reachable this run".
- Target company only (not the comparison pool), and not in `--as-of` runs (today's filings would be look-ahead).
- Endpoints: `corporate-share-holdings-master?index=equities&symbol=S` (list of quarters, each with the filed SHP XBRL link); `integrated-filing-results?index=equities&period_ended=all&type=Integrated Filing- Financials&symbol=S` (quarterly results filed from Q3 FY25 onward, XBRL link per filing, consolidated and standalone); `corporates-financial-results?index=equities&period=Quarterly&symbol=S` (older results filings; it stops at Dec 2024 for RELIANCE); then the XBRL files from `nsearchives.nseindia.com` (host allow-listed). `results-comparision` is not used (units and basis unproven; the XBRL files are preferred).
- What we take: the newest shareholding row's XBRL goes through the existing `parse_shp` (promoter, FII, DII, mutual funds, pledge, as-of date); the promoter change against the previous quarter cites two consecutive list rows. The newest eight quarterly CONSOLIDATED results files (five are needed for year-on-year; the rest cover a late or unreadable filing) (standalone only if a company has none, noted) go through the existing XBRL parser, so year-on-year compares two filings on the same basis. Banks file a different taxonomy (`INTEGRATED_FILING_BANKING`); net profit, EPS, finance cost and pre-tax profit are read, revenue is left to other sources.
- Cache: `~/.indiafacts/nse_api/` (`INDIAFACTS_NSE_CACHE`); list responses one day, XBRL files forever (a filing is a fixed document).
- Switches: `--no-nse-api` or `INDIAFACTS_NSE_API=0` turns it off. `INDIAFACTS_NSE_BROWSER_HEADERS=1` (default OFF) sends browser-like headers and warms up a cookie from the NSE home page; it exists only for the case where NSE starts refusing the honest client, and is covered by the owner's permission. Do not enable it otherwise.
- Snapshot job: enabled, one ticker at a time (it already waits between tickers). Render live runs: enabled with fallback.
- Published copy (added 2026-11-10): NSE answers 403 to Render's address, and we do not evade it (no proxy, no browser impersonation). The daily snapshot job instead publishes the figures it parsed (derived filing figures, with a link to each original XBRL file) as `nse/<SYMBOL>.json` on the `snapshots` branch, and Render reads that. The owner confirmed that publishing figures derived from this API is covered by the permission above. No raw NSE files are republished. Variables: `INDIAFACTS_NSE_COPY_BASE`, `INDIAFACTS_NSE_COPY_FIRST`, `INDIAFACTS_NSE_API_LIVE` (see docs/SNAPSHOTS.md).
