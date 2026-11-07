"""Run NexTrade and TradingAgents over the same tickers, one after the other, with the same Gemini key and model.

    python headtohead/orchestrate.py --date 2026-11-06 --tickers indiafacts/data/pool30.txt

Resumable: a ticker whose result files exist is skipped. Stops at once when the model quota is exhausted and says so.
NexTrade side: score against a 12-name pool, news, one Gemini narration (the like-for-like single call).
Keys are read from TradingAgents/.env into the child processes' environment only; nothing is printed or written.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUOTA_WORDS = ("resource_exhausted", "quota", "429", "rate limit")


def load_env(path: Path) -> dict:
    env = dict(os.environ)
    for line in path.read_text().splitlines():
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line.strip())
        if m and m.group(2).strip():
            env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env


def run_nt(ticker: str, date: str, out: Path, env: dict) -> str:
    f = out / f"{ticker}.nt.json"
    if f.exists():
        return "skipped"
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "indiafacts", ticker, "--score", "--pool-size", "12", "--news", "--llm", "gemini", "--no-remember",
                        "--json", str(out / f"{ticker}.nt.raw.json")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=1500)
    blob = (p.stderr or "").lower()
    raw = out / f"{ticker}.nt.raw.json"
    if p.returncode == 0 and raw.exists():
        s = json.loads(raw.read_text())
        ex = s.get("explanation") or {}
        f.write_text(json.dumps({"ticker": ticker, "status": "ok", "seconds": round(time.time() - t0, 1),
                                 "rating": (s.get("debate") or {}).get("stance", {}).get("label"),
                                 "confidence": (s.get("debate") or {}).get("stance", {}).get("confidence"),
                                 "score": (s.get("score") or {}).get("overall"), "explanation_source": ex.get("source"),
                                 "usage": ex.get("usage") or {}, "n_gaps": len(s.get("gaps") or []),
                                 "health_rows": sum(1 for r in (s.get("fundamentals") or []) if r["status"] == "ok"),
                                 "bull": [x["text"] for x in (s.get("debate") or {}).get("bull", [])],
                                 "bear": [x["text"] for x in (s.get("debate") or {}).get("bear", [])],
                                 "summary": ex.get("summary", "")}, indent=1))
        return "ok"
    f.write_text(json.dumps({"ticker": ticker, "status": "error", "error": blob[-300:]}))
    return "quota" if any(w in blob for w in QUOTA_WORDS) else "error"


def run_ta(ticker: str, date: str, out: Path) -> str:
    f = out / f"{ticker}.ta.json"
    if f.exists() and json.loads(f.read_text()).get("status") == "ok":
        return "skipped"
    p = subprocess.run([str(ROOT / "TradingAgents" / ".venv" / "bin" / "python"), str(ROOT / "headtohead" / "run_ta.py"), ticker, date, str(out)],
                       cwd=ROOT / "TradingAgents", capture_output=True, text=True, timeout=3600)
    return {0: "ok", 75: "quota"}.get(p.returncode, "error")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--tickers", type=Path, default=ROOT / "indiafacts" / "data" / "pool30.txt")
    ap.add_argument("--limit", type=int, default=30)
    a = ap.parse_args()
    out = ROOT / "headtohead" / "results" / a.date
    out.mkdir(parents=True, exist_ok=True)
    env = load_env(ROOT / "TradingAgents" / ".env")
    names = [ln.strip() for ln in a.tickers.read_text().splitlines() if ln.strip() and not ln.startswith("#")][: a.limit]
    log = out / "progress.log"
    for i, t in enumerate(names, 1):
        for side, fn in (("nt", lambda: run_nt(t, a.date, out, env)), ("ta", lambda: run_ta(t, a.date, out))):
            res = fn()
            line = f"{time.strftime('%H:%M:%S')} [{i}/{len(names)}] {t} {side}: {res}"
            print(line, flush=True)
            with open(log, "a") as fh:
                fh.write(line + "\n")
            if res == "quota":
                print("QUOTA EXHAUSTED: stop here and supply another key; rerun the same command to resume.", flush=True)
                return 75
    print("all done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
