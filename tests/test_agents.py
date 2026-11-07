import json

from indiafacts.agents import ROLES, run_panel, roles_for_prompts
from indiafacts.digest import Digest
from indiafacts.llm import LLMResult

D = Digest(text="F1 ENTITY X | profit 142.66 | HEALTH ROCE 54.9%\nF2 GAP none", ids={"F1": "", "F2": ""}, items={}, by_key={}, est_tokens=0)
GOOD = json.dumps({"summary": "Profit per share is 142.66.", "claims": [{"type": "fact", "text": "Earnings per share are 142.66.", "ids": ["F1"]},
                                                              {"type": "inference", "text": "Capital returns look strong at 54.9%.", "ids": ["F1"]}],
                   "uncertainty": "Little data."})


class Fake:
    def __init__(self, fail_on=None, bad_on=None):
        self.calls, self.fail_on, self.bad_on = [], fail_on, bad_on

    def complete(self, system, user, max_tokens):
        self.calls.append((system, user))
        n = len(self.calls)
        if n == self.fail_on:
            raise TimeoutError()
        if n == self.bad_on:
            return LLMResult(text=GOOD.replace("142.66", "999"), input_tokens=10, output_tokens=5)
        return LLMResult(text=GOOD, input_tokens=10, output_tokens=5)


def test_panel_runs_five_analysts_then_a_manager_who_sees_their_notes():
    c = Fake()
    res = run_panel(c, D)
    assert [r.id for r in res] == [r[0] for r in ROLES] + ["manager"] and len(c.calls) == 6
    assert all(r.explanation is not None for r in res)
    assert "ANALYST NOTES" in c.calls[-1][1] and "Fundamentals analyst" in c.calls[-1][1]
    assert "Fundamentals analyst" in c.calls[0][0] and "ANALYST NOTES" not in c.calls[0][1]


def test_one_failure_or_invented_number_never_stops_the_panel():
    res = run_panel(Fake(fail_on=2, bad_on=3), D)
    assert res[1].explanation is None and "model call failed" in res[1].error
    assert res[2].explanation is None and "not in digest" in res[2].error            # 999 is not in the digest
    assert res[0].explanation is not None and res[-1].explanation is not None


def test_prompts_for_a_browser_cover_all_roles():
    p = roles_for_prompts()
    assert len(p) == 6 and all("Never advise buying" in x["system"] for x in p)


def test_streamlit_ai_run_checks_answers_and_never_returns_the_key():
    from indiafacts.webui import ai_run, ai_html

    block = {"digest": D.text, "ids": ["F1", "F2"], "system": "S", "user": "U", "max_tokens": 700}
    seen = {}

    def post(url, headers, body, timeout=60):
        seen["h"] = repr(headers) + repr(body)
        return {"candidates": [{"content": {"parts": [{"text": GOOD}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}

    out = ai_run(block, "Gemini", "", "", "SECRETKEY", panel=False, post=post)
    assert out["results"][0]["error"] == "" and out["results"][0]["claims"]
    assert "SECRETKEY" not in repr(out) and "SECRETKEY" not in ai_html(out)
    panel = ai_run(block, "Gemini", "", "", "SECRETKEY", panel=True, post=post)
    assert len(panel["results"]) == 6
