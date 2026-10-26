---
description: What changed for one NSE/BSE company since the last indiafacts run (restatements, new filings, flipped checks)
argument-hint: TICKER [--filings-dir DIR]
allowed-tools: Bash(uv run:*)
---
Changes since the previous run (the tool keeps every version of every figure in a local snapshot store):

!`uv run --quiet --project ${CLAUDE_PLUGIN_ROOT} python -m indiafacts $ARGUMENTS --score --changes-only`

Summarise these changes in plain English, grouped by importance, and say which items need attention (possible restatements, status changes, flipped checks). Quote numbers exactly as shown. If nothing is listed, say there is nothing new or that this was the first run. This is research only, not financial, investment or trading advice.
