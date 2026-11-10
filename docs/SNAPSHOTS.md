# Daily snapshots

Why: on Render's free tier (shared cloud IP) live analyses sometimes fail with exit 5 (zero usable facts), probably because Yahoo throttles that IP. A scheduled GitHub Actions job precomputes analyses and the API serves them instantly. Live analysis stays as a fallback and as "Refresh now".

## How it works

1. `.github/workflows/snapshots.yml` runs weekdays at 12:30 UTC (18:00 IST, after the NSE close). It runs `python -m indiafacts.snapshots`, which analyses the Nifty 50 (`indiafacts/data/nifty50.txt`, approximate, edit as needed) plus the web app's example tickers, one at a time with a 5 s pause. It uses the same runner and flags as the API (including `INDIAFACTS_POOL_SIZE`).
2. Per ticker it writes `<TICKER>.json` (the API summary), `<TICKER>.html` (the report) and `index.json` (`{ticker: {as_of, ok, error, generated_at, commit}}`). A failed ticker is recorded and the run continues; if an older good snapshot exists it is kept and the failure is noted as `last_error`. The command exits 1 only if more than `--max-fail-pct` (default 30, env `SNAPSHOT_MAX_FAIL_PCT`) failed.
3. The workflow pushes the files to the orphan branch `snapshots`. Main never gets snapshot commits.
4. The API reads `index.json` and the ticker files from `INDIAFACTS_SNAPSHOT_BASE`, cached in memory for 1 h. In `POST /api/analyze`, a snapshot that is `ok` and at most 4 calendar days old is returned as an already-completed job, so the web app and the MCP connector keep their start-then-poll flow. The response and the job carry `served_from: "snapshot"`; the summary carries `served_from` and `snapshot_as_of`. Otherwise (no snapshot, stale, or `refresh=true` as query or body field) the analysis runs live and is labelled `served_from: "live"`.

Why a branch, not a Release asset: the branch needs no extra API, `raw.githubusercontent.com` is free and unauthenticated for public repos, and history is a free audit trail. A private repo would need a token; use a Release asset or host elsewhere in that case.

## Environment variables

| Variable | Where | Meaning |
| --- | --- | --- |
| `INDIAFACTS_SNAPSHOT_BASE` | Render | `https://raw.githubusercontent.com/<owner>/<repo>/snapshots`. Unset disables snapshots (live only). It is also the default base for the other published files: `INDIAFACTS_MARKETLENS_URL` (`marketlens.json`), `INDIAFACTS_POOL_METRICS_URL` (`pool_metrics.json`, the sector comparison) and `INDIAFACTS_NSE_COPY_BASE` (`nse/`) need setting only to point elsewhere; set one to an empty string to switch that file off (`indiafacts/published.py`). |
| `INDIAFACTS_SNAPSHOT_MAX_AGE_DAYS` | Render | Freshness limit in calendar days, default 4 (covers a weekend plus a holiday). |
| `SNAPSHOT_MAX_FAIL_PCT` | job | Failure share that turns the run red, default 30. |
| `INDIAFACTS_POOL_SIZE` | job, Render | Comparison pool size; the workflow sets 30. |

## Probe: does Yahoo work from GitHub's runners?

```
gh workflow run snapshots.yml -f probe=true
gh run watch
```

The log ends with `PROBE VERDICT: Yahoo WORKS ...` or `... does NOT work ...`. Locally: `python -m indiafacts.snapshots --probe`. Run the first full job with `gh workflow run snapshots.yml` (optionally `-f tickers=TCS.NS,INFY.NS`).

## Staleness trade-off

Fundamentals change about quarterly, so a snapshot is fine for them. Price-linked figures (price, P/E, P/B, levels, flows) can be up to a day old on a normal weekday, longer over a weekend; the `snapshot_as_of` date says exactly when, and the UI should show it next to "Refresh now". A snapshot ignores the user's profile fields (horizon, risk), so profile-specific wording is the generic one; "Refresh now" runs live with the profile.

## Operations

- Busy server: `INDIAFACTS_MAX_RUNNING=1` answers a second live analysis with 429 and the message "The server is busy with another analysis; try again in a minute." Snapshot hits never count toward that limit.
- Keep-warm: Render's free tier sleeps after about 15 minutes idle. Point any external pinger (for example UptimeRobot or cron-job.org, every 10 minutes) at `GET /api/health`. Nothing in this repo pings it.

## NSE filings daily copy

NSE's website API (`indiafacts/nseapi.py`) answers GitHub's runners but answers HTTP 403 to Render's datacenter address. We do not try to get around that block. Instead the snapshot job (which fetches NSE live, as before) writes what it parsed for each ticker to `nse/<SYMBOL>.json` on the `snapshots` branch, and Render reads that copy.

