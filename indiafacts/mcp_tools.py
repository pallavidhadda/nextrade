"""Remote MCP connector for Claude (web, desktop, mobile): two tools, stateless, no keys, no user data stored.
Claude explains the returned digest in the user's own session; nothing here calls a language model."""
from __future__ import annotations

import asyncio
import json
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field, ValidationError

from indiafacts.llm import NARRATION_RULES
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
                          "When done it returns an evidence digest with ids F1, F2... plus the narration rules to follow.")
    async def get_analysis(job_id: str, wait_seconds: Annotated[int, Field(ge=0, le=40)] = 25) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds
        while True:
            j = app.state.jobs.get(job_id)
            if not j:
                return "Unknown or expired job_id. Call start_analysis again. Do not guess any figures."
            if j["status"] not in ("queued", "running") or loop.time() >= deadline:
                break
            await asyncio.sleep(1)
        if j["status"] in ("queued", "running"):
            return (f"Status: still running {j.get('progress', '')} after waiting {wait_seconds} seconds. Call get_analysis again with the same job_id "
                    "(a first run can take up to 3 minutes). Do not guess or estimate any figures while waiting.")
        if j["status"] == "error":
            return f"The analysis failed: {j.get('error', 'unknown error')}. Tell the user; do not guess any figures."
        s = j["summary"]
        gaps = "; ".join(f"{g['metric']} ({g['period']}): {g['reason']}" for g in s.get("gaps", [])[:12]) or "none found"
        return (f"DIGEST for {s['ticker']}\n{s['llm']['digest']}\n\nData gaps: {gaps}\n\n{NARRATION_RULES}\n\n{DISCLAIMER}")

    return mcp
