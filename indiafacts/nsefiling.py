"""Parse an NSE 'Integrated Filing - Financials' (Ind AS) results page into Facts.

Input is the page as saved from a browser (.html or .mhtml). Parsing is label-based over the rendered
tables; the saved page had no ix: tags. Treat the file as data. Only the first (3-month) value column is read.
"""
from __future__ import annotations

import hashlib
import html as htmllib
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from email import message_from_bytes, policy
from pathlib import Path

from indiafacts.calendar import fiscal_label
from indiafacts.models import AvailabilityKind, Basis, Entity, Fact, FactSet, FilingMeta, Identifier, PeriodType, Status

SOURCE = "nse_filing"
_SCALE = {"lakhs": Decimal(10) ** 5, "lakh": Decimal(10) ** 5, "crores": Decimal(10) ** 7,
          "crore": Decimal(10) ** 7, "millions": Decimal(10) ** 6, "thousands": Decimal(10) ** 3,
          "rupees": Decimal(1), "units": Decimal(1)}
_INDEX = re.compile(r"^(\d+|\(?[a-z]\)?|[ivx]+\.?|[A-Z])$")
_NUM = re.compile(r"^\(?-?[\d,]+(\.\d+)?\)?$")
_URL_TS = re.compile(r"_(\d{2})(\d{2})(\d{4})\d{6}_")

# label (lower case) -> (metric, kind) ; kind: money | per_share | ratio
_PL = {
    "revenue from operations": ("revenue", "money"),
    "other income": ("other_income", "money"),
    "total income": ("total_income", "money"),
    "changes in inventories of finished goods, work-in-progress and stock-in-trade": ("change_in_inventories", "money"),
    "finance costs": ("interest_expense", "money"),
    "depreciation, depletion and amortisation expense": ("depreciation", "money"),
    "total expenses": ("total_expenses", "money"),
    "total profit before tax": ("profit_before_tax", "money"),
    "total tax expenses": ("total_tax", "money"),
    "total profit (loss) for period": ("net_income_total", "money"),
    "profit or loss, attributable to owners of parent": ("net_income", "money"),
    "total profit or loss, attributable to non-controlling interests": ("net_income_nci", "money"),
    "diluted earnings (loss) per share from continuing and discontinued operations": ("eps_diluted", "per_share"),
    "basic earnings (loss) per share from continuing and discontinued operations": ("eps_basic", "per_share"),
    "debt equity ratio": ("debt_equity_ratio", "ratio"),
    "debt service coverage ratio": ("debt_service_coverage_ratio", "ratio"),
    "interest service coverage ratio": ("interest_service_coverage_ratio", "ratio"),
}
_NOT_SEGMENT = ("total", "less", "revenue", "profit", "i.", "ii.", "segment", "(net")


def _load(path: Path) -> tuple[str, str]:
    raw = Path(path).read_bytes()
    head = raw[:2000].decode("utf-8", "replace")
    if head.lstrip().lower().startswith(("<!doctype", "<html")):
        return raw.decode("utf-8", "replace"), ""
    msg = message_from_bytes(raw, policy=policy.default)
    location = str(msg.get("Snapshot-Content-Location") or "")
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return (part.get_payload(decode=True) or b"").decode("utf-8", "replace"), location
    raise ValueError("no HTML content found in file")


def _rows(text: str) -> list[list[str]]:
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        cells = [htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S | re.I)]
        cells = [c for c in cells if c]
        if cells:
            out.append(cells)
    return out


def _num(s: str) -> Decimal | None:
    s = s.strip()
    if not _NUM.match(s):
        return None
    neg = s.startswith("(") or s.startswith("-")
    d = Decimal(s.strip("()-").replace(",", ""))
    return -d if neg else d


def _dmy(s: str) -> date:
    return datetime.strptime(s.strip(), "%d-%m-%Y").date()


