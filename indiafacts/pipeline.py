from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from indiafacts.analysis import add_gaps, check_ebitda, cross_check, growth_yoy, prefer_sources, reconcile_price, ttm
from indiafacts.availability import filter_as_of
from indiafacts.models import AvailabilityKind, Entity, FactSet, PeriodType, Status
from indiafacts.nsefiling import facts_from_nse_filing
from indiafacts.yahoo import fetch_facts

FLOW_METRICS = ("net_income", "ebitda", "interest_expense", "eps_diluted")


def _merge_entity(entity: Entity, filing: Entity) -> Entity:
    return entity.model_copy(update={
        "nse_symbol": filing.nse_symbol, "bse_code": filing.bse_code, "isin": filing.isin,
        "name": filing.name, "resolution": "resolved", "resolution_reason": "",
    })


def build_factset(ticker: str, as_of: date | None = None, client=None, sleep=time.sleep,
                  filing_path: Path | None = None) -> FactSet:
    """Fetch, flag gaps, optionally merge an official NSE filing, then append computed facts."""
    filing = facts_from_nse_filing(filing_path) if filing_path else None
    entity = Entity.from_ticker(ticker)
    if filing and entity.ticker.split(".")[0] != filing.entity.nse_symbol.value:
        raise ValueError(f"filing is for {filing.entity.nse_symbol.value}, not {entity.ticker}")
    filing_dates = {f.period_end: f.available_from for f in filing.facts
                    if f.availability_kind == AvailabilityKind.filed and f.available_from} if filing else None

    fs = add_gaps(fetch_facts(ticker, as_of=as_of, client=client, sleep=sleep, filing_dates=filing_dates))
    if fs.entity.resolution != "resolved" and not filing:
        return fs

    facts, pending = list(fs.facts), list(fs.not_yet_public)
    if filing:
        public, later = (filter_as_of(filing.facts, as_of) if as_of else (filing.facts, []))
        facts += public
        pending += later
        fs = fs.model_copy(update={"entity": _merge_entity(fs.entity, filing.entity)})

    extra = []
    if filing:
        new, demote = check_ebitda([f for f in facts if f.source == "nse_filing"],
                                   [f for f in facts if f.source == "yahoo"])
        facts = [demote.get(f.fact_id, f) for f in facts]
        extra += new
    primary = prefer_sources(facts)
    for metric in FLOW_METRICS:
        ok_q = [f for f in primary if f.metric == metric and f.period_type == PeriodType.Q and f.status == Status.ok]
        if not ok_q:
            continue
        latest = max(f.period_end for f in ok_q)
        extra.append(ttm(primary, metric, latest))
        if metric == "net_income":
            extra.append(growth_yoy(primary, metric, latest))
    pt = {f.metric: f for f in facts if f.period_type == PeriodType.point}
    if all(k in pt for k in ("price", "pe_ttm", "eps_ttm")):
        extra.append(reconcile_price(pt["price"], pt["pe_ttm"], pt["eps_ttm"]))
    if filing:
        yahoo = {(f.metric, f.period_end): f for f in facts
                 if f.source == "yahoo" and f.period_type == PeriodType.Q and f.status == Status.ok}
        for f in facts:
            y = yahoo.get((f.metric, f.period_end))
            if f.source == "nse_filing" and y is not None and y.unit == f.unit:
                extra.append(cross_check(f, y))
    return fs.model_copy(update={"facts": facts + extra, "not_yet_public": pending})
