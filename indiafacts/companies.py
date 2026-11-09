"""Company-name search that forgives typos ("infosis" finds Infosys) and knows common brand names.

Data: the Nifty 500 list (NSE public index file). A bare symbol that is not in the list is still allowed through, because
smaller listed companies are not in it; we only interrupt when what was typed looks like a mistake for a listed company.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "companies.json"
# what people type -> NSE symbol (checked against the list in tests)
ALIASES = {
    "sbi": "SBIN", "state bank": "SBIN", "airtel": "BHARTIARTL", "hul": "HINDUNILVR", "unilever": "HINDUNILVR", "larsen": "LT",
    "l&t": "LT", "l and t": "LT", "m and m": "M&M", "mahindra": "M&M", "kotak": "KOTAKBANK", "zomato": "ETERNAL", "paytm": "PAYTM",
    "ongc": "ONGC", "maruti": "MARUTI", "tata motors": "TMPV", "nykaa": "NYKAA", "policybazaar": "POLICYBZR", "dmart": "DMART",
    "lic": "LICI", "irctc": "IRCTC", "jio": "RELIANCE", "tcs": "TCS", "infosys": "INFY", "wipro": "WIPRO", "hcl": "HCLTECH",
}
STOP = {"ltd", "limited", "the", "of", "india", "and", "corporation", "company", "co", "pvt", "private"}


@dataclass(frozen=True)
class Match:
    symbol: str
    name: str
    industry: str
    score: float

    @property
    def ticker(self) -> str:
        return f"{self.symbol}.NS"

    @property
    def label(self) -> str:
        return f"{self.name} ({self.ticker})"


@lru_cache(maxsize=1)
def _companies() -> tuple[tuple[str, str, str, str, tuple[str, ...]], ...]:
    out = []
    for c in json.loads(DATA.read_text(encoding="utf-8")):
        norm = _norm(c["n"])
        toks = tuple(t for t in norm.split() if t not in STOP) or tuple(norm.split())
        out.append((c["s"], c["n"], c["i"], norm, toks))
    return tuple(out)


_LEGAL = {"ltd", "limited", "pvt", "private"}


def aliases_for(ticker: str) -> list[str]:
    """Normalised names a headline may use for this company: its symbol, its listed name without legal suffixes, and the
    brand names in ALIASES that point at it. Derived from the data above; nothing is invented. Only whole-word matching is safe."""
    sym = ticker.upper().rsplit(".", 1)[0] if re.search(r"\.(NS|BO)$", ticker.upper()) else ticker.upper()
    out = [_norm(sym)]
    for s_, n, _i, norm, _t in _companies():
        if s_ == sym:
            words = [w for w in norm.split() if w not in _LEGAL]
            if words:
                out.append(" ".join(words))
    out += [k for k, v in ALIASES.items() if v == sym]
    return list(dict.fromkeys(a for a in out if len(a) >= 2))


def _norm(s: str) -> str:
    s = s.lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _score(q: str, symbol: str, norm: str, toks: tuple[str, ...]) -> float:
    sym = symbol.lower()
    if q == sym or q == norm:
        return 1.0
    if norm.startswith(q) or sym.startswith(q):
        return 0.95 if len(q) >= 3 else 0.7
    if len(q) >= 3 and (q in norm or q in sym):
        return 0.85
    best = 0.0
    for t in toks:                                         # a typo usually damages one word of the name
        best = max(best, _sim(q, t))
    best = max(best, _sim(q, norm) * 0.95, _sim(q, sym) * 0.9)
    if " " in q:                                           # several typed words: every one must resemble some name word
        parts = q.split()
        if parts and all(max(_sim(p, t) for t in toks) >= 0.75 for p in parts):
            best = max(best, 0.8)
    return best


def search(query: str, limit: int = 6, min_score: float = 0.62) -> list[Match]:
    q = _norm(query)
    if len(q) < 2:
        return []
    by_symbol = {c[0]: c for c in _companies()}
    scored: dict[str, float] = {}
    for key, sym in ALIASES.items():
        exact = q == key
        if exact or (len(q) >= 3 and key.startswith(q)) or _sim(q, key) >= 0.85:
            if sym in by_symbol:
                scored[sym] = max(scored.get(sym, 0), 0.99 if exact else 0.9)
    for sym, name, ind, norm, toks in _companies():
        s = _score(q, sym, norm, toks)
        if s >= min_score and s > scored.get(sym, 0):
            scored[sym] = s
    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], by_symbol[kv[0]][1]))[:limit]
    return [Match(sym, by_symbol[sym][1], by_symbol[sym][2], round(sc, 3)) for sym, sc in ranked]


def resolve(raw: str) -> tuple[str | None, list[Match]]:
    """(ticker to use, suggestions). The ticker is None when the input looks like a mistake and the person should choose."""
    t = (raw or "").strip()
    if not t:
        return None, []
    up = t.upper()
    if re.fullmatch(r"[A-Z0-9&-]{1,20}\.(NS|BO)", up):
        return up, []
    symbols = {c[0] for c in _companies()}
    if up in symbols:
        return f"{up}.NS", []
    matches = search(t)
    if matches and matches[0].score >= 0.97 and (len(matches) == 1 or matches[1].score < 0.9):
        return matches[0].ticker, matches                   # an unmistakable name such as "Infosys Ltd."
    if matches and matches[0].score >= 0.6:
        return None, matches                                # a typo or a partial name: let the person pick
    if re.fullmatch(r"[A-Z0-9&-]{1,20}", up):
        return f"{up}.NS", []                               # maybe a listed company outside the Nifty 500
    return None, []
