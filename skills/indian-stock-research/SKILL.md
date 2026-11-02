---
name: indian-stock-research
description: Research an Indian listed company (NSE or BSE ticker such as RELIANCE, TCS.NS, HDFCBANK) from source-linked facts: score inside a comparison pool, nine-point checklist, data gaps, peer comparison. Use when the user asks to analyse, check, compare or understand an NSE/BSE stock. Education only, never advice.
---
# Indian stock research (NexTrade)

Use the NexTrade connector tools (`start_analysis`, `get_analysis`). Never run local code or the `python -m indiafacts` command for this: sandboxes and chat have no access to market-data sites. Everything numeric comes from the connector; never supply figures from memory.

1. Call `start_analysis` with the ticker (add `.NS` or `.BO` if the user gave it). Pass `horizon`, `risk_tolerance`, `risk_capacity` or `experience` only if the user told you; they only change how the factor score is weighted.
2. Call `get_analysis` with the `job_id`. If it says the job is unknown or expired, the server restarted: call `start_analysis` again (at most twice), then tell the user plainly.
   Call `get_analysis` with the `job_id`. If it says running, wait 15 to 20 seconds and call again (a first run can take up to 3 minutes). Do not guess or estimate anything while waiting.
3. When the DIGEST arrives, explain it to the user following the narrator rules printed at its end:
   - at most 5 short bullets, cite the evidence id (F12) after each claim;
   - copy numbers exactly; do not round, convert or compute new ones;
   - label each statement as a fact (from the digest) or your inference;
   - always list the data gaps, unverified and conflicting items;
   - never say buy, sell, hold, accumulate, avoid or suggest a price target; never say a stock is "good" or "bad";
   - end with: Research and education only; not financial, investment or trading advice.
4. If the connector tools are not available, tell the user to open Customize > Plugins > NexTrade > Connectors and add/connect the NexTrade connector. Do not answer from memory.
5. If the result is an error or "unresolved", say so plainly and stop.

The score is a percentile inside a small pool of companies, not an absolute quality rating. Say that whenever you quote it.
