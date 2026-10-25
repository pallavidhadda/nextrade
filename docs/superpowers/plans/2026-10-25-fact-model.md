# Fact Model (indiafacts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `indiafacts`, a Python package that turns Indian-ticker financial data into typed Facts with period, unit, source, basis and availability date, detects gaps, and renders only Facts.

**Architecture:** Pydantic models (Fact, Entity, FactSet) sit at the core. Pure functions handle fiscal calendar, availability, gap detection, TTM and reconciliation. One Yahoo adapter feeds the core, and a renderer accepts only Facts. No LLM calls anywhere. An iXBRL importer is a later task that plugs in as a second adapter.

**Tech Stack:** Python 3.12, pydantic v2, pandas, yfinance, pytest, ixbrlparse (Task 9 only). Package lives in `/Users/apple/Desktop/REA/Trading-agents/indiafacts/`, outside the upstream TradingAgents tree.

**Spec:** `docs/2026-10-25-fact-model-spec.md` (test IDs F1–F22 and A1–A3 refer to it). Test plan: `docs/2026-10-25-test-plan.md`.

## Global Constraints
- Research/education only; the not-advice disclaimer ends every rendered output.
- Money as `Decimal`; display crore = 1e7, lakh crore = 1e12, symbol "₹".
- India FY = 1 Apr to 31 Mar; quarter ends 30 Jun, 30 Sep, 31 Dec, 31 Mar.
- Availability deadline: +45 days for Q1–Q3, +60 days for Q4 and FY; kind `deadline_estimate`; boundary inclusive (`available_from <= as_of` is public).
- Tolerances: price reconciliation 1%; cross-source conflict 5%; retries 3.
- A Fact with status other than `ok` must have a non-empty `reason`.
- Never guess ISIN, exchange codes or basis; Yahoo basis is `unknown`.
- No API keys in Facts, logs, cache or output. Tests run offline from fixtures; live tests marked `live` and excluded by default.

## Review Focus
- Ticker typed lower-case, padded with spaces, or as `.BO`: must normalise to one canonical symbol, never raise an unhandled error (Task 4).
- Yahoo returns NaN, not None, for missing cells: must become status `unavailable`, never a number (Task 4).
- Loss-making quarter or negative equity: negative values must flow through TTM, growth and ratios without crashing; growth from a negative or zero base is `unavailable("base not positive")` (Task 5).
- `as_of` equal to `available_from`, and `as_of` before every period: boundary is inclusive, and empty results print "no data", not an exception (Task 3).
- Duplicate or unsorted period columns from the vendor: deduplicate by period_end, and flag a `conflict` if the values differ (Task 5).

## File Structure
- `pyproject.toml`: package metadata, pytest config with `live` marker.
- `indiafacts/models.py`: Fact, Entity, FactSet, enums.
- `indiafacts/calendar.py`: fiscal labels, expected quarter sequence.
- `indiafacts/units.py`: crore/lakh-crore formatting.
- `indiafacts/availability.py`: available_from, as-of filter.
- `indiafacts/yahoo.py`: adapter, retry, metric mapping.
- `indiafacts/analysis.py`: gap detection, TTM, reconciliation.
- `indiafacts/render.py`: Fact-only renderer and disclaimer.
- `indiafacts/cli.py`: `python -m indiafacts RELIANCE.NS --as-of YYYY-MM-DD`.
- `indiafacts/ixbrl.py`: Task 9.
- `tests/`: one test file per module, `tests/fixtures/reliance_quarterly.py` holds the spec's Fixture Q.

---

### Task 1: Project scaffold and core models

**Files:** Create `pyproject.toml`, `indiafacts/__init__.py`, `indiafacts/models.py`, `tests/test_models.py`. Also run `git init` at the project root and add `.gitignore` containing `.env`, `.venv/`, `__pycache__/`.

