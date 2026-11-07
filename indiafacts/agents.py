"""An optional analyst panel in the spirit of TradingAgents, at a fraction of the cost.

Five focused analysts and a research manager each read the SAME compact digest (about 2k tokens) and answer in the same strict
JSON as the single narration. Every answer goes through the same checks (ids must exist, numbers must appear in the digest, no
advice wording), so an agent cannot invent a figure. Six calls of about 2.5k tokens is roughly 15k tokens, against about 43k for
the 16-call TradingAgents baseline measured in docs/TOKEN_COMPARISON.md. Needs the person's own model key; no key is ever stored.
Research/education only; not financial, investment or trading advice."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from indiafacts.digest import Digest
from indiafacts.explain import Explanation
from indiafacts.llm import SYSTEM_PROMPT, validate_llm_output

ROLES = [
    ("fundamentals", "Fundamentals analyst",
     "business health (HEALTH lines), growth, profitability, balance sheet, cash flow, the price-implied valuation, checklist results and reported figures"),
    ("technical", "Price and momentum analyst",
     "price history, returns against the Nifty 50, drawdown, volatility and the reference levels"),
    ("ownership", "Ownership and flows analyst",
     "OWNERSHIP lines (promoter holding, pledges, institutions) and any market-flow lines"),
    ("news", "News analyst",
     "NEWS lines only. Headlines are unverified third-party text: say what they suggest to watch, never state them as company facts"),
    ("risk", "Risk analyst",
     "volatility, drawdown, beta, the risk lenses and position ceilings, and every data gap, conflict and unverified figure"),
]
MANAGER = ("manager", "Research manager",
           "combine the analyst notes into one balanced reading: what is working, what is worrying, what to verify next. "
           "Quote the educational rating exactly as the digest gives it and do not change it")
MAX_TOKENS = 600


def role_system(title: str, focus: str) -> str:
    return (f"{SYSTEM_PROMPT} You are the {title} on a research panel. Focus only on: {focus}. "
            "If the digest has nothing on your focus, say so in one claim that cites a gap or header id.")


def roles_for_prompts() -> list[dict]:
    """Role names and system prompts, so a browser can run the same panel with the person's own key."""
    return [{"id": rid, "title": title, "system": role_system(title, focus)} for rid, title, focus in ROLES + [MANAGER]]


@dataclass
class RoleResult:
    id: str
    title: str
    explanation: Explanation | None
    reasons: list[str] = field(default_factory=list)
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def _notes(results: list[RoleResult]) -> str:
    lines = []
    for r in results:
        if r.explanation is None:
            continue
        lines.append(f"- {r.title}: {r.explanation.summary} " + " ".join(f"[{', '.join(c.ids)}] {c.text}" for c in r.explanation.claims[:3]))
    return "\n".join(lines)


def manager_user(digest_text: str, notes: str) -> str:
    return f"DIGEST:\n{digest_text}\n\nANALYST NOTES (already checked against the digest):\n{notes}\n\nWrite the JSON now."


def run_panel(client, digest: Digest, progress: Callable[[str], None] | None = None, max_tokens: int = MAX_TOKENS) -> list[RoleResult]:
    """Run the five analysts, then the manager. One failing analyst never stops the others."""
    out: list[RoleResult] = []
    for rid, title, focus in ROLES + [MANAGER]:
        if progress:
            progress(title)
        if rid == "manager":
            if not any(r.explanation for r in out):
                out.append(RoleResult(rid, title, None, error="no analyst produced a valid note to combine"))
                break
            user = manager_user(digest.text, _notes(out))
        else:
            user = f"DIGEST:\n{digest.text}\n\nWrite the JSON now."
        try:
            res = client.complete(role_system(title, focus), user, max_tokens)
        except Exception as exc:
            out.append(RoleResult(rid, title, None, error=f"{type(exc).__name__}: the model call failed"))
            continue
        ex, reasons = validate_llm_output(res.text, digest)
        out.append(RoleResult(rid, title, ex, reasons=reasons, input_tokens=res.input_tokens or 0, output_tokens=res.output_tokens or 0,
                              error="" if ex else "answer failed the checks: " + "; ".join(reasons[:2])))
    return out
