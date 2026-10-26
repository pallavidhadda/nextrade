# NexTrade

**An AI-powered research assistant for Indian stocks (NSE/BSE).** It gathers source-linked facts, flags what is missing, compares a company with its peers and explains the numbers in plain English. It never says buy or sell.

The Python package and Claude Code plugin are named `indiafacts`.

Typed, source-linked facts for Indian equities (NSE/BSE). Every number carries its period, unit, source and an availability date, or is marked unavailable with a reason. No LLM calls.

**Research and education only. Not financial, investment or trading advice.** Data comes from Yahoo Finance (unofficial, can be late, incomplete or wrong). Availability dates are SEBI-deadline estimates, not filing dates.

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
python -m indiafacts RELIANCE.NS
python -m indiafacts RELIANCE.NS --as-of 2026-08-01
python -m indiafacts RELIANCE.NS --filing "samples/IndAS Details.html"     # official NSE results page you saved
python -m indiafacts ZOMATO.NS --symbol-changes samples/symbolchange.csv    # follows renames; demergers ask you to choose
python -m indiafacts RELIANCE.NS --horizon 5y+ --experience beginner --save-profile   # profile in ~/.indiafacts/
python -m indiafacts RELIANCE.NS --no-prices --view pro
python -m indiafacts RELIANCE.NS --filings-dir samples/filings          # every saved NSE results page for the company; revised filings are compared and restatements noted
python -m indiafacts RELIANCE.NS --changes                                # what changed since the last run (snapshots kept in ~/.indiafacts/brain.db; --no-remember to skip)
python -m indiafacts RELIANCE.NS --score --explain                  # deterministic explanation, no LLM, zero tokens
GOOGLE_API_KEY=... python -m indiafacts RELIANCE.NS --score --explain --llm gemini --html reports/r.html   # one validated, cached LLM call
python -m indiafacts RELIANCE.NS --score --html reports/reliance.html    # self-contained HTML report with charts (open in a browser)
python -m indiafacts RELIANCE.NS --score --universe tej:100     # top-100 liquid NSE names, point in time (TejHQ open data)
python -m indiafacts RELIANCE.NS --score          # rank vs a built-in pool of 30 large NSE names (about 2 minutes first run, cached for a day)
pytest            # offline tests
pytest -m live    # hits the network
```

Design and spec: `docs/`. Status: v0.6. Yahoo adapter, NSE results-page import, security master (symbol renames, curated demergers), price-history metrics vs Nifty 50, local investor profile. Percentile scoring inside a pool and a 9-point checklist (project-defined). No backtest yet: no claim that any output predicts returns.

## Use it inside Claude Code (plugin)
```
claude --plugin-dir /path/to/this/repo          # or add this repo as a marketplace once it is public
/indiafacts:analyze RELIANCE.NS --filing "samples/IndAS Details.html" --labels samples/ind_nifty500list.csv
/indiafacts:changes RELIANCE.NS
```
The command runs the deterministic tool (needs `uv`), and Claude explains the compact digest in your session, so no separate LLM key is needed. It still uses your session's tokens: in a test the digest added about 1.2k input tokens and the explanation about 1.7k output tokens on top of Claude Code's own context.

## Data credits
Price, symbol-history, corporate-action and universe data from the TejHQ open dataset (huggingface.co/datasets/tejhq/indian-markets, MIT tag; built from NSE/BSE public bhavcopy; verify exchange terms before any commercial use). Fundamentals and prices from Yahoo Finance via yfinance (unofficial). Educational project; not financial advice.

## Licence

Apache-2.0 (see `LICENSE`, `NOTICE`). Educational use only; not financial, investment or trading advice. Real NSE/BSE files and third-party datasets are not included and keep their own terms.
