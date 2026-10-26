# The second brain: an analyst's and wealth manager's view (draft 2026-10-26)
Research/education only; not financial, investment or trading advice. The app never tells anyone what to do with money; the brain keeps the user's own research, reasoning and decisions.

## What a professional keeps in their head (and a second brain must hold instead)
1. **Who the money is for.** Goals, horizon, risk tolerance AND capacity, liquidity needs, constraints, concentration limit (an investment policy statement). We have a profile; goal, liquidity need and the max single-stock share are stored but unused.
2. **What is owned.** Holdings, cost, dates, weights, sector exposure, how much one bad outcome would cost. We have nothing yet.
3. **Why each position or watch exists.** A thesis: the claims it rests on, the evidence for each, what would prove it wrong (kill criteria), and the disconfirming evidence already seen. We have evidence-linked claims and deterministic triggers, but they are thrown away after each run.
4. **What was decided and why.** A decision journal: date, what was known then, expected horizon, expected outcome, confidence. Without it nobody can learn, and hindsight rewrites memory.
5. **What changed since the last look.** Professionals do not re-read everything; they ask "what is new". Results season, filings, price moves through trigger levels. We recompute from scratch every run and remember nothing.
6. **Did it work?** Calls and scores graded against outcomes and the benchmark, out of sample. Not built (backtest, scorecard).
7. **Where each fact came from and how stale it is.** Provenance, availability dates, review-by dates. Built and the strongest part.

## What goes wrong without discipline (anti-goals)
Hindsight bias (judging past decisions with today's facts); confirmation bias (a thesis note with only supporting evidence); false precision (a pretty score read as a forecast); stale data presented as current; over-trading from constant alerts; hoarding notes nobody reviews; a tool whose confident tone outruns its evidence. Design answers: knowledge is stored AS OF a date and never edited; every thesis must list disconfirming evidence and kill criteria; every score page repeats "relative, not a forecast"; alerts are digests, not pings; review dates are mandatory.

## Proposed slices (each small, each useful alone, all local-first)
- **S0 Comparability gate and observation metadata** (done today: restated, evidence, comparability checks; follow-up: accept two filings so a year-on-year can be verified on one basis).
- **S1 Snapshot store and "what changed".** Save each run's facts, scores, checklist and gaps by date (SQLite or JSONL). A `changes` view: new quarter filed, gap closed, checklist test flipped, rank moved, a trigger crossed. This is the heart of a second brain and unlocks honest backtests (stored as-of data).
- **S2 Thesis notes.** One markdown file per company, front matter with claims (fact ids), kill criteria written as machine-checkable rules (metric, operator, threshold), disconfirming evidence, status. `thesis check` re-evaluates kill criteria against the newest facts.
- **S3 Decision journal** (the user's own entries, append-only): what, why, horizon, expected outcome, confidence. Automatic review at the horizon: return vs Nifty 50, which kill criteria fired, what the facts looked like then vs now. No advice from the app; it only records and reviews.
- **S4 Portfolio import and risk view.** Holdings CSV in; concentration against the profile's limit, sector exposure from NSE industry labels, simple drawdown and beta contribution; "this position would be X% of the portfolio" prompts. Uses the unused profile fields.
- **S5 Watch and digest.** Scheduled run (cron, or a Claude Code scheduled task) that writes a short digest of S1 changes for the watchlist and held names.
- **S6 Markdown vault export.** Obsidian-style folder: a note per company, daily notes, thesis and journal notes with [[links]] and the same fact ids. Plain text, user-owned, works offline, diff-able in git.
- **Later:** peers from a fast bulk source; sum-of-the-parts for conglomerates; backtest with the point-in-time universe; web front end over the same store.

## Design principles
Immutable, timestamped facts (never overwrite; add a newer version). Everything the user wrote is separate from everything the app computed. Machine-checkable rules beat prose. One source of truth: the fact ledger. The LLM narrates; code checks; notes link to fact ids so a claim can always be traced to evidence. Token cost stays near zero for the second brain itself: all of S1-S6 are deterministic; the LLM is only for optional plain-English summaries.

## Open questions
1. Local-first single user (markdown vault + SQLite on the user's machine) or a multi-user web app first? Recommendation: local-first, web later over the same store.
2. Is the portfolio (S4) in scope for the public project, given the advice-regulation caution? Recommendation: yes as the user's own tracking with no recommendations; confirm with a lawyer before a public launch.
3. Which slice first? Recommendation: S1 (snapshot and what-changed), because S2, S3, S5 and the backtest all stand on it.