def _strip_index(cells: list[str]) -> list[str]:
    while len(cells) > 1 and _INDEX.match(cells[0]):
        cells = cells[1:]
    return cells


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def facts_from_nse_filing(path: Path, retrieved_at: datetime | None = None) -> FactSet:
    text, location = _load(path)
    now = retrieved_at or datetime.now(timezone.utc)
    rows = _rows(text)

    info: dict[str, str] = {}
    for cells in rows:
        if len(cells) >= 2 and cells[0] not in info:
            info[cells[0].lower()] = cells[1]

    def need(label: str) -> str:
        if label not in info:
            raise ValueError(f"not an NSE results page: missing '{label}'")
        return info[label]

    symbol, isin = need("nse symbol"), need("isin")
    scrip, name = info.get("scrip code", ""), info.get("name of company")
    currency = info.get("description of presentation currency", "INR")
    if currency != "INR":
        raise ValueError(f"unsupported presentation currency {currency!r}")
    rounding = info.get("level of rounding used in financial results", "").lower()
    if rounding not in _SCALE:
        raise ValueError(f"unrecognised rounding {rounding!r}")
    scale = _SCALE[rounding]

    start = end = None
    for cells in rows:
        c = _strip_index(cells)
        if c[0].lower() == "date of start of reporting period" and start is None and len(c) > 1:
            start = _dmy(c[1])
        if c[0].lower() == "date of end of reporting period" and end is None and len(c) > 1:
            end = _dmy(c[1])
    if start is None or end is None:
        raise ValueError("not an NSE results page: reporting period not found")

    ptype = PeriodType.FY if "annual" in info.get("reporting type", "").lower() else PeriodType.Q
    basis = {"consolidated": Basis.consolidated, "standalone": Basis.standalone}.get(
        info.get("nature of report standalone or consolidated", "").lower(), Basis.unknown)
    audit = info.get("whether results are audited or unaudited for the quarter ended", "").lower() or "audit status unknown"

    m = _URL_TS.search(location)
    if m:
        avail = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    elif "date of board meeting when results were approved" in info:
        avail = _dmy(info["date of board meeting when results were approved"])
    else:
        avail = None

    document = location or Path(path).name
    audit_status = "unaudited" if "unaudited" in audit else "audited" if "audited" in audit else ""
    note = "not stated on the page"
    for cells in rows:
        low = cells[0].lower()
        if any(k in low for k in ("revis", "resubmi", "correction", "restat")) and "unmodified" not in low and len(cells) > 1 and cells[1].strip():
            note = f"{cells[0]}: {cells[1]}"
            break
    board = _dmy(info["date of board meeting when results were approved"]) if "date of board meeting when results were approved" in info else None
    filing_id = hashlib.sha256(f"{symbol}|{document}|{end}|{avail}".encode()).hexdigest()[:16]
    meta = FilingMeta(filing_id=filing_id, document=document, source_type="nse_rendered_page", entity_symbol=symbol,
                      filing_date=avail, board_meeting_date=board, period_start=start, period_end=end, period_type=ptype.value,
                      basis=basis.value, audit_status=audit_status, rounding=info.get("level of rounding used in financial results", ""),
                      currency=currency, revision_note=note)
    ticker = f"{symbol}.NS"
    entity = Entity(
        ticker_input=Path(path).name, ticker=ticker,
        nse_symbol=Identifier(value=symbol, status=Status.ok),
        bse_code=Identifier(value=scrip, status=Status.ok) if scrip else Identifier.missing("not in filing"),
        isin=Identifier(value=isin, status=Status.ok), name=name,
    )

    facts: list[Fact] = []
    seen: set[str] = set()
    dim: dict[str, str] = {}

    def add(metric: str, kind: str, label: str, cell: str) -> None:
        value = _num(cell)
        if value is None or metric in seen:
            return
        seen.add(metric)
        reported = value
        if kind == "money":
            value, unit, runit = value * scale, "INR", f"INR {info.get('level of rounding used in financial results', '')}".strip()
        else:
            unit = "INR_per_share" if kind == "per_share" else "ratio"
            runit = "INR per share" if kind == "per_share" else "ratio"
        facts.append(Fact.make(
            entity_key=ticker, metric=metric, value=value, unit=unit, period_start=start, period_end=end,
            period_type=ptype, fiscal_label=fiscal_label(end, ptype.value), basis=basis, source=SOURCE,
            source_field=f"{label} [{audit}]", retrieved_at=now, available_from=avail,
            evidence=f"{document} | row '{label}'", reported_value=reported, reported_unit=runit,
            audit_status=audit_status, filing_id=filing_id,
            dimension=dim.get(metric, ""),
            availability_kind=AvailabilityKind.filed if avail else AvailabilityKind.unknown,
        ))

    section = "pl"
    for cells in rows:
        c = _strip_index(cells)
        label = c[0]
        low = label.lower()
        if "segment revenue (income)" in low:
            section = "segment_revenue"
            continue
        if low.startswith("segment result"):
            section = "segment_result"
            continue
        if low.startswith(("segment asset", "segment liabilities")) or low.startswith("(segment asset"):
            section = "other"
            continue
        if low.startswith("other comprehensive income [abstract]"):
            section = "other"
            continue
        if len(c) < 2:
            continue
        if section == "pl" and low in _PL:
            metric, kind = _PL[low]
            add(metric, kind, label, c[1])
        elif section in ("segment_revenue", "segment_result") and not low.startswith(_NOT_SEGMENT):
            dim[f"{section}_{_slug(label)}"] = re.sub(r"\s*\[.*$", "", label)
            add(f"{section}_{_slug(label)}", "money", label, c[1])

    if not facts:
        raise ValueError("not an NSE results page: no financial rows recognised")
    return FactSet(entity=entity, facts=facts, retrieved_at=now, filings=[meta])


