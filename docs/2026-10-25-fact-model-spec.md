# Fact model and gap detection — build spec + test cases (DRAFT for approval)
Research/education only; not financial, investment or trading advice. Nothing is built.
Supports Priority 1: every reported number has a traceable source and a clear period, or is explicitly marked unavailable.

## 1. Intent
Today a number can reach a report with no period, unit, source or basis, and a missing quarter disappears silently (RELIANCE.NS: Sep-25 absent from the live Yahoo table, unflagged). This module makes every number a typed Fact and makes absence a first-class, explained value.

## 2. Scope
In: Fact and Entity types, Yahoo adapter, India fiscal-calendar logic, gap detection, TTM reconstruction, availability dates, reconciliation checks, a renderer that only accepts Facts.
Out (later): factor scoring (P2), thesis ledger (P3), backtesting (P4), exchange-filing adapter, front end, any LLM call.
Anti-goals: guessing an ISIN or a basis; filling a gap with an estimate shown as data; a report that prints a number not backed by a Fact.

## 3. Data model
Entity: nse_symbol, bse_code, isin, name, each `value | unavailable(reason)`; `ticker_input`; `resolved_via`.
Fact: fact_id (stable hash of entity, metric, period, source), metric, value (decimal), unit (INR | ratio | percent | shares | INR_per_share), period_start, period_end, period_type (Q | FY | TTM | point), fiscal_label (e.g. "Q1 FY27", "FY26"), basis (consolidated | standalone | unknown), source, source_field, retrieved_at, available_from, availability_kind (filed | deadline_estimate | unknown), status (ok | unavailable | gap | stale | conflict | unverified), reason (required unless status=ok), related_fact_ids.
Rule: a Fact with status != ok must carry a non-empty reason. A `unavailable` Fact has value = null.

## 4. Behaviours
B1 India fiscal calendar: FY runs 1 Apr to 31 Mar. Quarter ends 30 Jun (Q1), 30 Sep (Q2), 31 Dec (Q3), 31 Mar (Q4). Label e.g. period_end 2026-06-30 -> "Q1 FY27".
B2 Gap detection: for each statement, build the expected quarter-end sequence between earliest and latest returned period; any missing end becomes a Fact with status `gap` and reason "period not returned by <source>". Same for annual.
B3 TTM: computed only from four consecutive, non-gap quarters (sum for flows; latest for stocks). With a gap, TTM Fact status = unavailable, reason names the missing period. A vendor-stated TTM is kept as a separate Fact with status `unverified` and `related_fact_ids` to the quarters it could not be checked against.
B4 Availability: `available_from` = period_end + 45 days for Q1–Q3, + 60 days for Q4 and FY (SEBI LODR Reg 33 deadlines per secondary sources; verify against current text), kind `deadline_estimate`. A real filing date, when an adapter supplies one, overrides and sets kind `filed`.
B5 As-of filter: facts with available_from > as_of are excluded, and each exclusion is listed under "not yet public".
B6 Basis: Yahoo-sourced statements default to `unknown`; never inferred as consolidated.
B7 Reconciliation: price vs P/E x EPS within 1%; two sources for the same metric and period differing by more than 5% -> both kept, status `conflict`, spread shown.
B8 Identity: ISIN and exchange codes are `unavailable("no identifier source configured")` until a source exists; an empty vendor response triggers up to 3 retries, then entity status `unresolved` with the message "no data returned; ticker may have changed".
B9 Rendering: the renderer accepts only Facts. Numbers format as "₹20,946 cr" (crore = 1e7) with period and source in the cell or footnote.
B10 Every output ends with the not-advice disclaimer.

## 5. Interfaces (names are proposals)
`resolve_entity(ticker) -> Entity`; `fetch_facts(entity, as_of) -> FactSet` (includes gap/unavailable Facts); `ttm(factset, metric) -> Fact`; `reconcile(factset) -> list[Fact]`; `render(factset, facts) -> str`.

