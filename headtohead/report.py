"""Aggregate a head-to-head run into a table and a markdown report; later settle both systems' ratings against the Nifty 50.

    python headtohead/report.py --date 2026-11-06            # write results/<date>/summary.csv and HEAD_TO_HEAD.md
    python headtohead/report.py --date 2026-11-06 --record   # put both systems' ratings into two journals
    python headtohead/report.py --date 2026-11-06 --settle   # after 21+ sessions: settle both and print scoreboards
Research/education only; not financial, investment or trading advice.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BULL, BEAR = ("Buy", "Overweight"), ("Underweight", "Sell")
BLIND_WORDS = re.compile(r"unavailable|unable to|withheld|restricted|constraint|not available|no data|cannot", re.I)
NUM = re.compile(r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?")


def direction(r: str | None) -> str:
    return "bullish" if r in BULL else "bearish" if r in BEAR else "neutral" if r == "Hold" else "none"


def numbers(text: str) -> set[str]:
    return {m.replace(",", "") for m in NUM.findall(text or "")}


def ungrounded_share(ta: dict) -> tuple[int, int]:
    """Numbers in TradingAgents' final decision that appear in none of its own analyst reports (trivial small integers and years ignored)."""
    seen = set()
    for r in ta.get("reports", {}).values():
        seen |= numbers(r)
    final = {n for n in numbers(ta.get("final_trade_decision", "")) if not (re.fullmatch(r"\d{1,2}", n) or n in ("2025", "2026", "2027"))}
    return len(final - seen), len(final)


def blind_fundamentals(ta: dict) -> bool:
    f = (ta.get("reports", {}).get("fundamentals_report") or "")
    return bool(BLIND_WORDS.search(f[:700]))


def load(out: Path) -> list[dict]:
    rows = []
    for nt_f in sorted(out.glob("*.nt.json")):
        t = nt_f.name.removesuffix(".nt.json")
        nt = json.loads(nt_f.read_text())
        ta_f = out / f"{t}.ta.json"
        ta = json.loads(ta_f.read_text()) if ta_f.exists() else {"status": "missing"}
        u, n = ungrounded_share(ta) if ta.get("status") == "ok" else (0, 0)
        use = nt.get("usage") or {}
        rows.append({
            "ticker": t, "nt_status": nt.get("status"), "nt_rating": nt.get("rating"), "nt_conf": nt.get("confidence"), "nt_score": nt.get("score"),
            "nt_tokens": (use.get("in", 0) or 0) + (use.get("out", 0) or 0), "nt_seconds": nt.get("seconds"), "nt_health_rows": nt.get("health_rows"),
            "nt_gaps": nt.get("n_gaps"), "nt_llm": nt.get("explanation_source"),
            "ta_status": ta.get("status"), "ta_rating": ta.get("decision"), "ta_calls": ta.get("llm_calls"),
            "ta_tokens": (ta.get("input_tokens", 0) or 0) + (ta.get("output_tokens", 0) or 0), "ta_seconds": ta.get("seconds"),
            "ta_blind_fundamentals": blind_fundamentals(ta) if ta.get("status") == "ok" else None,
            "ta_ungrounded_numbers": u, "ta_numbers_in_decision": n,
            "agree": (direction(nt.get("rating")) == direction(ta.get("decision"))) if ta.get("status") == "ok" and nt.get("status") == "ok" else None,
        })
    return rows


def summarize(rows: list[dict], day: str) -> str:
    both = [r for r in rows if r["nt_status"] == "ok" and r["ta_status"] == "ok"]
    n = len(both)
    if not n:
        return "No complete pairs yet."
    pct = lambda k: 100 * sum(1 for r in both if k(r)) / n
    ta_num = sum(r["ta_numbers_in_decision"] for r in both)
    ta_un = sum(r["ta_ungrounded_numbers"] for r in both)
    dist = lambda key: ", ".join(f"{k} {sum(1 for r in both if r[key] == k)}" for k in ("Buy", "Overweight", "Hold", "Underweight", "Sell"))
    lines = [f"# Head-to-head, {day} ({n} tickers with both systems complete)",
             "Research/education only; not financial, investment or trading advice. Same Gemini key and model for both. TradingAgents ran with market, news and fundamentals analysts (social needs keys); NexTrade ran with the score, news and one Gemini narration. One run per ticker.", "",
             "| | TradingAgents | NexTrade |", "|---|---|---|",
             f"| Model calls per ticker (mean) | {mean(r['ta_calls'] for r in both):.1f} | 1 |",
             f"| Tokens per ticker (mean / median) | {mean(r['ta_tokens'] for r in both):,.0f} / {median(r['ta_tokens'] for r in both):,.0f} | {mean(r['nt_tokens'] for r in both):,.0f} / {median(r['nt_tokens'] for r in both):,.0f} |",
             f"| Seconds per ticker (mean) | {mean(r['ta_seconds'] for r in both):.0f} | {mean(r['nt_seconds'] for r in both):.0f} (includes the shared pool fetch) |",
             f"| Ticker reports with no usable fundamentals | {sum(1 for r in both if r['ta_blind_fundamentals'])} of {n} | {sum(1 for r in both if not r['nt_health_rows'])} of {n} have no business-health rows |",
             f"| Numbers in the final decision found in none of its own reports | {ta_un} of {ta_num} | not applicable: AI claims are machine-checked against the digest |",
             f"| Rating mix | {dist('ta_rating')} | {dist('nt_rating')} |",
             f"| Same direction (bullish, neutral, bearish) | {pct(lambda r: r['agree']):.0f}% of tickers | |", "",
             "Outcome quality is not judged here: record both ratings with `--record`, then run `--settle` after 21 trading sessions to score each system's ratings against the Nifty 50."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--settle", action="store_true")
    a = ap.parse_args()
    out = ROOT / "headtohead" / "results" / a.date
    rows = load(out)
    if a.record or a.settle:
        from indiafacts.journal import Journal, render_scoreboard

        dbs = {"nt": Journal(out / "nt_journal.db"), "ta": Journal(out / "ta_journal.db")}
        if a.record:
            added = 0
            for r in rows:
                if r["nt_status"] == "ok" and r["ta_status"] == "ok":
                    dbs["nt"].record(r["ticker"], date.fromisoformat(a.date), r["nt_rating"], r["nt_conf"] or "", r["nt_score"], None)
                    dbs["ta"].record(r["ticker"], date.fromisoformat(a.date), r["ta_rating"], "", None, None)
                    added += 2
            print(f"recorded {added} ratings")
        if a.settle:
            for k, j in dbs.items():
                res = j.settle(None, date.today())
                print(f"\n== {'NexTrade' if k == 'nt' else 'TradingAgents'}: settled {len(res.settled)}, could not settle {len(res.failed)}")
                print(render_scoreboard(j.scoreboard()))
        return 0
    with open(out / "summary.csv", "w", newline="") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    md = summarize(rows, a.date)
    (out / "HEAD_TO_HEAD.md").write_text(md + "\n")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
