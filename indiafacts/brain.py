"""Snapshot store ('second brain' S1): every run is remembered, every version of every figure is kept with its dates,
and `changes()` says what is new since the last look. Local sqlite file, standard library only.
Research and education only; not financial, investment or trading advice."""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from indiafacts.models import FactSet, PeriodType, Status

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, as_of TEXT, created_at TEXT, profile_hash TEXT);
CREATE TABLE IF NOT EXISTS observations(obs_id TEXT PRIMARY KEY, fact_id TEXT, ticker TEXT, metric TEXT, period_end TEXT,
  period_type TEXT, fiscal_label TEXT, source TEXT, source_field TEXT, value TEXT, status TEXT, reason TEXT, available_from TEXT,
  evidence TEXT, first_seen TEXT);
CREATE INDEX IF NOT EXISTS obs_fact ON observations(fact_id);
CREATE TABLE IF NOT EXISTS run_obs(run_id INTEGER, obs_id TEXT, PRIMARY KEY(run_id, obs_id));
CREATE TABLE IF NOT EXISTS scores(run_id INTEGER PRIMARY KEY, overall REAL, rank INTEGER, n INTEGER, config_hash TEXT);
CREATE TABLE IF NOT EXISTS filings(filing_id TEXT PRIMARY KEY, ticker TEXT, document TEXT, filing_date TEXT, period_end TEXT, basis TEXT,
  audit_status TEXT, rounding TEXT, currency TEXT, revision_note TEXT, first_seen TEXT);
