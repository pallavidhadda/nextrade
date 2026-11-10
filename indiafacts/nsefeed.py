"""Recent exchange announcements from NSE's public RSS feed (nsearchives.nseindia.com/content/RSS).

The feed is published by the exchange for anyone to read; no login, cookie or browser imitation is involved. It only
holds the most recent day or two of filings for all companies, so it answers "what did this company just file?",
not "give me five years of results". File names start with the NSE symbol, which is how items are matched.
Fails soft: any error returns an empty list and a reason.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from urllib.request import Request, urlopen

FEED_URL = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
RESULTS_URL = "https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml"
USER_AGENT = "NexTrade-research/0.1 (education; reads the exchange's public RSS)"
MAX_BYTES = 3_000_000
_CACHE: dict[str, tuple[float, str]] = {}
TTL = 300


@dataclass(frozen=True)
class Announcement:
    company: str
    symbol: str
    subject: str
    summary: str
    url: str
    published: datetime | None
    category: str = ""


def _get(url: str, opener: Callable = urlopen, now: Callable[[], float] = time.time) -> str:
    hit = _CACHE.get(url)
    if hit and now() - hit[0] < TTL:
        return hit[1]
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with opener(req, timeout=15) as r:
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("feed larger than the size cap")
    text = raw.decode("utf-8", "replace")
    _CACHE[url] = (now(), text)
    return text


def _symbol_from_url(url: str) -> str:
    m = re.search(r"/corporate/([A-Za-z0-9&-]+?)_\d{8,}", url or "")
    return m.group(1).upper() if m else ""


def parse_feed(xml_text: str) -> list[Announcement]:
    root = ET.fromstring(xml_text)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        when = None
        raw = (it.findtext("pubDate") or "").strip()
        for fmt in ("%d-%b-%Y %H:%M:%S",):
            try:
                when = datetime.strptime(raw, fmt)
            except ValueError:
                pass
        subject = desc.split("SUBJECT:")[-1].strip() if "SUBJECT:" in desc else desc[:80]
        m = re.search(r"informed the Exchange about\s+(.+?)\s*(?:\||$)", desc, re.I)
        out.append(Announcement(title, _symbol_from_url(link), subject, desc, link, when, m.group(1).strip() if m else ""))
    return out


def recent_for(symbol: str, opener: Callable = urlopen, limit: int = 8) -> tuple[list[Announcement], str]:
    """(items, note). `symbol` is the NSE symbol without .NS. A failure returns ([], reason) and never raises."""
    sym = symbol.upper().removesuffix(".NS")
    try:
        items = parse_feed(_get(FEED_URL, opener))
    except Exception as exc:
        return [], f"the exchange feed could not be read ({type(exc).__name__})"
    mine = [a for a in items if a.symbol == sym]
    mine.sort(key=lambda a: a.published or datetime.min, reverse=True)
    if not mine:
        return [], "no filing from this company in the exchange's latest feed (it holds only the last day or two)"
    return mine[:limit], ""
