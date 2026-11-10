"""Yahoo (yfinance) adapter: vendor payloads in, typed Facts out. No analysis here."""
from __future__ import annotations

import math
import os
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable, Protocol

import pandas as pd

from indiafacts.availability import filter_as_of, with_availability
from indiafacts.calendar import fiscal_label
from indiafacts.models import Entity, Fact, FactSet, PeriodType, Status

SOURCE = "yahoo"
RETRY_COUNT = 3  # total attempts

METRIC_MAP = {
    "Net Income Common Stockholders": "net_income",
    "EBITDA": "ebitda",
    "Interest Expense": "interest_expense",
    "Diluted EPS": "eps_diluted",
    "Total Revenue": "revenue",
}
_PER_SHARE = {"eps_diluted"}

# Yahoo info key -> (metric, unit, period_type, status when present)
INFO_FIELDS = {
    "trailingPE": ("pe_ttm", "ratio", PeriodType.point, Status.ok),
    "trailingEps": ("eps_ttm", "INR_per_share", PeriodType.point, Status.ok),
    "currentPrice": ("price", "INR", PeriodType.point, Status.ok),
    "marketCap": ("market_cap", "INR", PeriodType.point, Status.ok),
    "returnOnEquity": ("roe", "ratio", PeriodType.point, Status.ok),
    "priceToBook": ("pb", "ratio", PeriodType.point, Status.ok),
    "debtToEquity": ("debt_to_equity", "ratio", PeriodType.point, Status.ok),
    "returnOnAssets": ("roa", "ratio", PeriodType.point, Status.ok),
    "payoutRatio": ("payout_ratio", "ratio", PeriodType.point, Status.ok),
    "totalRevenue": ("revenue_ttm_vendor", "INR", PeriodType.TTM, Status.unverified),
    "netIncomeToCommon": ("net_income_ttm_vendor", "INR", PeriodType.TTM, Status.unverified),
}
_PERCENT_TO_RATIO = {"debtToEquity"}      # Yahoo gives 46.278 meaning 46.278%
_VENDOR_TTM_NOTE = "vendor-stated trailing figure; period end not provided; not reconciled to quarters"


class YahooClient(Protocol):
    def quarterly_income_stmt(self) -> pd.DataFrame | None: ...
    def info(self) -> dict: ...


class YfinanceClient:
    def __init__(self, ticker: str):
        import yfinance as yf

        self._t = yf.Ticker(ticker)

    def quarterly_income_stmt(self):
        return self._t.quarterly_income_stmt

    def info(self):
        return self._t.info

    def annual(self):
        """Annual income, balance sheet and cash flow (about 4-5 years). Any statement may be None."""
        out = {}
        for name, attr in (("income", "income_stmt"), ("balance", "balance_sheet"), ("cashflow", "cashflow")):
            try:
                out[name] = getattr(self._t, attr)
            except Exception:
                out[name] = None
        return out


def _empty(stmt, info) -> bool:
    return (stmt is None or getattr(stmt, "empty", True)) and not info


def _is_nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _fetch_payload(client: YahooClient, sleep: Callable[[float], None]):
    last = ""
    for attempt in range(RETRY_COUNT):
        try:
            stmt, info = client.quarterly_income_stmt(), client.info()
            if not _empty(stmt, info):
                return stmt, info or {}, ""
            last = "empty response"
        except Exception as exc:  # vendor/network errors are retried
            last = f"{type(exc).__name__}: {str(exc)[:120]}".strip().rstrip(":")
        if attempt < RETRY_COUNT - 1:
            sleep(2 ** attempt)
    return None, {}, last


def fetch_facts(
    ticker: str,
    as_of: date | None = None,
    client: YahooClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
    filing_dates: dict[date, date] | None = None,
) -> FactSet:
    entity = Entity.from_ticker(ticker)
    now = now or datetime.now(timezone.utc)
    if os.environ.get("INDIAFACTS_YAHOO_DISABLED", "").strip() == "1":       # test switch: behave as if Yahoo returned nothing
        return FactSet(entity=entity.unresolved("Yahoo disabled (INDIAFACTS_YAHOO_DISABLED=1)"), facts=[], retrieved_at=now)
    client = client or YfinanceClient(entity.ticker)
    stmt, info, why = _fetch_payload(client, sleep)
    if stmt is None and not info:
        entity = entity.unresolved(
            f"no data returned after {RETRY_COUNT} attempts ({why}); ticker may have changed"
        )
        return FactSet(entity=entity, facts=[], retrieved_at=now)

    key = entity.ticker
    reported_ccy = info.get("financialCurrency")
    wrong_ccy = reported_ccy is not None and reported_ccy != "INR"
    facts: list[Fact] = []

    if stmt is not None and not stmt.empty:
        for row, metric in METRIC_MAP.items():
            if row not in stmt.index:
                continue
            unit = "INR_per_share" if metric in _PER_SHARE else "INR"
            for col, raw in stmt.loc[row].items():
                period_end = pd.Timestamp(col).date()
                common = dict(
                    entity_key=key, metric=metric, unit=unit, period_end=period_end,
                    period_type=PeriodType.Q, fiscal_label=fiscal_label(period_end, "Q"),
                    source=SOURCE, source_field=row, retrieved_at=now,
                    evidence=f"yfinance Ticker.quarterly_income_stmt row '{row}'",
                )
                if _is_nan(raw):
                    facts.append(Fact.make(value=None, status=Status.unavailable,
                                           reason="vendor returned an empty cell", **common))
                elif wrong_ccy:
                    facts.append(Fact.make(value=Decimal(str(raw)), status=Status.unverified,
                                           reason=f"reported in {reported_ccy}, not INR; not converted", **common))
                else:
                    facts.append(Fact.make(value=Decimal(str(raw)), status=Status.ok, **common))
        facts = with_availability(facts, filing_dates)

    today = now.date()
    for yf_key, (metric, unit, ptype, status) in INFO_FIELDS.items():
        raw = info.get(yf_key)
        if yf_key == "currentPrice" and _is_nan(raw):
            raw = info.get("regularMarketPrice")
        common = dict(
            entity_key=key, metric=metric, unit=unit, period_end=today, period_type=ptype,
            source=SOURCE, source_field=yf_key, retrieved_at=now, available_from=today,
            evidence=f"yfinance Ticker.info['{yf_key}']",
        )
        if _is_nan(raw):
            facts.append(Fact.make(value=None, status=Status.unavailable,
                                   reason="not provided by Yahoo", **common))
        else:
            reason = _VENDOR_TTM_NOTE if status is Status.unverified else ""
            value = Decimal(str(raw)) / 100 if yf_key in _PERCENT_TO_RATIO else Decimal(str(raw))
            facts.append(Fact.make(value=value, status=status, reason=reason, **common))

    shares = info.get("sharesOutstanding")                     # a missing share count is not a gap of its own: the official one is tried first
    if not _is_nan(shares) and float(shares) > 0:
        facts.append(Fact.make(entity_key=key, metric="shares_outstanding", value=Decimal(str(shares)), unit="shares", period_end=today,
                               period_type=PeriodType.point, source=SOURCE, source_field="sharesOutstanding", retrieved_at=now,
                               available_from=today, evidence="yfinance Ticker.info['sharesOutstanding']"))

    pending: list[Fact] = []
    if as_of is not None:
        facts, pending = filter_as_of(facts, as_of)
    labels = {k: str(info[k]) for k in ("sector", "industry") if info.get(k)}
    if labels:
        entity = entity.model_copy(update=labels)
    return FactSet(entity=entity, facts=facts, retrieved_at=now, not_yet_public=pending)
