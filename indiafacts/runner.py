"""Run one analysis in its own process and read its JSON and HTML outputs. Shared by the HTTP API and the Streamlit app.
No keys are passed to the child. Education only; not financial, investment or trading advice."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

TICKER = re.compile(r"^[A-Za-z0-9&\-]{1,20}(\.(NS|BO))?$")
Runner = Callable[[dict, Callable[[str], None]], dict]


def subprocess_runner(opts: dict, progress: Callable[[str], None]) -> dict:
    """Run the CLI in its own process (own stdout, own timeout); read its JSON and HTML outputs."""
    with tempfile.TemporaryDirectory() as d:
        out_json, out_html = Path(d) / "s.json", Path(d) / "r.html"
        argv = [sys.executable, "-m", "indiafacts", opts["ticker"], "--score", "--explain", "--news", "--json", str(out_json), "--html", str(out_html)]
        labels = os.environ.get("INDIAFACTS_LABELS")
        if labels and Path(labels).exists():
            argv += ["--universe", labels, "--sector-pool"]
        if os.environ.get("INDIAFACTS_POOL_SIZE", "").isdigit():
            argv += ["--pool-size", os.environ["INDIAFACTS_POOL_SIZE"]]                  # smaller pool: faster on a small free host
        for flag, key in (("--horizon", "horizon"), ("--risk-tolerance", "risk_tolerance"),
                          ("--risk-capacity", "risk_capacity"), ("--experience", "experience")):
            if opts.get(key):
                argv += [flag, opts[key]]
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}      # the analysis needs no keys
        def _lower_priority() -> None:                                                         # keep the web server answering health checks
            try:
                os.nice(int(os.environ.get("INDIAFACTS_NICE", "10")))
            except (AttributeError, OSError, ValueError):
                pass

        proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env,
                                preexec_fn=_lower_priority if os.name == "posix" else None)
        tail: list[str] = []
        deadline = time.time() + 600
        for line in proc.stderr:                                                       # type: ignore[union-attr]
            line = line.strip()
            if re.match(r"^\[\d+/\d+\]", line):
                progress(line)
            elif line:
                tail = (tail + [line])[-3:]
            if time.time() > deadline:
                proc.kill()
                raise TimeoutError("analysis took too long")
        code = proc.wait()
        try:
            import resource

            print(f"analysis child exit={code} peak_memory_mb={resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // (1024 if sys.platform != 'darwin' else 1024 * 1024)}", file=sys.stderr, flush=True)
        except Exception:
            pass
        if code != 0 or not out_json.exists():
            raise ValueError(next((t[7:] for t in reversed(tail) if t.startswith("error: ")), "analysis failed"))
        return {"summary": json.loads(out_json.read_text(encoding="utf-8")), "html": out_html.read_text(encoding="utf-8")}
