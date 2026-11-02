"""Read a raw NSE/BSE XBRL instance (INDAS_*.xml, in-bse-fin taxonomy) into typed Facts, with the filing's own provenance.
Values are in rupees (the 'rounding' label only describes the display). Quarter values (context OneD) and balance sheet (OneI) are
trusted; year-to-date values (FourD) are kept as 'unverified' because the file's context dates repeat the quarter's dates, so their
year meaning rests on the BSE id convention until a results page confirms it. Education only; not financial advice."""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from indiafacts.calendar import fiscal_label
from indiafacts.models import (AvailabilityKind, Basis, Entity, Fact, FactSet, FilingMeta, Identifier, PeriodType, Status)

SOURCE = "nse_xbrl"
_TS = re.compile(r"_(\d{2})(\d{2})(\d{4})\d{6}\.xml$", re.I)
_XBRLI = "{http://www.xbrl.org/2003/instance}"

# concept -> (metric, unit kind)
_PL = {
    "RevenueFromOperations": ("revenue", "money"), "OtherIncome": ("other_income", "money"), "Income": ("total_income", "money"),
    "FinanceCosts": ("interest_expense", "money"), "DepreciationDepletionAndAmortisationExpense": ("depreciation", "money"),
    "Expenses": ("total_expenses", "money"), "ProfitBeforeTax": ("profit_before_tax", "money"), "TaxExpense": ("total_tax", "money"),
    "ProfitLossForPeriod": ("net_income_total", "money"), "ProfitOrLossAttributableToOwnersOfParent": ("net_income", "money"),
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations": ("eps_basic", "per_share"),
    "DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations": ("eps_diluted", "per_share"),
    "DebtEquityRatio": ("debt_equity_ratio", "ratio"), "DebtServiceCoverageRatio": ("debt_service_coverage_ratio", "ratio"),
    "InterestServiceCoverageRatio": ("interest_service_coverage_ratio", "ratio"),
}
_CASH = {
    "CashFlowsFromUsedInOperatingActivities": "operating_cash_flow",
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": "capex_ppe",
    "CashFlowsFromUsedInInvestingActivities": "investing_cash_flow",
    "CashFlowsFromUsedInFinancingActivities": "financing_cash_flow",
}
_BALANCE = {"Assets": "total_assets", "Liabilities": "total_liabilities", "Equity": "total_equity",
            "EquityAttributableToOwnersOfParent": "equity_owners", "CashAndCashEquivalents": "cash_and_equivalents"}


def _dec(text: str) -> Decimal | None:
    try:
        return Decimal(text.strip())
    except (InvalidOperation, AttributeError):
        return None


def _iso(text: str | None) -> date | None:
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None