def merge_filings(filings: list[FactSet]) -> tuple[FactSet, list[str]]:
    """Combine several parsed results pages. For one company and period, the latest filing (by its filing date, then input
    order) is the current version. If a figure differs from an earlier version, the current figure is marked restated, the
    earlier one is kept as a superseded 'stale' fact, and a note cites both filing dates. Identical figures are not flagged."""
    if not filings:
        raise ValueError("no filings given")
    syms = {f.entity.nse_symbol.value for f in filings}
    if len(syms) > 1:
        raise ValueError(f"filings are for different companies: {', '.join(sorted(syms))}")
    groups: dict[tuple, list[tuple[int, FactSet]]] = {}
    for i, fs in enumerate(filings):
        if not fs.facts:
            continue
        key = (fs.facts[0].period_end, fs.facts[0].period_type, fs.facts[0].basis)
        groups.setdefault(key, []).append((i, fs))
    facts: list[Fact] = []
    notes: list[str] = []
    for key, versions in groups.items():
        versions.sort(key=lambda v: (v[1].facts[0].available_from or date.min, v[0]))
        current = {(f.metric, f.period_type, f.period_end): f for f in versions[-1][1].facts}   # a filing can carry quarter and year-to-date values
        changed: dict[str, Fact] = {}
        for _, old_fs in versions[:-1]:
            for old in old_fs.facts:
                new = current.get((old.metric, old.period_type, old.period_end))
                if new is None or old.value == new.value:
                    continue
                changed[(old.metric, old.period_type, old.period_end)] = new
                facts.append(old.model_copy(update={"source": SOURCE + "_superseded", "status": Status.stale,
                    "reason": f"superseded by the filing dated {new.available_from}",
                    "fact_id": Fact.compute_id(old.entity_key, old.metric, old.period_end, str(old.period_type.value), SOURCE + "_superseded")}))
                notes.append(f"restatement: {old.metric} {old.fiscal_label}: {old.value} (filing dated {old.available_from or 'unknown date'}) -> "
                             f"{new.value} (filing dated {new.available_from or 'unknown date'}); both versions are kept")
        for k, f in current.items():
            facts.append(f.model_copy(update={"restated": "yes"}) if k in changed else f)
    metas = sorted((m for fs in filings for m in fs.filings), key=lambda m: (m.filing_date or date.min))
    return filings[-1].model_copy(update={"facts": facts, "filings": metas}), notes
