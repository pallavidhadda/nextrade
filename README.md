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
pytest            # offline tests
pytest -m live    # hits the network
```

Design and spec: `docs/`. Status: v0.2. Yahoo adapter, NSE results-page import, security master (symbol renames, curated demergers), price-history metrics vs Nifty 50, local investor profile. No scoring or backtest yet: no claim that any output predicts returns.