**Interfaces:**
- Produces: `Status` (str enum: ok, unavailable, gap, stale, conflict, unverified), `PeriodType` (Q, FY, TTM, point), `Basis` (consolidated, standalone, unknown), `AvailabilityKind` (filed, deadline_estimate, unknown); `Fact` (fields per spec section 3; `Fact.make(...)` classmethod computing `fact_id` as sha256 hex[:16] of entity|metric|period_end|period_type|source); `Entity`; `FactSet(entity: Entity, facts: list[Fact], retrieved_at: datetime)` with `.by_metric(name) -> list[Fact]`.

- [ ] **Step 1: Write failing tests** in `tests/test_models.py`: `test_non_ok_fact_requires_reason` (F13: constructing `Fact` with `status="gap"` and `reason=""` raises `ValueError`); `test_unavailable_fact_has_null_value`; `test_fact_id_is_stable` (same inputs, same id; different source, different id); `test_entity_identifiers_default_unavailable` (F15: `Entity.from_ticker("RELIANCE.NS").isin.status == "unavailable"` and reason non-empty).
- [ ] **Step 2:** Run `pytest tests/test_models.py -v`; expect FAIL (import error).
- [ ] **Step 3:** Implement the models with pydantic validators for the reason and null-value rules; `Entity.from_ticker` uppercases and strips the input, and sets nse_symbol from the part before `.NS`.
- [ ] **Step 4:** Run the tests; expect PASS.
- [ ] **Step 5:** Commit `feat: core fact models`.

### Task 2: Fiscal calendar and units

**Files:** Create `indiafacts/calendar.py`, `indiafacts/units.py`, `tests/test_calendar.py`, `tests/test_units.py`.

**Interfaces:**
- Produces: `fiscal_label(period_end: date, period_type: PeriodType) -> str`; `expected_quarter_ends(first: date, last: date) -> list[date]` (inclusive, ascending); `format_inr(value: Decimal) -> str`.

- [ ] **Step 1: Write failing tests:** F6 `test_fiscal_labels` (2026-06-30 Q -> "Q1 FY27"; 2026-03-31 Q -> "Q4 FY26"; 2026-03-31 FY -> "FY26"; 2025-12-31 Q -> "Q3 FY26"); `test_expected_quarter_ends_spans_gap` (2025-03-31 to 2026-06-30 yields 6 dates including 2025-09-30); F5 `test_format_inr` (Decimal("209460000000") -> "₹20,946 cr"; Decimal("16103642234880") -> "₹16.10 lakh cr"; Decimal("-83370000000") -> "-₹8,337 cr"); `test_format_inr_small_values` (Decimal("15.48") -> "₹15.48").
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Rule for `format_inr`: >= 1e12 shows lakh crore with 2 decimals; >= 1e7 shows crore with thousands separators and no decimals; below that plain rupees with 2 decimals.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat: fiscal calendar and INR formatting`.

### Task 3: Availability and as-of filtering

**Files:** Create `indiafacts/availability.py`, `tests/test_availability.py`.

**Interfaces:**
- Consumes: Task 1 models, Task 2 `fiscal_label`.
- Produces: `available_from(period_end: date, period_type: PeriodType) -> date`; `with_availability(facts: list[Fact], filing_dates: dict[date, date] | None = None) -> list[Fact]`; `filter_as_of(facts: list[Fact], as_of: date) -> tuple[list[Fact], list[Fact]]` returning (public, not_yet_public).

- [ ] **Step 1: Write failing tests:** F7 (Jun-26 Q -> 2026-08-14; Mar-26 Q -> 2026-05-30; Mar-26 FY -> 2026-05-30; kind `deadline_estimate`); F8 (as_of 2026-08-01 puts Jun-26 in not_yet_public and Mar-26 in public); F9 (a filing date of 2026-07-18 for Jun-26 sets available_from and kind `filed`); `test_boundary_inclusive` (as_of == available_from is public); `test_as_of_before_all_periods_returns_empty_not_error`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement with `timedelta`; `with_availability` returns new Facts (models are frozen).
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat: availability dates and as-of filter`.