## 6. Test cases (fixtures use the real 2026-10-25 RELIANCE.NS quarterly data, in ₹; crore = 1e7)
Fixture Q: net income Jun-26 209,460,000,000; Mar-26 169,710,000,000; Dec-25 186,450,000,000; Jun-25 269,940,000,000; Mar-25 194,070,000,000; Sep-25 absent.
F1 Gap: Fixture Q yields exactly one gap Fact, period_end 2025-09-30, status gap.
F2 TTM with gap: TTM net income as of Jun-26 is unavailable, reason mentions 2025-09-30; no number is shown.
F3 TTM without gap: a synthetic four-consecutive-quarter set sums correctly to the cent.
F4 Vendor TTM: Yahoo "Net Income 747,269,980,160" is stored with status unverified, never ok.
F5 Units: 209,460,000,000 INR renders "₹20,946 cr"; 16,103,642,234,880 renders "₹16.10 lakh cr".
F6 Fiscal labels: 2026-06-30 -> "Q1 FY27"; 2026-03-31 quarterly -> "Q4 FY26"; annual 2026-03-31 -> "FY26".
F7 Availability: Jun-26 quarter available_from 2026-08-14; Mar-26 quarter/FY 2026-05-30; kind deadline_estimate.
F8 As-of filter: as_of 2026-08-01 excludes the Jun-26 quarter and lists it under "not yet public"; includes Mar-26.
F9 Override: supplying a filing date of 2026-07-18 for Jun-26 sets available_from to it and kind filed.
F10 Reconcile OK: price 1190.00, P/E 21.550163, EPS 55.22 passes at 1%.
F11 Reconcile fail: EPS 50.00 with the same price flags a mismatch Fact.
F12 Conflict: two sources, revenue 100 vs 108 (8%) -> status conflict, both values kept; 100 vs 103 passes.
F13 Reason rule: constructing a non-ok Fact without a reason raises.
F14 Renderer: passing a bare float to render raises; property test over random FactSets proves every printed number maps to a fact_id.
F15 Identity: ISIN is `unavailable` with reason, never a fabricated string.
F16 Empty vendor: empty response retried 3 times (fake clock), then unresolved entity; the output contains no filler sentence about the company's business.
F17 Transient failure: first call raises, second succeeds -> data returned, retry logged.
F18 Basis: Yahoo statements print "basis: unknown"; no consolidated claim anywhere.
F19 Missing overview fields: ROE absent from vendor response -> Fact status unavailable, reason "not provided by Yahoo", and the digest lists it under "Could not check".
F20 Disclaimer present in every rendered output.
F21 Bank fixture (HDFCBANK.NS, 2 income quarters): fewer than 4 quarters -> TTM unavailable, reason "fewer than 4 quarters returned".
F22 Secrets: API keys never appear in Fact fields, logs or rendered output.

## 7. Acceptance
A1 RELIANCE.NS live replay: output shows the Sep-25 gap, TTM net income unavailable with its reason, P/E x EPS reconciliation OK, unit/basis labels on every figure, no unlabeled number.
A2 Re-run dated 2026-08-01: Jun-26 listed as not yet public; Mar-26 shown with "deadline estimate" note.
A3 All 22 tests pass offline from fixtures; live tests are separate and optional.

## 8. Calls I made (check these)
Own package outside the upstream TradingAgents tree (keeps their code untouched; location settled at plan stage); Python 3.12, Pydantic models, Decimal values; Yahoo as the only adapter in v1; deadline-based availability; 1% and 5% tolerances; 3 retries.

## 9. Left to the builder
Exact module layout, formatting details, fixture capture method, how the adapter normalises Yahoo row names to metric names (a mapping table to be reviewed).

## 10. Risks
Yahoo field names and coverage can change without notice; deadline dates are estimates; Yahoo's "unusual items" and TTM definitions are unverified; Indian companies' consolidated/standalone choice can't be read from Yahoo.
