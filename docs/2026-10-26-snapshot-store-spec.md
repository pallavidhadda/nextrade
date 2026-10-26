# S1 Snapshot store and "what changed" (compact spec, also covers restatement detection)
Research/education only; not advice.
Goal: remember every run, keep every VERSION of every figure with its dates, and report what changed since the last look. Restatements are a special case of "the same period's figure changed".

User's restatement procedure (pasted 2026-10-26) vs what is feasible now:
1 fetch the original filing; 2 fetch later filings for the same company and period; 3 compare submission type and revision remarks; 4 extract current and prior-year figures from the latest relevant filing; 5 compare with the original; 6 preserve both versions and cite filing dates.
Feasible: steps 4-6 once filings are supplied (saved pages), because the store keeps versions and filing dates. Steps 1-3 need automated access to NSE filing lists, which is blocked for scripts, and the "revision metadata" claim is unverified: our one sample results page shows no revision field (it shows audit status and board-meeting date). So: detect restatements by comparing figures across versions, and treat explicit revision remarks as a bonus when a page has them.
Policy confirmed: NSE/BSE are the source of truth, Yahoo only a cross-check; if comparability cannot be verified the growth figure is flagged (done: comparability gate).

Design: stdlib sqlite3 at ~/.indiafacts/brain.db (no new dependency). Observations are content-addressed by (fact id, value, status, reason, evidence): a changed value for the same fact id becomes a second version, never an overwrite. A run row links to the observations it saw, plus score, rank and checklist results. `changes(ticker)` compares the latest run with the previous one:
- possible_restatement: an NSE-filing figure for the same period changed; cites both filing dates and values;
- vendor_revision: a Yahoo reported figure changed;
- gap_closed / gap_opened; status_changed (ok to unverified etc.); new_figure (a new quarter);
- checklist_flip; rank_moved; score_changed (>= 1 point);
- market_move only when material (return/volatility moves >= 2 points, price/P-E/P-B/market-cap >= 5%); the rest are counted, not listed.
Computed facts are never reported as changes by themselves. The brain must never break a report: any storage error becomes a notice. `--no-remember` skips it. HOME is isolated in tests.
Tests BR1-BR10: dedupe and versions; restatement text with both dates; vendor revision; gap closed/opened; checklist flip and rank move; market materiality; first run; per-ticker previous run; storage failure is a notice; CLI `--changes`, `--no-remember`.
