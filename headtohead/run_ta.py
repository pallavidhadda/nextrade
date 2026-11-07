"""Run TradingAgents once and save what the comparison needs. Run from the TradingAgents folder with its own venv:

    cd TradingAgents && .venv/bin/python ../headtohead/run_ta.py TCS.NS 2026-11-06 ../headtohead/results/2026-11-06

Analysts: market, news, fundamentals (social needs Reddit or StockTwits keys, so it is left out and the report says so).
Exit codes: 0 done, 75 the model quota is exhausted (stop and ask for another key), 1 any other failure.
"""
import json
import sys
import threading
import time
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

MIN_GAP_SECONDS = 4.5      # Gemini free tier: 15 requests a minute
QUOTA_WORDS = ("resource_exhausted", "quota", "429", "rate limit", "rate_limit")


class Meter(BaseCallbackHandler):
    def __init__(self):
        self.lock, self.last, self.calls = threading.Lock(), 0.0, []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        with self.lock:
            wait = self.last + MIN_GAP_SECONDS - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()

    def on_llm_end(self, response, **kwargs):
        meta = {}
        for gens in response.generations:
            for g in gens:
                m = getattr(getattr(g, "message", None), "usage_metadata", None)
                if m:
                    meta = m
        self.calls.append({"input": meta.get("input_tokens", 0), "output": meta.get("output_tokens", 0)})


def main() -> int:
    ticker, date, out_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    meter = Meter()
    t0 = time.time()
    ta = TradingAgentsGraph(selected_analysts=("market", "news", "fundamentals"), debug=False, config=DEFAULT_CONFIG.copy(), callbacks=[meter])
    try:
        state, decision = ta.propagate(ticker, date)
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}".lower()
        quota = any(w in text for w in QUOTA_WORDS)
        (out_dir / f"{ticker}.ta.json").write_text(json.dumps({"ticker": ticker, "status": "quota" if quota else "error",
                                                              "error": text[:400], "calls": meter.calls}, indent=1))
        return 75 if quota else 1
    reports = {k: (state.get(k) or "") for k in ("market_report", "news_report", "fundamentals_report", "sentiment_report")}
    out = {"ticker": ticker, "date": date, "status": "ok", "decision": str(decision), "final_trade_decision": state.get("final_trade_decision", ""),
           "calls": meter.calls, "llm_calls": len(meter.calls), "input_tokens": sum(c["input"] for c in meter.calls),
           "output_tokens": sum(c["output"] for c in meter.calls), "seconds": round(time.time() - t0, 1), "reports": reports}
    (out_dir / f"{ticker}.ta.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
