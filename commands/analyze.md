---
description: Research one NSE/BSE company from source-linked facts (education only, not advice)
argument-hint: TICKER [--horizon 5y+] [--filing PAGE.html] [--filings-dir DIR] [--labels samples/ind_nifty500list.csv]
allowed-tools: Bash(uv run:*)
---
Evidence digest from the indiafacts tool (computed by code; every number carries an id):

!`uv run --quiet --project ${CLAUDE_PLUGIN_ROOT} python -m indiafacts $ARGUMENTS --score --digest`

Now explain this to the user following the narrator rules printed at the end of the digest. Use only what the digest says. If the digest block above is empty or shows an error, say that the tool could not run (it needs `uv` installed: https://docs.astral.sh/uv/) and do not guess any figures. Mention the data gaps. Offer `/indiafacts:changes TICKER` to see what changed since the last look.

This is research and education only; it is not financial, investment or trading advice.
