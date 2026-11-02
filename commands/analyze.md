---
description: Research one NSE/BSE company from source-linked facts (education only, not advice)
argument-hint: TICKER [--horizon 5y+] [--filing PAGE.html] [--filings-dir DIR] [--labels samples/ind_nifty500list.csv]
allowed-tools: Bash(uv run:*)
---
Evidence digest from the indiafacts tool (computed by code; every number carries an id):

!`uv run --quiet --project ${CLAUDE_PLUGIN_ROOT} python -m indiafacts $ARGUMENTS --score --pool-size 12 --digest`

Now explain this to the user following the narrator rules printed at the end of the digest. Use only what the digest says. If the digest block above is empty or shows an error, say that the tool could not run (it needs `uv` installed: https://docs.astral.sh/uv/, and network access to Yahoo Finance) and do not guess any figures. If the error says no data could be fetched and the NexTrade connector tools `start_analysis` and `get_analysis` are available, use them instead: start with the ticker, poll with the job_id every 15 to 20 seconds, then explain that digest the same way. Mention the data gaps. Offer `/indiafacts:changes TICKER` to see what changed since the last look.

This is research and education only; it is not financial, investment or trading advice.
