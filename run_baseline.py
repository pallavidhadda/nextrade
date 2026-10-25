"""Baseline run of TradingAgents with a rate limiter and per-call token log.

Usage (from the TradingAgents folder, so its .env is found):
    .venv/bin/python ../run_baseline.py RELIANCE.NS 2026-10-23 market,fundamentals
"""
import json
import sys
import threading
import time

from langchain_core.callbacks import BaseCallbackHandler

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

MIN_GAP_SECONDS = 4.5  # Gemini free tier: 15 requests/min


class ThrottleAndCount(BaseCallbackHandler):
    def __init__(self):
        self.lock = threading.Lock()
        self.last = 0.0
        self.calls = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        with self.lock:
            wait = self.last + MIN_GAP_SECONDS - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()

    def on_llm_end(self, response, **kwargs):
        usage = {}
        for gens in response.generations:
            for g in gens:
                meta = getattr(getattr(g, "message", None), "usage_metadata", None)
                if meta:
                    usage = meta
        self.calls.append({"input": usage.get("input_tokens", 0),
                           "output": usage.get("output_tokens", 0)})
        print(f"  call {len(self.calls)}: in={self.calls[-1]['input']} out={self.calls[-1]['output']}",
              flush=True)


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"
    date = sys.argv[2] if len(sys.argv) > 2 else "2026-10-23"
    analysts = tuple((sys.argv[3] if len(sys.argv) > 3 else "market,fundamentals").split(","))

    counter = ThrottleAndCount()
    ta = TradingAgentsGraph(selected_analysts=analysts, debug=False,
                            config=DEFAULT_CONFIG.copy(), callbacks=[counter])
    _, decision = ta.propagate(ticker, date)

    total_in = sum(c["input"] for c in counter.calls)
    total_out = sum(c["output"] for c in counter.calls)
    summary = {"ticker": ticker, "date": date, "analysts": analysts,
               "llm_calls": len(counter.calls), "input_tokens": total_in,
               "output_tokens": total_out, "decision": decision}
    print(json.dumps(summary, indent=2))
    with open(f"../baseline_{ticker}_{date}.json", "w") as f:
        json.dump({**summary, "calls": counter.calls}, f, indent=2)


if __name__ == "__main__":
    main()