CREATE TABLE IF NOT EXISTS checks(run_id INTEGER, check_id TEXT, result TEXT, PRIMARY KEY(run_id, check_id));
"""
MARKET_METRICS = {"price", "pe_ttm", "pb", "eps_ttm", "market_cap", "roe", "debt_to_equity", "revenue_ttm_vendor",
                  "net_income_ttm_vendor"}
POINT_PREFIXES = ("return_", "benchmark_return_", "relative_return_", "pct_from_", "max_drawdown_", "volatility")


@dataclass
class Change:
    kind: str
    text: str
    severity: str = "info"          # info | attention
    fact_ids: tuple[str, ...] = ()


@dataclass
class Version:
    value: Decimal | None
    status: str
    available_from: str | None
    source: str
    evidence: str
    first_seen: str


def default_path() -> Path:
    return Path.home() / ".indiafacts" / "brain.db"


def _label(o) -> str:
    return o["fiscal_label"] or o["period_end"]


class Brain:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.last_error: str | None = None

    def _conn(self) -> sqlite3.Connection:
        p = self.path or default_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p)
        c.row_factory = sqlite3.Row
        c.executescript(SCHEMA)
        return c

    def record_run(self, fs: FactSet, sc: dict | None, profile, now: datetime) -> int:
        c = self._conn()
        try:
            with c:
                run_id = c.execute("INSERT INTO runs(ticker, as_of, created_at, profile_hash) VALUES (?,?,?,?)",
                                   (fs.entity.ticker, fs.retrieved_at.date().isoformat(), now.isoformat(),
                                    getattr(profile, "profile_hash", None))).lastrowid
                for f in fs.facts:
                    key = "|".join(str(x) for x in (f.fact_id, f.value, f.status.value, f.reason, f.basis.value, f.evidence, f.available_from))
                    oid = hashlib.sha256(key.encode()).hexdigest()[:20]
                    c.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (oid, f.fact_id, fs.entity.ticker, f.metric, f.period_end.isoformat(), f.period_type.value,
                               f.fiscal_label, f.source, f.source_field, None if f.value is None else str(f.value),
                               f.status.value, f.reason, f.available_from.isoformat() if f.available_from else None,
                               f.evidence, now.isoformat()))
                    c.execute("INSERT OR IGNORE INTO run_obs VALUES (?,?)", (run_id, oid))
                for m in fs.filings:
                    c.execute("INSERT OR IGNORE INTO filings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (m.filing_id, fs.entity.ticker, m.document, m.filing_date.isoformat() if m.filing_date else None,
                               m.period_end.isoformat() if m.period_end else None, m.basis, m.audit_status, m.rounding, m.currency,
                               m.revision_note, now.isoformat()))
                r = (sc or {}).get("result")
                if r is not None and r.status == "ok":
                    c.execute("INSERT INTO scores VALUES (?,?,?,?,?)", (run_id, r.overall, r.rank, sc["n"], r.config_hash))
                for ch in (sc or {}).get("checklist", []):
                    c.execute("INSERT OR REPLACE INTO checks VALUES (?,?,?)", (run_id, ch.id, ch.result))
            return run_id
        finally:
            c.close()

    def safe_record_run(self, fs, sc, profile, now) -> int | None:
        """Never lets a storage problem break a report."""
        try:
            self.last_error = None
            return self.record_run(fs, sc, profile, now)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

    def stats(self) -> dict:
        c = self._conn()
        try:
            return {"runs": c.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
                    "observations": c.execute("SELECT COUNT(*) FROM observations").fetchone()[0]}
        finally:
            c.close()

    def filings(self, ticker: str) -> list[dict]:
        c = self._conn()
        try:
            return [dict(r) for r in c.execute("SELECT * FROM filings WHERE ticker=? ORDER BY filing_date, filing_id", (ticker,))]
        finally:
            c.close()

    def versions(self, fact_id: str) -> list[Version]:
        c = self._conn()
        try:
            rows = c.execute("SELECT * FROM observations WHERE fact_id=? ORDER BY first_seen, rowid", (fact_id,)).fetchall()
            return [Version(None if r["value"] is None else Decimal(r["value"]), r["status"], r["available_from"], r["source"],
                            r["evidence"], r["first_seen"]) for r in rows]
        finally:
            c.close()

    def _run_obs(self, c, run_id: int) -> dict[str, sqlite3.Row]:
        rows = c.execute("SELECT o.* FROM observations o JOIN run_obs r ON r.obs_id=o.obs_id WHERE r.run_id=?", (run_id,)).fetchall()
        return {r["fact_id"]: r for r in rows}

    def changes(self, ticker: str) -> list[Change]:
        c = self._conn()
        try:
            ids = [r["id"] for r in c.execute("SELECT id FROM runs WHERE ticker=? ORDER BY id", (ticker,)).fetchall()]
            if len(ids) < 2:
                return []
            prev_id, cur_id = ids[-2], ids[-1]
            prev, cur = self._run_obs(c, prev_id), self._run_obs(c, cur_id)
            out: list[Change] = []
            small = 0
            for fid, n in cur.items():
                o = prev.get(fid)
                reported = n["period_type"] == PeriodType.Q.value and n["source"] != "computed"
                is_market = n["metric"] in MARKET_METRICS or (n["source_field"] or "").startswith("series:")
                if o is None:
                    if n["status"] == Status.gap.value and reported:
                        out.append(Change("gap_opened", f"gap opened: {n['metric']} {_label(n)} is missing at {n['source']}", "attention", (fid,)))
                    elif reported and n["status"] == Status.ok.value:
                        out.append(Change("new_figure", f"new figure: {n['metric']} {_label(n)} = {n['value']} ({n['source']})", "info", (fid,)))
                    continue
                if o["obs_id"] == n["obs_id"] or (n["source"] == "computed" and not is_market):      # price metrics are computed but are market data
                    continue
                if o["status"] == Status.gap.value and n["status"] == Status.ok.value:
                    out.append(Change("gap_closed", f"gap closed: {n['metric']} {_label(n)} now has a figure ({n['value']})", "info", (fid,)))
                elif o["status"] != n["status"] and not is_market:
                    out.append(Change("status_changed", f"{n['metric']} {_label(n)}: status {o['status']} -> {n['status']}"
                                      + (f" ({n['reason']})" if n["reason"] else ""), "attention", (fid,)))
                elif o["value"] != n["value"] and reported:
                    if n["source"] == "nse_filing":
                        out.append(Change("possible_restatement",
                                          f"{n['metric']} {_label(n)}: {o['value']} (filing dated {o['available_from'] or 'unknown date'}) -> "
                                          f"{n['value']} (filing dated {n['available_from'] or 'unknown date'}); both versions are kept, "
                                          f"read the revised filing's remarks", "attention", (fid,)))
                    else:
                        out.append(Change("vendor_revision", f"{n['metric']} {_label(n)} changed at {n['source']}: {o['value']} -> {n['value']}",
                                          "info", (fid,)))
                elif o["value"] != n["value"] and is_market and o["value"] and n["value"]:
                    a, b = Decimal(o["value"]), Decimal(n["value"])
                    material = (abs(b - a) >= Decimal("0.02") if n["metric"].startswith(POINT_PREFIXES)
                                else (a != 0 and abs(b - a) / abs(a) >= Decimal("0.05")))
                    if material:
                        out.append(Change("market_move", f"{n['metric']}: {o['value']} -> {n['value']}", "info", (fid,)))
                    else:
                        small += 1
            if small:
                out.append(Change("market_move_summary", f"{small} small market figure(s) moved slightly (not listed)"))
            ps, cs = c.execute("SELECT * FROM scores WHERE run_id=?", (prev_id,)).fetchone(), c.execute("SELECT * FROM scores WHERE run_id=?", (cur_id,)).fetchone()
            if ps and cs:
                if ps["rank"] != cs["rank"]:
                    out.append(Change("rank_moved", f"pool rank {ps['rank']} -> {cs['rank']} of {cs['n']}"))
                if abs(cs["overall"] - ps["overall"]) >= 1.0:
                    out.append(Change("score_changed", f"overall score {ps['overall']:.1f} -> {cs['overall']:.1f}"))
            pc = {r["check_id"]: r["result"] for r in c.execute("SELECT * FROM checks WHERE run_id=?", (prev_id,))}
            for r in c.execute("SELECT * FROM checks WHERE run_id=?", (cur_id,)):
                if r["check_id"] in pc and pc[r["check_id"]] != r["result"]:
                    out.append(Change("checklist_flip", f"checklist '{r['check_id']}': {pc[r['check_id']]} -> {r['result']}", "attention"))
            order = {"possible_restatement": 0, "status_changed": 1, "checklist_flip": 2, "gap_opened": 3, "gap_closed": 4,
                     "new_figure": 5, "rank_moved": 6, "score_changed": 7, "vendor_revision": 8, "market_move": 9}
            return sorted(out, key=lambda ch: order.get(ch.kind, 99))
        finally:
            c.close()