- Format: `{version, symbol, generated_at, shareholding: {as_on, sh: {...Shareholding fields}, rows: [newest 8 list rows: date, pr_and_prgrp, recordId, xbrl, ...]}, results: [{period, basis, audited, filing_date, xbrl_url, entity, filing, common, facts}]}`. `common` holds the fields all facts of a filing share; `fact_id` is recomputed on read. The raw XBRL files are not published (about 100-500 KB each, roughly 1 GB for 486 tickers); the parsed copy is about 80 KB per ticker, so about 40 MB for 486 (measure on the first real run).
- Evidence: facts keep source `nse_xbrl` / `nse_shp` and their concept-level evidence; a fact read from the copy adds "official NSE filing <XBRL url>; daily copy as of <date>". The report notice reads "official NSE filings from the daily copy as of <date> (NSE does not answer this server directly)".
- The job sets `INDIAFACTS_NSE_COPY_OUT=<out>/nse` and points `INDIAFACTS_NSE_COPY_BASE` at that same folder (yesterday's files, already checked out), so NSE is tried live first and yesterday's copy is only a fallback if NSE fails during the run. A part live did not produce keeps the older copy's version of it.
- Reader: tries the copy when a live call fails, never raises, 1 h memory cache (5 min for a miss). If there is no copy either, the old notice "official NSE filings not reachable this run" stays.

| Variable | Where | Meaning |
| --- | --- | --- |
| `INDIAFACTS_NSE_COPY_BASE` | Render | `https://raw.githubusercontent.com/<owner>/<repo>/snapshots/nse/` (or a `file://` folder). Where `<SYMBOL>.json` is read. |
| `INDIAFACTS_NSE_COPY_FIRST` | Render | `1` reads the copy before trying NSE live (saves the 403 round trips; needs `INDIAFACTS_NSE_COPY_BASE`). |
| `INDIAFACTS_NSE_API_LIVE` | any | `0` turns only the live NSE calls off; the copy is still read. `INDIAFACTS_NSE_API=0` turns both off. |
| `INDIAFACTS_NSE_COPY_OUT` | job | Folder the copy is written to. Set by `snapshots.py`; leave unset elsewhere. |

## NSE Market Lens file

Before precomputing, the job fetches the NSE Market Lens universe once (58 requests, 1 s apart; see `docs/DATA_PERMISSIONS.md`) into `snapshots/marketlens.json`, which is published on the `snapshots` branch next to the reports. Each analysis in the run reads that file (the job points `INDIAFACTS_MARKETLENS_URL` at it), so NSE is not called per ticker. If the fetch fails, the previous file on the branch is kept.

| Variable | Where | Meaning |
| --- | --- | --- |
| `INDIAFACTS_MARKETLENS_URL` | Render | `https://raw.githubusercontent.com/<owner>/<repo>/snapshots/marketlens.json`. Read with a 1 h memory cache; when set, NSE is never called directly. |
| `INDIAFACTS_MARKETLENS_CACHE` | local | Disk cache path, default `~/.indiafacts/marketlens.json`, valid for 1 day. |
| `INDIAFACTS_MARKETLENS` | any | `0` switches Market Lens off (also `--no-marketlens`). |

`INDIAFACTS_MARKETLENS_LIVE=0` disables the direct Market Lens request for the target on live analyses (the snapshot job sets it).

Refresh by hand: `python -m indiafacts.marketlens`.

## Drift check

Why: a source can change shape or units without any error (Market Lens already ships beta = 1 and return on equity = 0 for every company). `indiafacts/drift.py` compares today's `marketlens.json` and `pool_metrics.json` (and, when samples are given, NSE API list responses) with the baseline `indiafacts/data/source_schema.json` and with yesterday's published copies. The snapshot job runs it after fetching Market Lens and building `pool_metrics.json` (`snapshots.drift_gate`) and publishes `drift_report.json` next to them: `{generated_at, status: ok|warning|breaking, checks: [{source, check, field, severity, detail}], disabled_fields}`.

Checks: required fields present with the right type; sanity ranges (P/E 0-500, P/B 0-100, market cap above 1e9 INR, volatility, holdings sum 100 +/- 1); row count against yesterday (total, and per sector with at least 5 rows; more than 30% change); placeholders (0 or null, or one repeated value, in more than 50% of rows); units (median more than 5 times yesterday's); anchors (Market Lens market cap of RELIANCE, TCS and HDFCBANK within 5% of our own figure; skipped, as info, while `pool_metrics.json` publishes no `market_cap` metric). Thresholds live in the schema file.

| Severity | Triggers | What happens |
| --- | --- | --- |
| breaking | missing required field, wrong type, out-of-range values (over 20% of rows), unit jump, row count drop over 30%, anchor failure | That source's new file is not published: yesterday's copy is kept (or none, if there was none). `drift_report.json` is still published; `index.json` gets `_meta.drift_status`. The `drift-issue` job opens or comments on a GitHub issue titled `Source drift: <source>`. |
| warning | placeholder field, smaller shifts, row count rise over 30% | Files are published. The run's step summary lists the findings. |
| info | a known placeholder (`expected_placeholders` in the schema), or a check that could not run | Listed in the report only. |

Placeholder fields go into `disabled_fields` (`marketlens.<field>`, `pool_metrics.<metric>`). Market Lens fields are skipped for that day by `marketlens._num` through `INDIAFACTS_DRIFT_REPORT` (the job sets it to the report path; unset means nothing is skipped). Placeholder pool metrics are removed from the published `pool_metrics.json`. The report stamp carries `drift_status` and `source_policy` (hash of `data/source_policy.json`).

Issues: the `drift-issue` job is the only one with `issues: write`. It runs `python -m indiafacts.drift issues drift_report.json` using `gh` and `GH_TOKEN`, deduplicated by exact title (an open issue gets a comment instead). Run the workflow by hand with `-f dry_run=true` to print the titles and bodies instead. Issues are not closed automatically. Locally: `python -m indiafacts.drift check --marketlens new.json --marketlens-prev old.json --pool pool.json --nse-dir tests/fixtures`.
