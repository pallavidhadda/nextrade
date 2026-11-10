"""Thin HTTP API for the web app: submit a ticker, poll a job, fetch the summary and the self-contained report.
Education only; not financial, investment or trading advice. No user-supplied paths ever reach the analysis."""
from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from indiafacts.render import DISCLAIMER
from indiafacts.runner import TICKER, Runner, subprocess_runner  # noqa: F401  (re-exported)

CACHE_SECONDS = 3600
JOB_KEEP_SECONDS = 6 * 3600


FACT_COLUMNS = ["fact_id", "metric", "value", "unit", "period_end", "period_type", "basis", "source", "status", "reason", "evidence"]
_TEXT_COLUMNS = {"metric", "unit", "source", "reason", "evidence"}


def _csv_text(v) -> str:
    """Text from third-party sources must not be read as a spreadsheet formula."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    horizon: Literal["<1y", "1-3y", "3-5y", "5y+"] | None = None
    risk_tolerance: Literal["low", "medium", "high"] | None = None
    risk_capacity: Literal["low", "medium", "high"] | None = None
    experience: Literal["beginner", "expert"] | None = None
    refresh: bool = False          # true skips any precomputed snapshot and runs live

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not TICKER.match(v) or v.startswith("-"):
            raise ValueError("ticker must look like RELIANCE or RELIANCE.NS")
        from indiafacts.companies import resolve

        chosen, sugg = resolve(v)
        if chosen is None and sugg:
            raise ValueError(f"{v} is not a listed ticker. Did you mean: " + ", ".join(m.label for m in sugg[:3]) + "?")
        return v


class Busy(Exception):
    pass


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw: str = Field(max_length=20000)
    model: str | None = Field(default=None, max_length=80)


BUSY_MESSAGE = "The server is busy with another analysis; try again in a minute."


def create_app(runner: Runner = subprocess_runner, max_running: int | None = None, per_minute: int = 6, claim_runner=None, snapshots="env") -> FastAPI:
    if max_running is None:
        max_running = int(os.environ.get("INDIAFACTS_MAX_RUNNING", "2"))
    holder: dict = {}
    if snapshots == "env":
        from indiafacts.snapshots import client_from_env

        snapshots = client_from_env()          # None when INDIAFACTS_SNAPSHOT_BASE is unset: live analysis only

    def log(msg: str) -> None:
        print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)

    log(f"nextrade-api starting: pool_size={os.environ.get('INDIAFACTS_POOL_SIZE', 'default')} "
        f"workers={os.environ.get('INDIAFACTS_WORKERS', 'default')} max_running={max_running} nice={os.environ.get('INDIAFACTS_NICE', '10')}")

    @asynccontextmanager
    async def lifespan(_app):
        mcp = holder.get("mcp")
        if mcp is None:
            yield
        else:
            async with mcp.session_manager.run():
                yield

    app = FastAPI(title="NexTrade API", docs_url=None, redoc_url=None, lifespan=lifespan)
    origins = [o for o in os.environ.get("INDIAFACTS_CORS", "").split(",") if o]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["content-type"])
    jobs: dict[str, dict] = {}
    hits: dict[str, list[float]] = {}
    trust_proxy = os.environ.get("INDIAFACTS_TRUST_PROXY") == "1"

    mcp_token = os.environ.get("INDIAFACTS_MCP_TOKEN", "")

    @app.middleware("http")
    async def headers(request: Request, call_next):
        if mcp_token and request.url.path.startswith("/mcp"):
            given = request.headers.get("authorization", "")
            if not hmac.compare_digest(given.encode(), f"Bearer {mcp_token}".encode()):
                return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"www-authenticate": "Bearer"})
        resp = await call_next(request)
        resp.headers.setdefault("x-content-type-options", "nosniff")
        resp.headers.setdefault("referrer-policy", "no-referrer")
        resp.headers.setdefault("cache-control", "no-store")
        return resp

    def client_key(request: Request) -> str:
        if trust_proxy and request.headers.get("x-forwarded-for"):
            return request.headers["x-forwarded-for"].split(",")[0].strip()
        return request.client.host if request.client else "?"
    cache: dict[str, tuple[float, str]] = {}
    lock = threading.Lock()

    def running() -> int:
        return sum(1 for j in jobs.values() if j["status"] in ("queued", "running"))

    def work(job_id: str, opts: dict) -> None:
        j = jobs[job_id]
        j["status"] = "running"
        log(f"job {job_id} started {opts.get('ticker')}")
        t0 = time.time()
        try:
            res = runner(opts, lambda p: j.__setitem__("progress", p))
            res["summary"]["served_from"] = "live"
            j.update(status="done", summary=res["summary"], html=res["html"], served_from="live")
            log(f"job {job_id} done in {time.time() - t0:.0f}s")
        except (ValueError, TimeoutError) as exc:
            j.update(status="error", error=str(exc)[:300].replace(os.path.expanduser("~"), "~") or "analysis failed")
            log(f"job {job_id} failed after {time.time() - t0:.0f}s: {type(exc).__name__}: {str(exc)[:200]}")
        except Exception as exc:
            j.update(status="error", error=f"analysis failed ({type(exc).__name__})")
            log(f"job {job_id} crashed after {time.time() - t0:.0f}s: {type(exc).__name__}")

    @app.get("/api/health")
    def health():
        return {"ok": True, "disclaimer": DISCLAIMER}

    def from_snapshot(opts: dict) -> str | None:
        """An already-completed job built from a fresh precomputed snapshot, or None.
        Snapshots are computed with the labelled default profile, so a request that sets any profile field runs live."""
        if any(v is not None for k, v in opts.items() if k != "ticker"):
            return None
        snap = snapshots.lookup(opts["ticker"]) if snapshots is not None else None
        if snap is None:
            return None
        summary = dict(snap["summary"], served_from="snapshot", snapshot_as_of=snap["as_of"])
        job_id = uuid.uuid4().hex[:16]
        with lock:
            jobs[job_id] = {"status": "done", "created": time.time(), "progress": "", "summary": summary, "html": snap["html"],
                            "served_from": "snapshot", "snapshot_as_of": snap["as_of"]}
        log(f"job {job_id} served from snapshot {opts['ticker']} as_of {snap['as_of']}")
        return job_id

    def submit(opts: dict, who: str, refresh: bool = False) -> tuple[str, bool]:
        refresh = refresh or bool(opts.get("refresh"))
        opts = {k: v for k, v in opts.items() if k != "refresh"}
        if not refresh:
            snap_id = from_snapshot(opts)
            if snap_id:
                return snap_id, True
        key = repr(sorted(opts.items()))
        with lock:
            now = time.time()
            for k in [k for k, j in jobs.items() if now - j["created"] > JOB_KEEP_SECONDS]:
                jobs.pop(k, None)
            for k in [k for k, w in hits.items() if not w or now - w[-1] >= 60]:          # forget connections idle for a minute
                hits.pop(k, None)
            for k in [k for k, (t, jid) in cache.items() if now - t >= CACHE_SECONDS or jid not in jobs]:
                cache.pop(k, None)
            window = hits.setdefault(who, [])
            window[:] = [t for t in window if now - t < 60]
            if len(window) >= per_minute:
                raise Busy("Too many requests from this connection; wait a minute.")
            window.append(now)
            hit = None if refresh else cache.get(key)
            if hit and now - hit[0] < CACHE_SECONDS and hit[1] in jobs and jobs[hit[1]]["status"] == "done":
                return hit[1], True
            if running() >= max_running:
                raise Busy(BUSY_MESSAGE)
            job_id = uuid.uuid4().hex[:16]
            jobs[job_id] = {"status": "queued", "created": now, "progress": ""}
            cache[key] = (now, job_id)
        threading.Thread(target=work, args=(job_id, opts), daemon=True).start()
        return job_id, False

    from indiafacts.runner import claim_runner as _default_claim

    app.state.submit, app.state.jobs = submit, jobs
    app.state.claim_runner = claim_runner or _default_claim

    @app.post("/api/analyze", status_code=202)
    def analyze(req: AnalyzeRequest, request: Request, refresh: bool = False):
        try:
            job_id, cached = submit(req.model_dump(exclude={"refresh"}), client_key(request), refresh or req.refresh)
        except Busy as exc:
            raise HTTPException(429, str(exc))
        return {"job_id": job_id, "cached": cached, "served_from": jobs[job_id].get("served_from", "live")}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        j = jobs.get(job_id)
        if not j:
            raise HTTPException(404, "unknown job")
        out = {k: j[k] for k in ("status", "progress", "summary", "error", "served_from", "snapshot_as_of") if k in j}
        if out.get("summary"):
            out["summary"] = {k: v for k, v in out["summary"].items() if k != "facts"}      # the web page does not need them; the CSV route does
        return out

    @app.get("/api/jobs/{job_id}/facts.csv")
    def facts_csv(job_id: str):
        j = jobs.get(job_id)
        if not j or j["status"] != "done":
            raise HTTPException(404, "no facts for this job")
        summary = j.get("summary") or {}
        facts = summary.get("facts")
        if facts is None:
            raise HTTPException(404, "this result carries no per-fact data")
        buf = io.StringIO(newline="")
        buf.write(f"# {DISCLAIMER}\n")
        if summary.get("facts_total") is not None and summary["facts_total"] > len(facts):
            buf.write(f"# {len(facts)} of {summary['facts_total']} facts included (size cap)\n")
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(FACT_COLUMNS)
        for f in facts:
            w.writerow([_csv_text(f.get(c)) if c in _TEXT_COLUMNS else ("" if f.get(c) is None else f.get(c)) for c in FACT_COLUMNS])
        t = re.sub(r"[^A-Za-z0-9_-]", "", str(summary.get("ticker", "facts")).split(".")[0]) or "facts"
        d = str(summary.get("retrieved_at", ""))[:10]
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"content-disposition": f'attachment; filename="nextrade_{t}_{d}_facts.csv"', "x-content-type-options": "nosniff"})

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
    def report(job_id: str, download: int = 0, embed: int = 0):
        j = jobs.get(job_id)
        if not j or j["status"] != "done":
            raise HTTPException(404, "no report for this job")
        html = j["html"]
        if embed and not download:
            # Shown inside the web page: always the light page theme, and it tells the parent how tall it is so the page scrolls, not the frame.
            html = html.replace('<html lang="en">', '<html lang="en" data-theme="light" data-embed="1">', 1)
            html = html.replace("</body>", "<script>(function(){function p(){parent.postMessage({nt:'report-height',h:document.body.offsetHeight},'*')}"
                                "addEventListener('load',p);if(window.ResizeObserver)new ResizeObserver(p).observe(document.body);p()})()</script></body>", 1)
        extra = {}
        if download:
            t = re.sub(r"[^A-Za-z0-9_-]", "", str((j.get("summary") or {}).get("ticker", "report")).split(".")[0]) or "report"
            d = str((j.get("summary") or {}).get("retrieved_at", ""))[:10]
            extra["content-disposition"] = f'attachment; filename="nextrade_{t}_{d}.html"'
        return HTMLResponse(html, headers={**extra,
            "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:",
            "x-content-type-options": "nosniff"})

    from indiafacts.mcp_tools import build_mcp

    hosts = [h for h in os.environ.get("INDIAFACTS_MCP_HOSTS", "").split(",") if h]
    mcp = build_mcp(app, hosts or None)
    holder["mcp"] = mcp
    app.mount("/", mcp.streamable_http_app())          # last, so /api routes win; the connector URL is /mcp
    return app


app = create_app()
