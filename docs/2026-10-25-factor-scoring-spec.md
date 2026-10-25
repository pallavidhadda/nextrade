# Priority 2 — Screening and factor scoring: study, spec, test cases (DRAFT for approval)
Research/education only; not financial, investment or trading advice. Nothing is built.
Success criterion (yours): reproducible scores, explicit weights, and tests that catch ranking changes caused by bad data.

## 1. What I read (source, not READMEs; not run)
ai-hedge-fund (MIT): blend weights are explicit per model in versioned YAML; conviction normalised to a gross target; an analyst can *abstain* when data is insufficient and abstentions are excluded from averages (portfolio/construction.py); every clamp is logged; scorecard grades views by hit rate and rank IC.
FinRobot (Apache-2.0): peer screening is fully deterministic so "the same candidate payload always yields the same peer set, with a numeric trace" (operators/peer_screen.py); their note records the old LLM selection swinging a price target +-30% in a day. Membership and median-eligibility are separate questions: a peer with an extreme multiple stays in the set but is kept out of the median by a "not meaningful" cap (P/E 75, EV/EBITDA 50); a negative P/E is excluded; None propagates as not-meaningful; dropped rows are reported, not silently dropped (operators/multiples.py). Tiered affinity (same industry, then cross-recommended, then same sector) with size-proximity ranking and a demotion rule for far-away names.
Standard methods I know from general knowledge, not read in these repos (verify before citing): winsorise then percentile-rank or z-score within a universe; sector-relative ranking; Piotroski F-score (9 binary pass/fail tests, robust to outliers); Greenblatt Magic Formula (rank earnings yield and return on capital, sum ranks).
Gap: none of the four repos has tests that perturb bad inputs and assert the ranking flags it. That is the part to build.

## 2. Design (my calls; check them)
Inputs: FactSets for a universe (user-supplied ticker list; default = the 30 large NSE names I probed) plus a sector label per name (needs one new Yahoo field, `sector`, stored on Entity).
Metric registry (versioned YAML, hashed into every output): id, source metric, direction, validity rule (e.g. P/E valid if 0 < P/E <= 75, FinRobot-style), winsorise bounds, factor group, weight. v1 metrics are limited to what our Facts hold: Value (P/E, price/book if added), Quality (ROE when present, interest cover and debt/equity from filings), Growth (YoY net income, YoY revenue from filings), Leverage. Momentum needs price-history Facts and comes later.
Normalisation: winsorise at 5th/95th percentile within the comparison group, then percentile rank to 0-100. Group = sector if it has >= 8 valid names, else whole universe with a visible "sector group too small" flag. Banks/NBFCs use their own metric set (no EBITDA, EV).
Missing data: never imputed. A missing or invalid metric is dropped for that name and its weight renormalised only if the factor keeps >= 60% of its weight; otherwise the factor score is `unavailable` with a reason. Overall score needs >= 2 valid factors, else `abstain`. Coverage % is printed next to every score.
Output: each score is a Fact (value 0-100 or unavailable) whose related_fact_ids list the inputs, plus config hash, as-of date and a rank. Ties break alphabetically. Same inputs and config always give byte-identical output.
Complementary discrete screen: a Piotroski-style pass/fail checklist as a second, outlier-proof view (open question 2).
No LLM anywhere in scoring.

## 3. Test cases (the point of this priority)
S1 Determinism: shuffled input order gives identical scores and ranks.
S2 Config hash changes when any weight changes; output records it.
S3 Weights file must sum to 1.0 per factor group and overall, else error.
S4 Monotonic: raising a higher-is-better metric for one name never lowers its score.
S5 Negative or zero earnings: P/E invalid ("not meaningful"), never scored as cheap.
S6 P/E above the NM cap is excluded from normalisation bounds but the name stays in the universe.
S7 Unit error: one name's ROE reported as 18 instead of 0.18 is flagged by validity bounds, and the other names' ranks do not move.
S8 Missing value is not treated as zero: removing a metric changes coverage, not the score of unrelated names.
S9 Coverage under 60% for a factor gives `unavailable` with reason, not a guess.
S10 Fewer than 2 valid factors gives `abstain`.
S11 Outlier robustness: adding one absurd outlier name (P/E 10000) changes no other name's rank by more than 1 place.
S12 Stale facts (older than a configured age) are flagged and excluded from the score.
S13 Sector group of 7 falls back to universe with the visible flag; group of 8 does not.
S14 Bank fixture is scored only on the bank metric set.
S15 Rank-change guard: re-scoring after replacing one name's data with a corrupted version reports which names moved and why (a diff report), and fails a threshold test if more than k ranks move.
S16 Every output number maps to input fact_ids (provenance), and unavailable scores carry reasons.
S17 Ties broken alphabetically and stably.
S18 No score exists without the not-advice disclaimer in rendered output.
S19 Leakage guard: scoring as of a past date uses only facts public by that date (reuses availability filter).
S20 Golden test: a small fixed universe with hand-computed percentile scores matches to 2 decimals.

## 4. Open questions for you
1. Investor horizon: long-term fundamentals (months to years) or shorter swing timing? It decides whether momentum is a core factor or a side flag.
2. Add a Piotroski-style 9-point pass/fail checklist next to the 0-100 score?
3. Default universe: my 30-name list (Nifty 50 constituents file would need a source I have not verified).

## 5. Next
On approval: write the plan (tasks, signatures, tests) and build test-first, as for the fact model.
