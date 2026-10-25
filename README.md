# indiafacts

Typed, source-linked facts for Indian equities (NSE/BSE). Every number carries its period, unit, source and an availability date, or is marked unavailable with a reason. No LLM calls.

**Research and education only. Not financial, investment or trading advice.** Data comes from Yahoo Finance (unofficial, can be late, incomplete or wrong). Availability dates are SEBI-deadline estimates, not filing dates.

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
python -m indiafacts RELIANCE.NS
python -m indiafacts RELIANCE.NS --as-of 2026-08-01
pytest            # offline tests
pytest -m live    # hits the network
```

Design and spec: `docs/`. Status: v0.1, Yahoo adapter only.
