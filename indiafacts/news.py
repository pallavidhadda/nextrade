"""Recent headlines for the target company, with a rough keyword sentiment hint. Headlines are unverified third-party text:
they are never Facts, never scored, and are shown to the narrator as data, not instructions. Education only; not financial advice."""
from __future__ import annotations

import email.utils
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Protocol

from pydantic import BaseModel, ConfigDict

MAX_AGE_DAYS = 30
TITLE_MAX = 160
_CTRL = re.compile(r"[\x00-\x1f\x7f]+|\x1b\[[0-9;]*m")
_POS = ("surge", "jump", "rally", "rallies", "beat", "beats", "record", "rise", "rises", "gain", "gains", "upgrade", "win", "wins", "order win",
        "strong", "growth", "dividend", "bonus", "buyback", "outperform", "profit up", "approval")
_NEG = ("fall", "falls", "slump", "plunge", "plunges", "miss", "misses", "downgrade", "probe", "fraud", "penalty", "fine", "loss", "losses",
        "resign", "resigns", "default", "ban", "raid", "lawsuit", "decline", "declines", "warning", "cut", "weak", "layoff", "layoffs")


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    publisher: str = ""
    published: datetime | None = None
    url: str = ""
    sentiment_hint: str = "neutral"          # positive | negative | neutral; keyword guess, not analysis


class NewsClient(Protocol):
    def news(self, symbol: str) -> list[dict]: ...


class YfinanceNews:
    def news(self, symbol: str) -> list[dict]:
        import yfinance as yf

        return list(yf.Ticker(symbol).news or [])


_NOISE_TITLE = re.compile(r"stock price, news, quote|share price today|live nse/bse|stock price live|share price live|quote and history|historical prices", re.I)
_NOISE_SOURCE = {"facebook", "youtube", "instagram", "reddit", "x", "twitter", "tiktok", "linkedin", "pinterest"}
_UA = {"User-Agent": "Mozilla/5.0 (compatible; NexTradeResearch/0.8; educational use)"}


def _http_fetch(url: str) -> bytes:
    import requests

    r = requests.get(url, timeout=20, headers=_UA)
    r.raise_for_status()
    return r.content


class GoogleNewsRss:
    """Headline titles from Google News RSS (free, no key; terms of use unverified, so titles only and no article text are kept)."""

    def __init__(self, fetch=None):
        self.fetch = fetch or _http_fetch

    def news(self, symbol: str) -> list[dict]:
        base = symbol.upper().split(".")[0]
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(f"{base} NSE shares when:14d") + "&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            raw = self.fetch(url)
            if b"<!doctype" in raw.lower() or b"<!entity" in raw.lower():
                return []
            root = ET.fromstring(raw)
        except Exception:
            return []
        rows = []
        for it in root.findall(".//item"):
            title, source = (it.findtext("title") or "").strip(), (it.findtext("source") or "").strip()
            if source and title.endswith(f" - {source}"):
                title = title[: -len(source) - 3].rstrip()
            if not title or _NOISE_TITLE.search(title) or source.lower() in _NOISE_SOURCE:
                continue
            if not re.search(rf"(?<![A-Za-z0-9]){re.escape(base)}(?![A-Za-z0-9])", title, re.I):
                continue                                                     # search results are noisy: the headline must name the company
            try:
                ts = int(email.utils.parsedate_to_datetime(it.findtext("pubDate") or "").timestamp())
            except (TypeError, ValueError):
                ts = None
            link = (it.findtext("link") or "").strip()
            rows.append({"title": title, "publisher": source, "providerPublishTime": ts, "link": link if link.startswith(("http://", "https://")) else ""})
        return rows


class CombinedNews:
    """Yahoo first (it has nothing for most NSE tickers), then Google News."""

    def __init__(self, *clients):
        self.clients = clients or (YfinanceNews(), GoogleNewsRss())

    def news(self, symbol: str) -> list[dict]:
        for c in self.clients:
            try:
                rows = c.news(symbol)
            except Exception:
                rows = []
            if rows:
                return rows
        return []


def sentiment_hint(title: str) -> str:
    words = re.findall(r"[a-z]+", (title or "").lower())
    text = " ".join(words)
    pos = sum(1 for w in _POS if re.search(rf"\b{re.escape(w)}\b", text))
    neg = sum(1 for w in _NEG if re.search(rf"\b{re.escape(w)}\b", text))
    return "positive" if pos > neg else "negative" if neg > pos else "neutral"


def _clean(s: str, n: int = TITLE_MAX) -> str:
    return re.sub(r"\s+", " ", _CTRL.sub(" ", s or "")).strip()[:n]


def _parse(row: dict) -> tuple[str, str, datetime | None, str]:
    c = row.get("content") if isinstance(row.get("content"), dict) else None
    if c:
        when = None
        try:
            when = datetime.fromisoformat(str(c.get("pubDate", "")).replace("Z", "+00:00"))
        except ValueError:
            pass
        url = ((c.get("canonicalUrl") or {}).get("url")) or ((c.get("clickThroughUrl") or {}).get("url")) or ""
        return c.get("title", ""), (c.get("provider") or {}).get("displayName", ""), when, url
    ts = row.get("providerPublishTime")
    when = datetime.fromtimestamp(ts, timezone.utc) if isinstance(ts, (int, float)) else None
    return row.get("title", ""), row.get("publisher", ""), when, row.get("link", "")


def fetch_news(ticker: str, client: NewsClient | None = None, limit: int = 6, now: datetime | None = None) -> tuple[list[NewsItem], str]:
    now = now or datetime.now(timezone.utc)
    try:
        rows = (client or CombinedNews()).news(ticker)
    except Exception:
        return [], "news headlines could not be fetched (source unreachable from this machine); the report has no news section"
    seen: set[str] = set()
    items: list[NewsItem] = []
    for row in rows:
        title, pub, when, url = _parse(row)
        title = _clean(title)
        key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        if not title or key in seen:
            continue
        if when is not None and when < now - timedelta(days=MAX_AGE_DAYS):
            continue
        if url and not url.startswith(("https://", "http://")):
            url = ""
        seen.add(key)
        items.append(NewsItem(title=title, publisher=_clean(pub, 40), published=when, url=url[:300], sentiment_hint=sentiment_hint(title)))
    items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items[:limit], ""
