"""Who owns the company: official shareholding pattern when available, otherwise Yahoo's vendor proxies, clearly labelled."""
from __future__ import annotations

from indiafacts.models import FactSet, Status

NSE_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"
HOW_TO = ("Official pattern not found in the free feed right now. On the NSE website open Corporate Filings, then Shareholding Pattern, and save the company's XBRL file, then "
          "run with --shareholding FILE (or drop it in your filings folder as SHP_*.xml).")

# metric, label, meaning
OFFICIAL = [
    ("sh_promoter", "Promoter and promoter group", "Share held by the founding group."),
    ("sh_promoter_pledged", "Promoter shares pledged", "Share of the promoters' own shares pledged as loan security. High is a risk flag."),
    ("sh_foreign_inst", "Foreign institutions (FPI)", "Foreign funds and institutions."),
    ("sh_domestic_inst", "Domestic institutions", "Mutual funds, insurers, banks and other Indian institutions."),
    ("sh_mutual_funds", "of which mutual funds", "Indian mutual funds."),
    ("sh_public", "Public", "Everyone who is not a promoter."),
    ("sh_retail", "Small retail (up to Rs 2 lakh)", "Individual investors holding small amounts."),
]
CHANGES = {"sh_promoter": "sh_promoter_change", "sh_foreign_inst": "sh_foreign_inst_change", "sh_domestic_inst": "sh_domestic_inst_change"}


def _latest(fs: FactSet, metric: str):
    c = [f for f in fs.facts if f.metric == metric and f.value is not None and f.status in (Status.ok, Status.unverified)]
    return max(c, key=lambda f: (f.period_end, f.retrieved_at)) if c else None


def _reading(metric: str, v: float) -> str:
    if metric == "sh_promoter_pledged":
        return "none" if v <= 0 else "low" if v <= 0.10 else "moderate" if v <= 0.25 else "high"
    return ""


def _change_word(metric: str, d: float) -> str:
    limit = 0.01 if metric != "sh_promoter" else 0.02
    return "rising" if d >= limit else "falling" if d <= -limit else "steady"


def ownership(fs: FactSet) -> dict:
    rows = []
    anchor = _latest(fs, "sh_promoter") or _latest(fs, "sh_public")
    if anchor is not None:
        for metric, label, meaning in OFFICIAL:
            f = _latest(fs, metric)
            if f is None:
                continue
            v = float(f.value)
            row = {"metric": metric, "label": label, "display": f"{v:.1%}", "reading": _reading(metric, v), "meaning": meaning,
                   "change": None, "fact_ids": [f.fact_id]}
            ch = _latest(fs, CHANGES[metric]) if metric in CHANGES else None
            if ch is not None:
                d = float(ch.value)
                row["change"] = f"{d * 100:+.1f} pp since the previous filing ({_change_word(metric, d)})"
                row["fact_ids"].append(ch.fact_id)
            rows.append(row)
        return {"source": "official", "as_on": anchor.period_end.isoformat(), "rows": rows, "how_to": ""}
    for metric, label in (("insider_holding", "Promoter or insider holding"), ("institutional_holding", "Institutional holding")):
        f = _latest(fs, metric)
        if f is not None:
            rows.append({"metric": metric, "label": label, "display": f"{float(f.value):.1%}", "reading": "", "change": None,
                         "meaning": f.reason or "Vendor estimate.", "fact_ids": [f.fact_id]})
    return {"source": "proxy" if rows else "none", "as_on": "", "rows": rows, "how_to": HOW_TO}


def ownership_lines(fs: FactSet) -> list[str]:
    o = ownership(fs)
    if o["source"] == "official":
        out = ["", f"WHO OWNS IT (official NSE shareholding pattern as on {o['as_on']})"]
    else:
        out = ["", "WHO OWNS IT (vendor estimates only; the official pattern was not available)"]
    for r in o["rows"]:
        tag = f" [{r['reading']}]" if r["reading"] else ""
        ch = f"; {r['change']}" if r["change"] else ""
        out.append(f"  {r['label']}: {r['display']}{tag}{ch}")
    if not o["rows"]:
        out.append("  no ownership data returned")
    if o["how_to"]:
        out.append("  " + o["how_to"])
    return out
