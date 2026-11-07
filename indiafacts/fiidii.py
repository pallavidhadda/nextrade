"""Cash-market FII/FPI and DII buying and selling, from a file YOU save from NSE's FII/DII page.

NSE publishes this figure only on its website (the page has a download), not as a public file feed, and its JSON API sits behind a
bot check that this project does not go around. So the supported route is: save the page's data, then
    python -m indiafacts.fiidii import saved_file.csv      (or .json)
Every import is merged into a local store, so history builds up day by day. Amounts are rupees crore, as NSE prints them.
Education only; not financial advice.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DATE_FORMATS = ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%d-%B-%Y")
FIELDS = ["date", "category", "buy", "sell", "net", "source"]
NOTE = ("Cash-market buying and selling by foreign portfolio investors (FII/FPI) and domestic institutions (DII), in rupees crore, "
        "from files you saved from NSE. Whole market, not one stock. Context only; it is never used in a rating.")


@dataclass(frozen=True)
class Row:
    day: date
    category: str          # FII | DII
    buy: float
    sell: float
    net: float


def default_store() -> Path:
    return Path(os.environ.get("INDIAFACTS_FIIDII_STORE") or Path.home() / ".indiafacts" / "fiidii.csv")


def _num(x) -> float | None:
    if x is None:
        return None
    t = re.sub(r"[,\s₹]", "", str(x))
    t = t.replace("(", "-").replace(")", "")
    try:
        return float(t)
    except ValueError:
        return None


def _date(x) -> date | None:
    t = str(x).strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


def _cat(x: str) -> str | None:
    u = str(x).upper()
    if "FII" in u or "FPI" in u:
        return "FII"
    if "DII" in u:
        return "DII"
    return None


def _make(day, cat, buy, sell, net) -> Row | None:
    if day is None or cat is None or buy is None or sell is None:
        return None
    return Row(day, cat, buy, sell, net if net is not None else round(buy - sell, 2))


def _key(h: str) -> str:
    return re.sub(r"[^a-z]", "", h.lower())


def parse_records(records: list[dict]) -> list[Row]:
    """Long layout: one record per date and category. Keys may be NSE's JSON names or CSV headings."""
    rows = []
    for r in records:
        k = {_key(a): b for a, b in r.items()}
        cat = next((_cat(v) for kk, v in k.items() if "categ" in kk and _cat(v)), None)
        day = next((_date(v) for kk, v in k.items() if kk.startswith("date") and _date(v)), None)
        buy = next((_num(v) for kk, v in k.items() if "buy" in kk and _num(v) is not None), None)
        sell = next((_num(v) for kk, v in k.items() if "sell" in kk and _num(v) is not None), None)
        net = next((_num(v) for kk, v in k.items() if "net" in kk and _num(v) is not None), None)
        row = _make(day, cat, buy, sell, net)
        if row:
            rows.append(row)
    return rows


def parse_wide(records: list[dict]) -> list[Row]:
    """Wide layout: one record per date with columns such as 'FII Buy', 'FII Sell', 'FII Net', 'DII Buy' ..."""
    rows = []
    for r in records:
        day = next((_date(v) for h, v in r.items() if _key(h).startswith("date") and _date(v)), None)
        if day is None:
            continue
        for cat in ("FII", "DII"):
            grab = lambda word: next((_num(v) for h, v in r.items()
                                      if (cat.lower() in _key(h) or (cat == "FII" and "fpi" in _key(h))) and word in _key(h) and _num(v) is not None), None)
            row = _make(day, cat, grab("buy"), grab("sell"), grab("net"))
            if row:
                rows.append(row)
    return rows


def parse_file(path: Path) -> list[Row]:
    raw = Path(path).read_bytes()
    if len(raw) > 5_000_000:
        raise ValueError("file larger than the 5 MB cap")
    text = raw.decode("utf-8-sig", "replace")
    rows: list[Row] = []
    if text.lstrip().startswith(("[", "{")):
        data = json.loads(text)
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [data])
        rows = parse_records([d for d in data if isinstance(d, dict)])
    else:
        lines = text.splitlines()
        start = next((i for i, ln in enumerate(lines) if re.search(r"date", ln, re.I) and re.search(r"buy|sell|net", ln, re.I)), None)
        if start is None:
            raise ValueError("could not find a header row with date and buy/sell columns")
        recs = list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))
        rows = parse_records(recs) or parse_wide(recs)
    if not rows:
        raise ValueError("no FII or DII rows could be read from this file")
    return rows


