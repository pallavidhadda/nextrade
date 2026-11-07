# NexTrade

**An AI-powered research assistant for Indian stocks (NSE/BSE).** It gathers source-linked facts, says plainly what is missing, compares a company with its peers and explains the numbers in plain English. It never says buy or sell.

> Research and education only. Not financial, investment or trading advice. Free data (Yahoo Finance) is unofficial and can be late, incomplete or wrong. A historical test of simple price signals ([result](docs/2026-10-26-backtest-result.md)) is not evidence that any score predicts returns.

## What it produces
Per company: source-linked facts with gaps, a pool-relative score, a nine-point checklist, what the price implies (reverse DCF grid), deterministic indicators, a bull case versus bear case, an educational rating on the Buy / Overweight / Hold / Underweight / Sell scale with confidence, volatility-based reference levels, three risk lenses with position ceilings, recent headlines with a keyword hint, a decision journal that settles each rating against the Nifty 50, and a claim checker for figures you read elsewhere, and a business-health block from annual statements (free cash flow, net debt, EV/EBITDA, ROCE, 3-year growth, lender metric set for banks). One model call at most, on a digest of about 2k tokens; see [docs/TOKEN_COMPARISON.md](docs/TOKEN_COMPARISON.md). Priorities: [docs/MOSCOW_PRIORITIES.md](docs/MOSCOW_PRIORITIES.md).

## What makes it different
- **Provenance first.** Every figure carries period, unit, source and basis, or is marked unavailable with a reason. Missing quarters are flagged, never filled.
- **India aware.** Renames (Zomato to Eternal), demergers (Tata Motors), NSE results pages you save, a point-in-time liquid universe from TejHQ open data.
- **Cheap on tokens.** Maths is code. A model only narrates a compact digest (about 1.6k tokens measured, versus about 39k for the TradingAgents baseline run, which does different work), or no model at all.
- **Private by design.** No accounts. Your model key stays in your browser. The server only checks that the model's claims cite real evidence.

## Use it
```bash
uv venv --python 3.12 && uv pip install -e ".[dev,api]"
python -m indiafacts RELIANCE.NS --score --explain --html report.html     # terminal and HTML report
python -m indiafacts.backtest --from-year 2016 --oos-start 2023-01-01     # price-signal scorecard
python -m indiafacts.claims TCS.NS eps 142.66 --unit per_share            # check a stated figure against sourced facts
python -m indiafacts.journal settle                                      # score past educational ratings against the Nifty 50
python -m indiafacts.journal board                                       # scoreboard by rating
python -m indiafacts.journal log --limit 6                               # rate a slice of the pool and record it (also runs weekdays via GitHub Actions)
python -m indiafacts TCS.NS --announcements                              # latest exchange filings from NSE's public RSS feed
```
Web app (Next.js): [web/README.md](web/README.md). Streamlit app (free, from GitHub): `streamlit run streamlit_app.py`, deploy steps in [docs/DEPLOY_STREAMLIT.md](docs/DEPLOY_STREAMLIT.md). API and Claude connector hosting: [docs/DEPLOY.md](docs/DEPLOY.md); optional connector lock: [docs/CONNECTOR_LOCK.md](docs/CONNECTOR_LOCK.md).

Claude Code plugin (private repo for now):
```
/plugin install indiafacts --marketplace pallavidhadda/nextrade
/indiafacts:analyze RELIANCE.NS          # uses the NexTrade connector (works in chat and Cowork)
/indiafacts:analyze-local RELIANCE.NS    # Claude Code only: runs locally, needs network and uv
```

## Where it stands
Latest team review: [docs/QUALITY_AND_UX_REVIEW_2026-11-07.md](docs/QUALITY_AND_UX_REVIEW_2026-11-07.md); storage decisions: [docs/DATABASE.md](docs/DATABASE.md). See [docs/PRODUCT_REVIEW.md](docs/PRODUCT_REVIEW.md) for the honest comparison with TradingAgents, ai-hedge-fund, FinRobot and OpenBB and the ranked to-do list, and [docs/ROADMAP.md](docs/ROADMAP.md).

## Licence
Apache-2.0 (see `LICENSE`, `NOTICE`). Real NSE/BSE files and third-party datasets are not included and keep their own terms. TejHQ data: attribute TejHQ.
