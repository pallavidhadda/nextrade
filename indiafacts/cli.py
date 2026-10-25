from __future__ import annotations

import argparse
import sys
import time
from datetime import date

from indiafacts.pipeline import build_factset
from indiafacts.render import render


def main(argv: list[str] | None = None, client=None, sleep=time.sleep) -> int:
    p = argparse.ArgumentParser(prog="indiafacts", description="Source-linked facts for an NSE/BSE ticker.")
    p.add_argument("ticker", help="e.g. RELIANCE.NS")
    p.add_argument("--as-of", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    args = p.parse_args(argv)
    try:
        fs = build_factset(args.ticker, as_of=args.as_of, client=client, sleep=sleep)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(render(fs, as_of=args.as_of))
    return 0
