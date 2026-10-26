"""Thin HTTP API for the web app: submit a ticker, poll a job, fetch the summary and the self-contained report.
Education only; not financial, investment or trading advice. No user-supplied paths ever reach the analysis."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from indiafacts.render import DISCLAIMER

TICKER = re.compile(r"^[A-Za-z0-9&\-]{1,20}(\.(NS|BO))?$")
CACHE_SECONDS = 3600
JOB_KEEP_SECONDS = 6 * 3600
Runner = Callable[[dict, Callable[[str], None]], dict]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    horizon: Literal["<1y", "1-3y", "3-5y", "5y+"] | None = None
    risk_tolerance: Literal["low", "medium", "high"] | None = None
    risk_capacity: Literal["low", "medium", "high"] | None = None
    experience: Literal["beginner", "expert"] | None = None

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not TICKER.match(v) or v.startswith("-"):
            raise ValueError("ticker must look like RELIANCE or RELIANCE.NS")
        return v


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw: str = Field(max_length=20000)
    model: str | None = Field(default=None, max_length=80)


def subprocess_runner(opts: dict, progress: Callable[[str], None]) -> dict:
    """Run the CLI in its own process (own stdout, own timeout); read its JSON and HTML outputs."""
    with tempfile.TemporaryDirectory() as d:
        out_json, out_html = Path(d) / "s.json", Path(d) / "r.html"
        argv = [sys.executable, "-m", "indiafacts", opts["ticker"], "--score", "--explain", "--json", str(out_json), "--html", str(out_html)]
        labels = os.environ.get("INDIAFACTS_LABELS")
        if labels and Path(labels).exists():
            argv += ["--universe", labels, "--sector-pool"]
        for flag, key in (("--horizon", "horizon"), ("--risk-tolerance", "risk_tolerance"),
                          ("--risk-capacity", "risk_capacity"), ("--experience", "experience")):
            if opts.get(key):
                argv += [flag, opts[key]]
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}      # the analysis needs no keys
        proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env)
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
        if code != 0 or not out_json.exists():
            raise ValueError(next((t[7:] for t in reversed(tail) if t.startswith("error: ")), "analysis failed"))
        import json

        return {"summary": json.loads(out_json.read_text(encoding="utf-8")), "html": out_html.read_text(encoding="utf-8")}


def create_app(runner: Runner = subprocess_runner, max_running: int = 2) -> FastAPI:
    app = FastAPI(title="NexTrade API", docs_url=None, redoc_url=None)
    origins = [o for o in os.environ.get("INDIAFACTS_CORS", "").split(",") if o]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["content-type"])
    jobs: dict[str, dict] = {}
    cache: dict[str, tuple[float, str]] = {}
    lock = threading.Lock()

    def running() -> int:
        return sum(1 for j in jobs.values() if j["status"] in ("queued", "running"))

    def work(job_id: str, opts: dict) -> None:
        j = jobs[job_id]
        j["status"] = "running"
        try:
            res = runner(opts, lambda p: j.__setitem__("progress", p))
            j.update(status="done", summary=res["summary"], html=res["html"])
        except (ValueError, TimeoutError) as exc:
            j.update(status="error", error=str(exc)[:300].replace(os.path.expanduser("~"), "~") or "analysis failed")
        except Exception as exc:
            j.update(status="error", error=f"analysis failed ({type(exc).__name__})")

    @app.get("/api/health")
    def health():
        return {"ok": True, "disclaimer": DISCLAIMER}

    @app.post("/api/analyze", status_code=202)
    def analyze(req: AnalyzeRequest):
        opts = req.model_dump()
        key = repr(sorted(opts.items()))
        with lock:
            now = time.time()
            for k in [k for k, j in jobs.items() if now - j["created"] > JOB_KEEP_SECONDS]:
                jobs.pop(k, None)
            hit = cache.get(key)
            if hit and now - hit[0] < CACHE_SECONDS and hit[1] in jobs and jobs[hit[1]]["status"] == "done":
                return {"job_id": hit[1], "cached": True}
            if running() >= max_running:
                raise HTTPException(429, "The service is busy with other analyses; try again in a minute.")
            job_id = uuid.uuid4().hex[:16]
            jobs[job_id] = {"status": "queued", "created": now, "progress": ""}
            cache[key] = (now, job_id)
        threading.Thread(target=work, args=(job_id, opts), daemon=True).start()
        return {"job_id": job_id, "cached": False}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        j = jobs.get(job_id)
        if not j:
            raise HTTPException(404, "unknown job")
        return {k: j[k] for k in ("status", "progress", "summary", "error") if k in j}

    @app.post("/api/jobs/{job_id}/validate")
    def validate(job_id: str, req: ValidateRequest):
        """Check a model's answer against the stored digest. The caller's own model produced it; no key ever reaches us."""
        from indiafacts.digest import Digest
        from indiafacts.llm import validate_llm_output

        j = jobs.get(job_id)
        llm = (j or {}).get("summary", {}).get("llm") if j and j["status"] == "done" else None
        if not llm:
            raise HTTPException(404, "no digest for this job")
        d = Digest(text=llm["digest"], ids={i: "" for i in llm["ids"]}, items={}, by_key={}, est_tokens=0)
        ex, reasons = validate_llm_output(req.raw, d)
        if ex is None:
            return {"explanation": None, "reasons": reasons}
        body = ex.model_dump()
        body["source"] = "your model"
        return {"explanation": body, "reasons": reasons}

    @app.get("/api/jobs/{job_id}/report", response_class=HTMLResponse)
    def report(job_id: str):
        j = jobs.get(job_id)
        if not j or j["status"] != "done":
            raise HTTPException(404, "no report for this job")
        return HTMLResponse(j["html"], headers={
            "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:",
            "x-content-type-options": "nosniff"})

    return app


app = create_app()
