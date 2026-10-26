# indiafacts

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
python -m indiafacts RELIANCE.NS --score --explain                  # deterministic explanation, no LLM, zero tokens
GOOGLE_API_KEY=... python -m indiafacts RELIANCE.NS --score --explain --llm gemini --html reports/r.html   # one validated, cached LLM call
python -m indiafacts RELIANCE.NS --score --html reports/reliance.html    # self-contained HTML report with charts (open in a browser)
python -m indiafacts RELIANCE.NS --score --universe tej:100     # top-100 liquid NSE names, point in time (TejHQ open data)
python -m indiafacts RELIANCE.NS --score          # rank vs a built-in pool of 30 large NSE names (about 2 minutes first run, cached for a day)
pytest            # offline tests
pytest -m live    # hits the network
```

Design and spec: `docs/`. Status: v0.5. Yahoo adapter, NSE results-page import, security master (symbol renames, curated demergers), price-history metrics vs Nifty 50, local investor profile. Percentile scoring inside a pool and a 9-point checklist (project-defined). No backtest yet: no claim that any output predicts returns.

## Data credits
Price, symbol-history, corporate-action and universe data from the TejHQ open dataset (huggingface.co/datasets/tejhq/indian-markets, MIT tag; built from NSE/BSE public bhavcopy; verify exchange terms before any commercial use). Fundamentals and prices from Yahoo Finance via yfinance (unofficial). Educational project; not financial advice.