### Task 4: Yahoo adapter

**Files:** Create `indiafacts/yahoo.py`, `tests/test_yahoo.py`, `tests/fixtures/reliance_quarterly.py` (Fixture Q from the spec as a pandas DataFrame; periods Jun-26, Mar-26, Dec-25, Jun-25, Mar-25, no Sep-25; rows: Net Income Common Stockholders, EBITDA, Interest Expense, Diluted EPS).

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `fetch_facts(ticker: str, as_of: date | None = None, client: YahooClient | None = None) -> FactSet`, where `YahooClient` is a Protocol with `quarterly_income_stmt() -> DataFrame | None`, `info() -> dict`, so tests inject fakes. `METRIC_MAP: dict[str, str]` maps Yahoo row names to metric names (net_income, ebitda, interest_expense, eps_diluted, revenue). `RETRY_COUNT = 3`.

- [ ] **Step 1: Write failing tests:** F16 `test_empty_response_retried_then_unresolved` (fake client returns None 3 times; assert 3 calls, entity status unresolved, rendered facts contain no business-description text); F17 `test_transient_failure_then_success`; F18 `test_basis_is_unknown`; F19 `test_missing_overview_field_becomes_unavailable_fact` (info lacks returnOnEquity -> Fact metric roe, status unavailable, reason contains "not provided by Yahoo"); `test_nan_cell_becomes_unavailable_not_number`; `test_ticker_normalisation` (" reliance.ns " and "RELIANCE.NS" give the same entity; ".BO" accepted); `test_no_secrets_in_facts` (F22: set env `GOOGLE_API_KEY=SECRET123` and assert it appears nowhere in `FactSet.model_dump_json()`).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement `fetch_facts`: retry loop with injectable sleep (no real sleeping in tests), map rows via `METRIC_MAP`, convert values to Decimal, call `with_availability`, and apply `filter_as_of` when `as_of` is given. A default `YahooClient` wraps yfinance and is the only code that imports it.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat: yahoo adapter with retries and explicit gaps`.

### Task 5: Gap detection and TTM

**Files:** Create `indiafacts/analysis.py` (gaps, TTM), `tests/test_analysis.py`.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `detect_gaps(facts: list[Fact], metric: str) -> list[Fact]` (gap Facts, one per missing quarter end); `ttm(facts: list[Fact], metric: str, as_of_period: date) -> Fact`; `growth_yoy(facts: list[Fact], metric: str, period_end: date) -> Fact`.

- [ ] **Step 1: Write failing tests:** F1 (Fixture Q yields exactly one gap, 2025-09-30, status gap, reason mentions the source); F2 (TTM net income as of 2026-06-30 is `unavailable` and reason contains "2025-09-30"); F3 (synthetic four consecutive quarters 10, 20, 30, 40 sum to 100.00 exactly, status ok, `related_fact_ids` has four ids); F4 (vendor TTM stays status `unverified`); F21 (3 quarters -> unavailable, reason "fewer than 4 quarters returned"); `test_negative_values_flow_through_ttm`; `test_growth_from_negative_base_unavailable` (reason "base not positive"); `test_duplicate_period_columns_conflict` (same period_end twice with different values -> one Fact with status conflict).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement using `expected_quarter_ends`; flows sum, stock metrics (balance sheet) take the latest value.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat: gap detection and ttm`.

### Task 6: Reconciliation

**Files:** Modify `indiafacts/analysis.py`; create `tests/test_reconcile.py`.

**Interfaces:**
- Produces: `reconcile_price(price: Fact, pe: Fact, eps: Fact, tol: float = 0.01) -> Fact`; `reconcile_sources(a: Fact, b: Fact, tol: float = 0.05) -> list[Fact]`.

