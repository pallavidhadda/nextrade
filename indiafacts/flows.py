"""Market-wide positioning of FIIs, DIIs, proprietary traders and clients in equity derivatives, from NSE's public daily file.

Source: nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv (participant-wise open interest, published
by the exchange for anyone; plain HTTP, no cookies). This is derivatives positioning for the WHOLE market, not buying or selling
of one stock, and not the cash-market FII/DII net flow (that figure is only on NSE's cookie-protected site, which this project
does not use). It is context, never an input to a company's rating. Education only; not financial advice.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d}.csv"
USER_AGENT = "NexTrade-research/0.1 (education; reads the exchange's public daily files)"
PARTICIPANTS = ("FII", "DII", "Pro", "Client")
NOTE = ("Index-futures positions of each participant group across the whole market, from the exchange's daily participant file. "
        "It says how traders are positioned, not what any one stock saw, and it is not the cash-market FII/DII buy-sell figure. Context only.")


@dataclass
class Day:
    day: date
    net: dict[str, int]            # index futures long minus short, contracts
    long_share: dict[str, float]   # long / (long + short)


def _get(day: date, opener: Callable = urlopen) -> bytes | None:
    req = Request(URL.format(d=day.strftime("%d%m%Y")), headers={"User-Agent": USER_AGENT})
    try:
        with opener(req, timeout=15) as r:
            raw = r.read(200_000)
    except Exception:
        return None
    return raw if raw.lstrip().startswith(b'"') or b"Client Type" in raw[:600] else None


def parse(raw: bytes, day: date) -> Day:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8", "replace"))))
    header_i = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Client Type"), None)
    if header_i is None:
        raise ValueError("not a participant-wise file")
    head = [h.strip() for h in rows[header_i]]
    li, si = head.index("Future Index Long"), head.index("Future Index Short")
    net, share = {}, {}
    for r in rows[header_i + 1:]:
        if not r or r[0].strip() not in PARTICIPANTS:
            continue
        lo, sh = int(float(r[li])), int(float(r[si]))
        net[r[0].strip()] = lo - sh
        share[r[0].strip()] = lo / (lo + sh) if lo + sh else 0.5
    if not net:
        raise ValueError("no participant rows found")
    return Day(day, net, share)


def history(today: date | None = None, sessions: int = 6, opener: Callable = urlopen, cache_dir: Path | None = None) -> list[Day]:
    """The latest `sessions` trading days that have a published file, newest first. Missing days (weekends, holidays) are skipped."""
    today = today or date.today()
    cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".indiafacts" / "flows"
    out: list[Day] = []
    d = today
    for _ in range(sessions * 3 + 6):
        if len(out) >= sessions:
            break
        if d.weekday() < 5:
            f = cache_dir / f"{d.isoformat()}.json"
            day = None
            if f.exists():
                try:
                    j = json.loads(f.read_text())
                    day = Day(d, j["net"], j["long_share"])
                except (ValueError, KeyError):
                    day = None
            if day is None:
                raw = _get(d, opener)
                if raw is not None:
                    try:
                        day = parse(raw, d)
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        f.write_text(json.dumps({"net": day.net, "long_share": day.long_share}))
                    except ValueError:
                        day = None
            if day is not None:
                out.append(day)
        d -= timedelta(days=1)
    return out


def summary(days: list[Day]) -> dict | None:
    """Plain structure for the views; None when nothing could be fetched."""
    if not days:
        return None
    latest, oldest = days[0], days[-1]
    rows = []
    for p in PARTICIPANTS:
        if p not in latest.net:
            continue
        change = latest.net[p] - oldest.net[p] if p in oldest.net and len(days) > 1 else None
        rows.append({"participant": p, "net": latest.net[p], "long_share": latest.long_share[p], "change": change,
                     "stance": "net long" if latest.net[p] > 0 else "net short" if latest.net[p] < 0 else "flat"})
    return {"as_of": latest.day.isoformat(), "since": oldest.day.isoformat(), "sessions": len(days), "rows": rows, "note": NOTE}


def lines(s: dict | None) -> list[str]:
    if not s:
        return ["", "MARKET FLOWS: the exchange's participant file could not be read just now"]
    out = ["", f"MARKET FLOWS (index-futures positions by participant, as of {s['as_of']}; whole market, not this stock)"]
    for r in s["rows"]:
        ch = "" if r["change"] is None else f", {r['change']:+,} contracts since {s['since']}"
        out.append(f"  {r['participant']}: {r['stance']} {abs(r['net']):,} contracts, {r['long_share']:.0%} of their positions are long{ch}")
    out.append("  " + s["note"])
    return out
