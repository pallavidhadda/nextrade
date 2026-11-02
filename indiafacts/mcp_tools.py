"""Remote MCP connector for Claude (web, desktop, mobile): two tools, stateless, no keys, no user data stored.
Claude explains the returned digest in the user's own session; nothing here calls a language model."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field, ValidationError

from indiafacts.llm import NARRATION_RULES, NARRATION_RULES_FULL
from indiafacts.render import DISCLAIMER

INSTRUCTIONS = (
    "NexTrade gathers source-linked facts about NSE/BSE companies for education. Call start_analysis with a ticker, then call "
    "get_analysis with the job_id every 15 to 20 seconds until it returns a DIGEST (a first run can take 1 to 3 minutes). "
    "Explain only what the digest says, cite its F-ids, separate facts from inferences, state the data gaps, never give "
    "buy/sell/hold advice or targets, and end with the disclaimer."
)


def build_mcp(app, allowed_hosts: list[str] | None = None) -> FastMCP:
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=bool(allowed_hosts), allowed_hosts=allowed_hosts or [],
                                    allowed_origins=["https://claude.ai", "https://claude.com"] if allowed_hosts else [])
    mcp = FastMCP("NexTrade", instructions=INSTRUCTIONS, stateless_http=True, json_response=True,
                  streamable_http_path="/mcp", transport_security=sec)

    @mcp.tool(description="Start a research run for one Indian listed company (education only, not financial advice). "
                          "Returns a job_id; then call get_analysis. Profile options only change how the factor score is weighted.")
    def start_analysis(ticker: str, horizon: Literal["<1y", "1-3y", "3-5y", "5y+"] | None = None,
                       risk_tolerance: Literal["low", "medium", "high"] | None = None,
                       risk_capacity: Literal["low", "medium", "high"] | None = None,
                       experience: Literal["beginner", "expert"] | None = None) -> str:
        from indiafacts.api import AnalyzeRequest, Busy

        try:
            req = AnalyzeRequest(ticker=ticker, horizon=horizon, risk_tolerance=risk_tolerance,
                                 risk_capacity=risk_capacity, experience=experience)
        except ValidationError as exc:
            raise ValueError("ticker must look like RELIANCE or RELIANCE.NS") from exc
        try:
            job_id, cached = app.state.submit(req.model_dump(), "mcp")
        except Busy as exc:
            raise ValueError(str(exc)) from exc
        return json.dumps({"job_id": job_id, "cached": cached, "next": "call get_analysis with this job_id in 15 to 20 seconds"})

    @mcp.tool(description="Get the result of start_analysis. The call waits on the server for up to wait_seconds (default 25) for the job to finish, "
                          "so just call it again if it says running; do not guess any figures. "
                          "Pass the ticker too: if the server restarted and lost the job, a new run starts automatically and the answer says which job_id to use. When done it returns an evidence digest with ids F1, F2... plus the narration rules to follow (detail=full gives a 9-section report; brief gives 5 bullets).")
    async def get_analysis(job_id: str, wait_seconds: Annotated[int, Field(ge=0, le=40)] = 25,
                           detail: Literal["full", "brief"] = "full", ticker: str | None = None) -> str:
        from indiafacts.api import AnalyzeRequest, Busy

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds
        restarted = ""
        while True:
            j = app.state.jobs.get(job_id)
            if not j:
                if ticker and not restarted:
                    try:
                        req = AnalyzeRequest(ticker=ticker)
                        job_id, _ = app.state.submit(req.model_dump(), "mcp")
                    except (ValidationError, Busy):
                        return "Unknown or expired job_id. Call start_analysis again. Do not guess any figures."
                    restarted = (f"The server restarted and lost the earlier job, so a fresh run for {req.ticker} was started. "
                                 f"Use this new job_id from now on: {job_id}. ")
                    continue
                return "Unknown or expired job_id. Call start_analysis again. Do not guess any figures."
            if j["status"] not in ("queued", "running") or loop.time() >= deadline:
                break
            await asyncio.sleep(1)
        if j["status"] in ("queued", "running"):
            return (f"{restarted}Status: still running {j.get('progress', '')} after waiting {wait_seconds} seconds. Call get_analysis again with the same job_id "
                    "(a first run can take up to 3 minutes). Do not guess or estimate any figures while waiting.")
        if j["status"] == "error":
            return f"The analysis failed: {j.get('error', 'unknown error')}. Tell the user; do not guess any figures."
        s = j["summary"]
        gaps = "; ".join(f"{g['metric']} ({g['period']}): {g['reason']}" for g in s.get("gaps", [])[:12]) or "none found"
        base = (os.environ.get("INDIAFACTS_PUBLIC_URL") or "").rstrip("/")
        link = (f"\n\nFull interactive report (charts, tables; open in a browser): {base}/api/jobs/{job_id}/report" if base else "")
        rules = NARRATION_RULES_FULL if detail == "full" else NARRATION_RULES
        return (f"{restarted}DIGEST for {s['ticker']}\n{s['llm']['digest']}\n\nData gaps: {gaps}\n\n{rules}{link}\n\n{DISCLAIMER}")

    @mcp.tool(description="Check one stated figure about an Indian listed company (for example 'TCS EPS was 142.66') against sourced facts. "
                          "Returns supported, contradicted, supported only by an unverified source, or unverifiable, with the sources. "
                          "State the unit (crore, lakh_crore, inr, per_share, ratio or percent) and, for quarterly or annual figures, the period such as 'Q2 FY27' or 'FY26'.")
    async def check_claim(ticker: str, metric: str, value: float, unit: Literal["inr", "crore", "lakh_crore", "per_share", "ratio", "percent"],
                          period: str | None = None) -> str:
        from indiafacts.api import AnalyzeRequest

        try:
            tk = AnalyzeRequest(ticker=ticker).ticker
        except ValidationError as exc:
            raise ValueError("ticker must look like RELIANCE or RELIANCE.NS") from exc
        opts = {"ticker": tk, "metric": metric[:60], "value": value, "unit": unit, "period": (period or "")[:20] or None}
        try:
            r = await asyncio.to_thread(app.state.claim_runner, opts)
        except Exception:
            return "The claim could not be checked right now (data source unreachable or no data). Do not guess; tell the user it is unverified."
        lines = [f"CLAIM CHECK for {tk}: {r['verdict'].upper()}", r["explanation"]]
        for m in r.get("matches", [])[:4]:
            lines.append(f"- {m['source']} {m['period']} = {m['value']} ({m['status']}); {m['evidence'] or 'no evidence note'}")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    return mcp