- [ ] **Step 1: Write failing tests:** F10 (1190.00, 21.550163, 55.22 -> status ok); F11 (EPS 50.00 -> status conflict, reason shows both implied and actual price); F12 (100 vs 108 -> two Facts, both conflict, spread 8%; 100 vs 103 -> ok); `test_zero_eps_unavailable`.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS. **Step 5:** Commit `feat: reconciliation checks`.

### Task 7: Fact-only renderer

**Files:** Create `indiafacts/render.py`, `tests/test_render.py`.

**Interfaces:**
- Produces: `render(factset: FactSet, as_of: date | None = None) -> str` with sections: header (entity, basis, as-of), data-quality banner, quarterly table in ₹ crore with `unav` cells for gaps, "Could not check" list, "Not yet public" list, disclaimer. `DISCLAIMER` constant.

- [ ] **Step 1: Write failing tests:** F14 `test_render_rejects_bare_numbers` (passing a float list raises `TypeError`); property test with hypothesis or a seeded random generator: every number printed in a table cell maps to a fact_id in the footnote index; F20 `test_disclaimer_present`; `test_basis_unknown_printed`; `test_sep25_gap_shown_as_unav`; `test_not_yet_public_listed`.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS. **Step 5:** Commit `feat: fact-only renderer`.

### Task 8: CLI and acceptance replay

**Files:** Create `indiafacts/cli.py`, `indiafacts/__main__.py`, `tests/test_acceptance.py`.

**Interfaces:**
- Consumes: Tasks 1–7. Produces: `main(argv: list[str]) -> int`; usage `python -m indiafacts TICKER [--as-of YYYY-MM-DD]`.

- [ ] **Step 1: Write failing tests:** A1 offline using Fixture Q through `main` with a fake client (output contains the Sep-25 gap, "TTM net income" unavailable with its reason, P/E x EPS reconciliation ok, "basis: unknown", the disclaimer, and no bare unlabeled numbers); A2 with `--as-of 2026-08-01` (Jun-26 under "Not yet public", Mar-26 marked "deadline estimate"). Mark one test `live` that runs the real RELIANCE.NS fetch.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement CLI wiring. **Step 4:** Run offline tests: all of F1–F22 and A1–A2 pass. **Step 5:** Run the live test once manually and record the output in `docs/`. Commit `feat: cli and acceptance replay`.

### Task 9: iXBRL import (starts when the sample file is in `samples/`)

**Files:** Create `indiafacts/ixbrl.py`, `tests/test_ixbrl.py`; add dependency `ixbrlparse`.

**Interfaces:**
- Produces: `facts_from_ixbrl(path: Path) -> FactSet`, with `source="nse_ixbrl"`, `availability_kind="filed"`, basis read from the filing's own tags (else `unknown`).

- [ ] **Step 1:** Inspect the sample file and record in the test module docstring: company, period, basis tag, filing timestamp, scale. Write failing tests asserting the file's real values (net income, revenue), period type, units, and that `available_from` equals the filing timestamp date.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement with ixbrlparse (contexts give periods, units, scale applied). **Step 4:** Run; expect PASS. **Step 5:** Commit `feat: ixbrl import`.

---

## Self-review
- Spec coverage: F1–F4, F21 (Task 5); F5, F6 (Task 2); F7–F9 (Task 3); F10–F12 (Task 6); F13, F15 (Task 1); F14, F20 (Task 7); F16–F19, F22 (Task 4); A1, A2 (Task 8). A3 (all tests pass offline) is the Task 8 gate. Identity (B8) is covered in Tasks 1 and 4.
- Names used across tasks match the Interfaces blocks (`fetch_facts`, `detect_gaps`, `ttm`, `render`, `filter_as_of`).
- Deferred or out of scope: factor scoring, thesis ledger, backtests, front end, exchange-filing automation.
- Calls to check: package name `indiafacts`; Decimal values; hypothesis library optional; `git init` at the project root.
