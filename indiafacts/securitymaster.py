"""Security master: where did this symbol go? Renames from NSE's symbol-change list plus a small curated table
for corporate actions the list cannot express (demergers). Pure functions; no network."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

CURATED_PATH = Path(__file__).parent / "data" / "security_master.json"
_SUFFIXES = (".NS", ".BO")


@dataclass(frozen=True)
class SymbolChange:
    name: str
    old: str
    new: str
    effective: date


class SymbolChanges(list):
    """List of SymbolChange; `.skipped` counts rows ignored (bad date or old == new)."""
    skipped: int = 0


@dataclass(frozen=True)
class CuratedChange:
    old_symbol: str
    successors: list[str]
    change_type: str
    effective_date: str
    source_urls: list[str]
    reviewed_on: date
    review_by: date
    notes: str = ""


@dataclass
class Resolution:
    input: str
    kind: str                       # direct | renamed | split | unknown
    symbols: list[str]
    notice: str = ""
    chain: list[SymbolChange] = field(default_factory=list)


def normalize_symbol(raw: str) -> str:
    s = raw.strip().upper()
    for suf in _SUFFIXES:
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def load_symbol_changes(path: Path) -> SymbolChanges:
    out = SymbolChanges()
    for row in csv.DictReader(open(path, encoding="utf-8-sig", newline="")):
        old, new = (row.get("OLD SYMBOL") or "").strip().upper(), (row.get("NEW SYMBOL") or "").strip().upper()
        try:
            eff = datetime.strptime((row.get("EFFECTIVE DATE") or "").strip(), "%d-%b-%Y").date()
        except ValueError:
            out.skipped += 1
            continue
        if not old or not new or old == new:
            out.skipped += 1
            continue
        out.append(SymbolChange((row.get("NAME OF THE COMPANY") or "").strip(), old, new, eff))
    _reject_cycles(out)
    return out


def _reject_cycles(changes: list[SymbolChange]) -> None:
    nxt: dict[str, list[str]] = {}
    for c in changes:
        nxt.setdefault(c.old, []).append(c.new)
    done: set[str] = set()
    for start in nxt:
        stack, on_path = [(start, iter(nxt.get(start, [])))], [start]
        while stack:
            node, it = stack[-1]
            child = next(it, None)
            if child is None:
                stack.pop()
                done.add(on_path.pop())
            elif child in on_path:
                loop = on_path[on_path.index(child):] + [child]
                raise ValueError("circular symbol changes: " + " -> ".join(loop))
            elif child not in done and child in nxt:
                stack.append((child, iter(nxt[child])))
                on_path.append(child)


def load_curated(path: Path | None = None, today: date | None = None) -> list[CuratedChange]:
    today = today or date.today()
    data = json.loads(Path(path or CURATED_PATH).read_text(encoding="utf-8"))
    out = []
    for e in data.get("entries", []):
        if not e.get("source_urls"):
            raise ValueError(f"curated entry {e.get('old_symbol')}: source_urls required")
        review_by = date.fromisoformat(e["review_by"])
        if review_by < today:
            raise ValueError(f"curated entry {e['old_symbol']}: review overdue (review_by {review_by})")
        out.append(CuratedChange(
            old_symbol=e["old_symbol"].upper(), successors=[s.upper() for s in e["successors"]],
            change_type=e["change_type"], effective_date=e["effective_date"], source_urls=e["source_urls"],
            reviewed_on=date.fromisoformat(e["reviewed_on"]), review_by=review_by, notes=e.get("notes", "")))
    return out


def resolve_symbol(raw: str, changes: list[SymbolChange] | None, curated: list[CuratedChange]) -> Resolution:
    sym = normalize_symbol(raw)
    events: dict[str, list[tuple[date, str, SymbolChange]]] = {}
    for c in changes or []:
        events.setdefault(c.old, []).append((c.effective, "old", c))
        events.setdefault(c.new, []).append((c.effective, "new", c))

    def retired(s: str) -> SymbolChange | None:
        ev = sorted(events.get(s, []), key=lambda e: (e[0], e[1] == "old"))
        return ev[-1][2] if ev and ev[-1][1] == "old" else None

    by_old = {c.old_symbol: c for c in curated}
    chain: list[SymbolChange] = []
    current, seen = sym, set()
    while current not in seen:
        seen.add(current)
        if current in by_old:
            c = by_old[current]
            notice = (f"{current} was subject to a {c.change_type} (effective {c.effective_date}); successors: "
                      f"{', '.join(c.successors)}. Choose one; the app will not guess.")
            return Resolution(raw, "split", list(c.successors), notice, chain)
        hop = retired(current)
        if hop is None:
            break
        chain.append(hop)
        current = hop.new
    if chain:
        last = chain[-1]
        notice = f"{sym} is now {current} (symbol changed {last.effective.isoformat()} per NSE symbol-change list)"
        return Resolution(raw, "renamed", [current], notice, chain)
    if sym in events:
        return Resolution(raw, "direct", [sym])
    if changes is None:
        return Resolution(raw, "unknown", [sym], "symbol-change list not loaded; no rename check was possible")
    return Resolution(raw, "unknown", [sym], f"{sym}: not in security master (no recorded symbol change)")