def facts_from_nse_xbrl(path: Path, retrieved_at: datetime | None = None) -> FactSet:
    raw = Path(path).read_bytes()
    head = raw.lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise ValueError("refusing an XBRL file that contains a DOCTYPE or entity declaration")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"not an NSE XBRL instance: {exc}") from exc
    if not root.tag.endswith("}xbrl"):
        raise ValueError("not an NSE XBRL instance: root element is not xbrl")
    now = retrieved_at or datetime.now(timezone.utc)

    contexts: dict[str, dict] = {}
    for c in root.iter(f"{_XBRLI}context"):
        per = c.find(f"{_XBRLI}period")
        if per is None:
            continue
        contexts[c.get("id", "")] = {
            "start": _iso((per.findtext(f"{_XBRLI}startDate"))), "end": _iso(per.findtext(f"{_XBRLI}endDate")),
            "instant": _iso(per.findtext(f"{_XBRLI}instant")),
            "dim": c.find(f"{_XBRLI}scenario") is not None or c.find(f"{_XBRLI}segment") is not None or c.find(f"{_XBRLI}entity/{_XBRLI}segment") is not None,
        }
    vals: dict[tuple[str, str], str] = {}
    for el in root:
        ctx = el.get("contextRef")
        if ctx and ctx in contexts and not contexts[ctx]["dim"] and "}" in el.tag:
            vals.setdefault((el.tag.split("}")[1], ctx), (el.text or "").strip())
    if not vals or "OneD" not in contexts:
        raise ValueError("not an NSE XBRL instance: no results contexts found")

    def one(concept: str, ctx: str = "OneD") -> str:
        return vals.get((concept, ctx), "")

    currency = one("DescriptionOfPresentationCurrency") or "INR"
    if currency != "INR":
        raise ValueError(f"unsupported presentation currency {currency!r}")
    q = contexts["OneD"]
    if q["start"] is None or q["end"] is None:
        raise ValueError("not an NSE XBRL instance: quarter period missing")
    symbol = one("Symbol") or (root.find(f".//{_XBRLI}identifier").text or "").strip()
    basis = {"consolidated": Basis.consolidated, "standalone": Basis.standalone}.get(one("NatureOfReportStandaloneConsolidated").lower(), Basis.unknown)
    audit_raw = one("WhetherResultsAreAuditedOrUnaudited").lower()
    audit = "unaudited" if "unaudited" in audit_raw else "audited" if "audited" in audit_raw else ""
    m = _TS.search(Path(path).name)
    avail = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
    document = Path(path).name
    filing_id = hashlib.sha256(f"{symbol}|{document}|{q['end']}|{avail}".encode()).hexdigest()[:16]
    ticker = f"{symbol}.NS"
    scrip = one("ScripCode")
    entity = Entity(ticker_input=document, ticker=ticker, nse_symbol=Identifier(value=symbol, status=Status.ok),
                    bse_code=Identifier(value=scrip, status=Status.ok) if scrip else Identifier.missing("not in filing"),
                    isin=Identifier.missing("not in the XBRL file"), name=one("NameOfTheCompany") or None)
    meta = FilingMeta(filing_id=filing_id, document=document, source_type="nse_xbrl_instance", entity_symbol=symbol, filing_date=avail,
                      period_start=q["start"], period_end=q["end"], period_type="Q", basis=basis.value, audit_status=audit,
                      rounding=one("LevelOfRoundingUsedInFinancialStatements"), currency=currency)
    end = q["end"]
    fy_start = end.replace(year=end.year - 1) + timedelta(days=1)
    kind_unit = {"money": "INR", "per_share": "INR_per_share", "ratio": "ratio"}
    facts: list[Fact] = []

    def add(metric, concept, ctx, ptype, start, stop, unit, status=Status.ok, reason=""):
        v = _dec(vals.get((concept, ctx), ""))
        if v is None:
            return
        facts.append(Fact.make(
            entity_key=ticker, metric=metric, value=v, unit=unit, period_start=start, period_end=stop, period_type=ptype,
            fiscal_label=fiscal_label(stop, ptype.value) if ptype != PeriodType.point else None, basis=basis, source=SOURCE,
            source_field=f"in-bse-fin:{concept} [{audit or 'audit status unknown'}]", retrieved_at=now, available_from=avail,
            availability_kind=AvailabilityKind.filed if avail else AvailabilityKind.unknown, status=status, reason=reason,
            evidence=f"{document} | in-bse-fin:{concept} @ {ctx}", reported_value=v, reported_unit=unit, audit_status=audit, filing_id=filing_id))

    year_note = "year-to-date value read from context FourD; the file's own dates repeat the quarter, so confirm against the results page"
    have_owner = ("ProfitOrLossAttributableToOwnersOfParent", "OneD") in vals
    for concept, (metric, kind) in _PL.items():
        add(metric, concept, "OneD", PeriodType.Q, q["start"], end, kind_unit[kind])
        add(metric, concept, "FourD", PeriodType.FY, fy_start, end, kind_unit[kind], Status.unverified, year_note)
    if not have_owner:                                                                      # standalone filings have no owners' split
        add("net_income", "ProfitLossForPeriod", "OneD", PeriodType.Q, q["start"], end, "INR")
        add("net_income", "ProfitLossForPeriod", "FourD", PeriodType.FY, fy_start, end, "INR", Status.unverified, year_note)
    for concept, metric in _CASH.items():
        add(metric, concept, "FourD", PeriodType.FY, fy_start, end, "INR", Status.unverified, year_note)
    inst = contexts.get("OneI")
    if inst and inst["instant"]:
        for concept, metric in _BALANCE.items():
            add(metric, concept, "OneI", PeriodType.point, None, inst["instant"], "INR")
    if not facts:
        raise ValueError("not an NSE XBRL instance: no financial values recognised")
    return FactSet(entity=entity, facts=facts, retrieved_at=now, filings=[meta])
