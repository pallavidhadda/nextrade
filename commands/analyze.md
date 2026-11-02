---
description: Research one NSE/BSE company with the NexTrade connector (education only, not advice)
argument-hint: TICKER such as RELIANCE or TCS.NS
---
Analyse the company named in the arguments ($ARGUMENTS) using the NexTrade connector tools. Do not run any local code or shell command.

1. Call `start_analysis` with the ticker (default NSE; add `.BO` only if the user asks for BSE). Pass profile options only if the user gave them.
2. Call `get_analysis` with the returned `job_id`. Each call waits up to about 25 seconds on the server; if it says still running, call again immediately with the same job_id, up to about 10 calls. Do not stop early. Do not guess or estimate any figure while waiting.
3. If `get_analysis` says the job is unknown or expired, the server restarted: call `start_analysis` again, at most twice, then tell the user plainly.
4. When the DIGEST arrives, explain it following the narrator rules printed at its end: at most 5 short bullets, cite the evidence id (F12) after each claim, copy numbers exactly, label facts and inferences, state every data gap, never tell the user what to do with the stock and give no price targets.
5. If the NexTrade connector tools are not available, say so and tell the user to open Customize > Plugins > NexTrade > Connectors and add the connector. Do not answer from memory.

Research and education only; not financial, investment or trading advice.
