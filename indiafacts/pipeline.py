from __future__ import annotations

import time
from datetime import date

from indiafacts.analysis import add_gaps, growth_yoy, reconcile_price, ttm
from indiafacts.models import FactSet, PeriodType, Status
from indiafacts.yahoo import fetch_facts

FLOW_METRICS = ("net_income", "ebitda", "interest_expense", "eps_diluted")


def build_factset(ticker: str, as_of: date | None = None, client=None, sleep=time.sleep) -> FactSet:
    """Fetch, flag gaps, then append computed facts (TTM, YoY, price check)."""
    fs = add_gaps(fetch_facts(ticker, as_of=as_of, client=client, sleep=sleep))
    if fs.entity.resolution != "resolved":
        return fs
    extra = []
    for metric in FLOW_METRICS:
        ok_q = [f for f in fs.facts if f.metric == metric and f.period_type == PeriodType.Q
                and f.status == Status.ok]
        if not ok_q:
            continue
        latest = max(f.period_end for f in ok_q)
        extra.append(ttm(fs.facts, metric, latest))
        if metric == "net_income":
            extra.append(growth_yoy(fs.facts, metric, latest))
    pt = {f.metric: f for f in fs.facts if f.period_type == PeriodType.point}
    if all(k in pt for k in ("price", "pe_ttm", "eps_ttm")):
        extra.append(reconcile_price(pt["price"], pt["pe_ttm"], pt["eps_ttm"]))
    return fs.model_copy(update={"facts": fs.facts + extra})
