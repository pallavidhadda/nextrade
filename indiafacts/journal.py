"""Decision journal and settlement: every educational rating is recorded, then scored against the Nifty 50 once its holding window
has traded. Entry is the first close AFTER the decision date; the outcome is known only after the full window has closed.
Adapted in approach from TauricResearch/TradingAgents' memory settlement (Apache-2.0, https://github.com/TauricResearch/TradingAgents);
the reflection step is deterministic text here, not a model call. Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from indiafacts.prices import PriceClient, YfinancePriceClient, load_series
from indiafacts.render import DISCLAIMER

BULLISH = ("Buy", "Overweight")
BEARISH = ("Underweight", "Sell")
RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
HOLD_BAND = 0.03
DEFAULT_HORIZON = 21

SCHEMA = """CREATE TABLE IF NOT EXISTS decisions (
  ticker TEXT NOT NULL, decided_on TEXT NOT NULL, horizon_days INTEGER NOT NULL, rating TEXT NOT NULL, confidence TEXT, score REAL,
  price REAL, profile_hash TEXT, recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
  entry_date TEXT, exit_date TEXT, raw_return REAL, benchmark_return REAL, alpha REAL, verdict TEXT, note TEXT, settled_on TEXT,
  PRIMARY KEY (ticker, decided_on, horizon_days))"""


def default_path() -> Path:
    return Path.home() / ".indiafacts" / "journal.db"


@dataclass
class Settlement:
    settled: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str, str]] = field(default_factory=list)


class Journal:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or default_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._db()) as db:
            db.execute(SCHEMA)
            db.commit()

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def record(self, ticker: str, decided_on: date, rating: str, confidence: str, score: float | None, price: float | None,
               profile_hash: str = "", horizon_days: int = DEFAULT_HORIZON) -> bool:
        if rating not in RATINGS:
            return False
        with closing(self._db()) as db:
            db.execute("DELETE FROM decisions WHERE ticker=? AND decided_on=? AND horizon_days=? AND settled_on IS NULL",
                       (ticker, decided_on.isoformat(), horizon_days))
            db.execute("INSERT OR IGNORE INTO decisions (ticker, decided_on, horizon_days, rating, confidence, score, price, profile_hash) VALUES (?,?,?,?,?,?,?,?)",
                       (ticker, decided_on.isoformat(), horizon_days, rating, confidence, score, price, profile_hash))
            db.commit()
        return True

    def pending(self) -> list[dict]:
        with closing(self._db()) as db:
            return [dict(r) for r in db.execute("SELECT * FROM decisions WHERE settled_on IS NULL ORDER BY decided_on")]

    def settled_rows(self) -> list[dict]:
        with closing(self._db()) as db:
            return [dict(r) for r in db.execute("SELECT * FROM decisions WHERE settled_on IS NOT NULL ORDER BY decided_on")]

    def export_csv(self, path: Path) -> int:
        """Write every decision to a CSV (the portable copy of the journal). Returns the row count."""
        import csv

        with closing(self._db()) as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM decisions ORDER BY decided_on, ticker")]
        cols = [c for c in (rows[0].keys() if rows else self._columns())]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        return len(rows)

    def _columns(self) -> list[str]:
        with closing(self._db()) as db:
            return [r[1] for r in db.execute("PRAGMA table_info(decisions)")]

    def import_csv(self, path: Path) -> int:
        """Load decisions from a CSV written by export_csv. Existing rows are kept (primary key wins); returns rows added."""
        import csv

        if not Path(path).exists():
            return 0
        cols = self._columns()
        added = 0
        with open(path, newline="", encoding="utf-8") as fh, closing(self._db()) as db:
            for row in csv.DictReader(fh):
                vals = [(row.get(c) if row.get(c) not in ("", None) else None) for c in cols]
                cur = db.execute(f"INSERT OR IGNORE INTO decisions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
                added += cur.rowcount
            db.commit()
        return added

    def settle(self, client: PriceClient | None, today: date, holding_days: int | None = None, benchmark: str = "^NSEI",
               hold_band: float = HOLD_BAND) -> Settlement:
        client = client or YfinancePriceClient()
        out = Settlement()
        cache: dict[str, object] = {}

        def series(sym: str):
            if sym not in cache:
                cache[sym] = load_series(sym, client, as_of=today)
            return cache[sym]

        for row in self.pending():
            hd = holding_days or row["horizon_days"]
            decided = date.fromisoformat(row["decided_on"])
            if (today - decided).days < hd + 1:
                continue                                                   # the window cannot have traded yet
            try:
                s, b = series(row["ticker"]), series(benchmark)
            except Exception:
                out.failed.append((row["ticker"], row["decided_on"], "prices unavailable from the data source"))
                continue
            after = [(d, c) for d, c in zip(s.dates, s.close) if d > decided and d < today]
            if len(after) <= hd or not b.usable:
                continue                                                   # not enough closed sessions yet
            (entry_d, entry_c), (exit_d, exit_c) = after[0], after[hd]
            bmap = dict(zip(b.dates, b.close))

            def bench_at(d):
                keys = [k for k in bmap if k <= d]
                return bmap[max(keys)] if keys else None

            b0, b1 = bench_at(entry_d), bench_at(exit_d)
            if b0 is None or b1 is None or b.dates[-1] < exit_d:
                continue
            raw, bret = exit_c / entry_c - 1, b1 / b0 - 1
            alpha = raw - bret
            rating = row["rating"]
            ok = alpha > 0 if rating in BULLISH else alpha < 0 if rating in BEARISH else abs(alpha) <= hold_band
            side = "bullish" if rating in BULLISH else "bearish" if rating in BEARISH else f"neutral (within {hold_band:.0%} of the index)"
            note = (f"{rating}: stock {raw:+.1%} versus Nifty 50 {bret:+.1%} over {hd} sessions (excess {alpha:+.1%}); "
                    f"{'consistent' if ok else 'not consistent'} with a {side} rating. One window, not evidence the rule works.")
            with closing(self._db()) as db:
                db.execute("UPDATE decisions SET entry_date=?, exit_date=?, raw_return=?, benchmark_return=?, alpha=?, verdict=?, note=?, settled_on=? "
                           "WHERE ticker=? AND decided_on=? AND horizon_days=?",
                           (entry_d.isoformat(), exit_d.isoformat(), raw, bret, alpha, "consistent" if ok else "inconsistent", note,
                            today.isoformat(), row["ticker"], row["decided_on"], row["horizon_days"]))
                db.commit()
            out.settled.append((row["ticker"], row["decided_on"]))
        return out

    def scoreboard(self) -> dict:
        rows = self.settled_rows()

        def agg(rs: list[dict]) -> dict:
            n = len(rs)
            return {"n": n, "mean_raw": sum(r["raw_return"] for r in rs) / n if n else None,
                    "mean_alpha": sum(r["alpha"] for r in rs) / n if n else None,
                    "consistent_rate": sum(1 for r in rs if r["verdict"] == "consistent") / n if n else None}

        return {"overall": agg(rows), "by_rating": {k: agg([r for r in rows if r["rating"] == k]) for k in RATINGS if any(r["rating"] == k for r in rows)},
                "pending": len(self.pending())}


def render_scoreboard(sb: dict) -> str:
    o = sb["overall"]
    lines = ["DECISION JOURNAL SCOREBOARD (ratings settled against the Nifty 50 after their holding window)",
             f"settled {o['n']}, still pending {sb['pending']}"]
    if o["n"]:
        lines.append(f"{'rating':<12}{'n':>4}{'mean return':>14}{'mean excess':>14}{'consistent':>12}")
        for k, a in sb["by_rating"].items():
            lines.append(f"{k:<12}{a['n']:>4}{a['mean_raw']:>+14.1%}{a['mean_alpha']:>+14.1%}{a['consistent_rate']:>12.0%}")
        lines.append(f"{'all':<12}{o['n']:>4}{o['mean_raw']:>+14.1%}{o['mean_alpha']:>+14.1%}{o['consistent_rate']:>12.0%}")
    lines += ["Small samples and overlapping windows: this is a log of past ratings, not a track record and not evidence the rule works.", DISCLAIMER]
    return "\n".join(lines)


def log_batch(j: Journal, a, runner=None) -> int:
    """Rate a rotating slice of the pool and record each rating, so the journal fills without anyone typing tickers.
    The slice rotates by day of year, so a daily or weekly schedule covers the whole list over time."""
    import contextlib
    import io

    from indiafacts.cli import main as cli_main

    path = a.tickers or Path(__file__).parent / "data" / "pool30.txt"
    names = [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    if not names:
        print("no tickers to rate")
        return 2
    start = (date.today().timetuple().tm_yday * a.limit) % len(names)
    chosen = [names[(start + i) % len(names)] for i in range(min(a.limit, len(names)))]
    ok = bad = 0
    for t in chosen:
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = runner(t) if runner else cli_main([t, "--score", "--pool-size", str(a.pool_size), "--no-tej"], journal=j)
        except Exception as exc:
            code = 1
            print(f"  {t}: failed ({type(exc).__name__})")
        ok, bad = (ok + 1, bad) if code == 0 else (ok, bad + 1)
    print(f"rated {ok}, failed {bad}: {', '.join(chosen)}")
    return 0 if ok else 1


def main(argv: list[str] | None = None, client=None, journal: Journal | None = None) -> int:
    p = argparse.ArgumentParser(prog="indiafacts.journal", description="Settle and review recorded educational ratings.")
    p.add_argument("action", choices=["settle", "board", "pending", "log", "export", "import"])
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--csv", type=Path, default=Path("data/journal.csv"), help="export/import file (default data/journal.csv)")
    p.add_argument("--tickers", type=Path, default=None, help="log: file with one ticker per line (default: the built-in pool of 30)")
    p.add_argument("--limit", type=int, default=10, help="log: how many tickers to rate this run")
    p.add_argument("--pool-size", type=int, default=12, help="log: comparison pool size per run (smaller is faster)")
    a = p.parse_args(argv)
    j = journal or Journal(a.db)
    if a.action == "export":
        print(f"exported {j.export_csv(a.csv)} decisions to {a.csv}")
        return 0
    if a.action == "import":
        print(f"imported {j.import_csv(a.csv)} new decisions from {a.csv}")
        return 0
    if a.action == "log":
        return log_batch(j, a)
    if a.action == "settle":
        res = j.settle(client, date.today())
        print(f"settled {len(res.settled)}; could not settle {len(res.failed)}")
        for t, d, why in res.failed:
            print(f"  {t} {d}: {why}")
        print(render_scoreboard(j.scoreboard()))
    elif a.action == "board":
        print(render_scoreboard(j.scoreboard()))
    else:
        for r in j.pending():
            print(f"{r['ticker']} {r['decided_on']} {r['rating']} ({r['confidence']}) horizon {r['horizon_days']} sessions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
