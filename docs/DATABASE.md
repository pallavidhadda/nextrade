# Do we need a database? (2026-11-07)
Research/education only; not financial, investment or trading advice.

## What exists today
| Data | Where it lives | Survives a restart? |
|---|---|---|
| Decision journal (every educational rating, later settled against the Nifty 50) | SQLite file `~/.indiafacts/journal.db` on the machine that ran the analysis | Yes on your laptop. **No on the free Render server**: its disk is wiped on restart |
| Snapshot store ("what changed since last run") | SQLite `~/.indiafacts/brain.db`, same caveat | same |
| Pool cache (30 companies, one day) | JSON files in `~/.indiafacts/cache` | a cache; losing it only costs time |
| Facts, scores, reports | computed per request; nothing stored | n/a |
| Users, profiles, keys | not collected on purpose | n/a |

## What "run the journal for 4-6 weeks" means
A rating is a claim about the future. It can only be scored once its holding window (21 trading sessions, about 4.5 weeks) has passed: the journal buys at the next close, waits, then compares the stock with the Nifty 50. So a journal started today shows its first settled rows in about five weeks, and a meaningful scoreboard (a few hundred settled ratings across Buy to Sell) needs a couple of months. There is no shortcut: fundamentals are not point-in-time in free data, so past ratings cannot be reconstructed honestly.

## What we did about it
- `python -m indiafacts.journal log --limit 6` rates a rotating slice of the pool and records each rating, so nobody has to type tickers.
- `export` / `import` move the journal to and from `data/journal.csv`.
- `.github/workflows/journal.yml` runs import, log, settle, export every weekday after the NSE close and commits `journal.csv` to the **`data` branch** (so `main` has no data commits); `shareholding.yml` does the same for `shareholding.csv` every 4 hours. **The CSV on the data branch is the database for the public scoreboard.** To use it locally: `git fetch origin data`, then `git show origin/data:shareholding.csv > ~/.indiafacts/shareholding.csv`. It is free, versioned, diffable and needs no server.

## Do we need a real database?
- **For the portfolio project: no.** One CSV, a few thousand rows a year, one writer (the scheduled job).
- **Yes, if** the hosted app starts remembering things per visitor (watchlists, saved profiles, holdings, alerts). Then use Postgres (Supabase free tier is enough) with row-level security, and keep the privacy promise explicit. Until then "no accounts, nothing stored" is a feature.
- Do not put the journal on Render's free disk. Either use the scheduled job above or a managed Postgres.