def _read(path: Path) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def import_file(path: Path, store: Path | None = None) -> tuple[int, int]:
    """Merge a saved file into the store. Returns (rows added, rows already present)."""
    store = Path(store or default_store())
    rows = parse_file(path)
    have = {(r["date"], r["category"]) for r in _read(store)}
    new = [r for r in rows if (r.day.isoformat(), r.category) not in have]
    dup = len(rows) - len(new)
    seen = set()
    uniq = []
    for r in new:
        if (r.day, r.category) not in seen:
            seen.add((r.day, r.category))
            uniq.append(r)
    if uniq:
        store.parent.mkdir(parents=True, exist_ok=True)
        fresh = not store.exists()
        with open(store, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if fresh:
                w.writeheader()
            for r in sorted(uniq, key=lambda r: (r.day, r.category)):
                w.writerow({"date": r.day.isoformat(), "category": r.category, "buy": r.buy, "sell": r.sell, "net": r.net,
                            "source": Path(path).name})
    return len(uniq), dup + (len(new) - len(uniq))


def load(store: Path | None = None) -> list[Row]:
    out = []
    for r in _read(Path(store or default_store())):
        try:
            out.append(Row(date.fromisoformat(r["date"]), r["category"], float(r["buy"]), float(r["sell"]), float(r["net"])))
        except (ValueError, KeyError):
            continue
    return sorted(out, key=lambda r: (r.day, r.category))


def summary(sessions: int = 10, store: Path | None = None) -> dict | None:
    rows = load(store)
    if not rows:
        return None
    days = sorted({r.day for r in rows})[-sessions:]
    out = []
    for cat in ("FII", "DII"):
        mine = {r.day: r for r in rows if r.category == cat and r.day in days}
        if not mine:
            continue
        ordered = [mine[d] for d in sorted(mine)]
        last = ordered[-1]
        streak, sign = 0, 1 if last.net >= 0 else -1
        for r in reversed(ordered):
            if (r.net >= 0) == (sign > 0):
                streak += 1
            else:
                break
        out.append({"category": cat, "last_day": last.day.isoformat(), "last_net": round(last.net, 2),
                    "window_net": round(sum(r.net for r in ordered), 2), "sessions": len(ordered),
                    "streak": streak, "streak_word": "net buying" if sign > 0 else "net selling"})
    return {"rows": out, "as_of": days[-1].isoformat(), "note": NOTE} if out else None


def lines(s: dict | None) -> list[str]:
    if not s:
        return []
    out = ["", f"CASH-MARKET FII/DII (rupees crore, from files you saved from NSE; latest {s['as_of']})"]
    for r in s["rows"]:
        out.append(f"  {r['category']}: {r['last_net']:+,.0f} on {r['last_day']}; {r['window_net']:+,.0f} over the last {r['sessions']} sessions; "
                   f"{r['streak']} session(s) in a row of {r['streak_word']}")
    out.append("  " + s["note"])
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(prog="indiafacts.fiidii", description="Import and show cash-market FII/DII data you saved from NSE.")
    p.add_argument("action", choices=["import", "show"])
    p.add_argument("files", nargs="*", type=Path)
    p.add_argument("--store", type=Path, default=None)
    a = p.parse_args(argv)
    if a.action == "import":
        if not a.files:
            print("give one or more saved files (.csv or .json)", file=sys.stderr)
            return 2
        bad = 0
        for f in a.files:
            try:
                added, dup = import_file(f, a.store)
                print(f"{f.name}: added {added}, already had {dup}")
            except (ValueError, OSError) as exc:
                bad += 1
                print(f"{f.name}: not imported ({exc})", file=sys.stderr)
        return 1 if bad else 0
    print("\n".join(lines(summary(store=a.store))) or "nothing imported yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
