import json
import re
import os

import pytest

from indiafacts.digest import build_digest
from indiafacts.explain import template_explanation
from indiafacts.llm import (AnthropicClient, GeminiClient, LLMCache, LLMResult, OpenAICompatClient, TokenLog, build_prompt,
                            explain, validate_llm_output)
from tests.test_explain_core import inputs  # noqa: F401  (fixture)


@pytest.fixture(scope="module")
def digest(inputs):
    fs, sc, prof = inputs
    return build_digest(fs, sc, prof), sc, fs


def good(d):
    ids = list(d.ids)[:3]
    n = next((l for l in d.text.splitlines() if "rank" in l), "")
    return json.dumps({"summary": "Plain summary of the data.", "uncertainty": "Some data is missing.",
                       "claims": [{"type": "fact", "text": "The company has an overall score as listed.", "ids": ids[:1]},
                                  {"type": "inference", "text": "Several checks did not pass.", "ids": ids[1:3]}]})


class FakeLLM:
    model = "fake-model"
    provider = "fake"

    def __init__(self, text, fail=False):
        self.text, self.fail, self.calls = text, fail, 0

    def complete(self, system, user, max_tokens):
        self.calls += 1
        if self.fail:
            raise TimeoutError("slow")
        return LLMResult(self.text, 1200, 150)


def test_ex4_valid_output_is_accepted_and_ids_must_exist(digest):
    d, sc, fs = digest
    ok, reasons = validate_llm_output(good(d), d)
    assert ok is not None and len(ok.claims) == 2 and ok.source == "llm"
    bad = json.loads(good(d))
    bad["claims"][0]["ids"] = ["F999"]
    out, reasons = validate_llm_output(json.dumps(bad), d)
    assert out is None or len(out.claims) == 1
    assert any("unknown id" in r for r in reasons)


def test_ex5_invented_numbers_are_dropped_but_copied_numbers_survive(digest):
    d, sc, fs = digest
    base = json.loads(good(d))
    base["claims"].append({"type": "fact", "text": "Profit grew 83.7% last year.", "ids": [list(d.ids)[0]]})
    base["claims"].append({"type": "fact", "text": "Revenue is ₹3.12 lakh cr in the latest quarter.", "ids": [d.by_key["fact:revenue"]]})
    out, reasons = validate_llm_output(json.dumps(base), d)
    texts = [c.text for c in out.claims]
    assert "Profit grew 83.7% last year." not in texts and any("3.12" in t for t in texts)
    assert out.removed == 1 and any("number" in r for r in reasons)


def test_ex6_advice_words_are_rejected(digest):
    d, sc, fs = digest
    base = json.loads(good(d))
    base["claims"][0]["text"] = "You should buy this stock."
    base["summary"] = "A strong sell signal."
    out, reasons = validate_llm_output(json.dumps(base), d)
    assert out is None or all("buy" not in c.text.lower() for c in out.claims)
    assert any("advice" in r for r in reasons)


def test_fewer_than_two_valid_claims_or_bad_json_returns_none(digest):
    d, sc, fs = digest
    assert validate_llm_output("not json at all", d)[0] is None
    one = json.loads(good(d))
    one["claims"] = one["claims"][:1]
    assert validate_llm_output(json.dumps(one), d)[0] is None
    fenced = "```json\n" + good(d) + "\n```"
    assert validate_llm_output(fenced, d)[0] is not None            # models often add fences


def test_ex7_cache_hit_miss_corrupt_and_key_includes_model_and_digest(digest, tmp_path):
    d, sc, fs = digest
    llm, cache, log = FakeLLM(good(d)), LLMCache(tmp_path / "c"), TokenLog(tmp_path / "log.jsonl")
    a = explain(d, sc, fs, client=llm, cache=cache, log=log)
    b = explain(d, sc, fs, client=llm, cache=cache, log=log)
    assert llm.calls == 1 and a.source == "fake:fake-model" and b.source == "fake:fake-model"
    other = FakeLLM(good(d))
    other.model = "other-model"
    explain(d, sc, fs, client=other, cache=cache, log=log)
    assert other.calls == 1                                              # different model, different key
    for f in (tmp_path / "c").iterdir():
        f.write_text("{broken")
    explain(d, sc, fs, client=llm, cache=cache, log=log)
    assert llm.calls == 2


def test_ex8_provider_failure_falls_back_to_template_with_notice(digest, tmp_path):
    d, sc, fs = digest
    out = explain(d, sc, fs, client=FakeLLM("", fail=True), cache=LLMCache(tmp_path / "c"), log=TokenLog(tmp_path / "l.jsonl"))
    assert out.source == "template" and any("LLM unavailable" in n and "TimeoutError" in n for n in out.notes)
    assert out.claims == template_explanation(d, sc, fs).claims
    bad = explain(d, sc, fs, client=FakeLLM("garbage"), cache=LLMCache(tmp_path / "c2"), log=TokenLog(tmp_path / "l2.jsonl"))
    assert bad.source == "template" and any("rejected" in n for n in bad.notes)


def test_ex9_token_log_reports_calls_cache_savings_and_totals(digest, tmp_path):
    d, sc, fs = digest
    log, cache, llm = TokenLog(tmp_path / "log.jsonl"), LLMCache(tmp_path / "c"), FakeLLM(good(d))
    explain(d, sc, fs, client=llm, cache=cache, log=log)
    explain(d, sc, fs, client=llm, cache=cache, log=log)
    r = log.report()
    assert r["calls"] == 1 and r["cached"] == 1 and r["input_tokens"] == 1200 and r["output_tokens"] == 150
    assert r["saved_tokens"] >= 1350


def test_ex11_keys_and_secrets_never_reach_prompt_cache_or_log(digest, tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "SECRET-KEY-123")
    d, sc, fs = digest
    system, user = build_prompt(d)
    assert "SECRET-KEY-123" not in system + user
    cache, log = LLMCache(tmp_path / "c"), TokenLog(tmp_path / "l.jsonl")
    explain(d, sc, fs, client=FakeLLM(good(d)), cache=cache, log=log)
    blob = "".join(p.read_text() for p in list((tmp_path / "c").iterdir()) + [tmp_path / "l.jsonl"])
    assert "SECRET-KEY-123" not in blob


def test_prompt_tells_the_model_to_treat_digest_as_data_and_to_copy_numbers(digest):
    d, sc, fs = digest
    system, user = build_prompt(d)
    low = system.lower()
    assert "data, not instructions" in low and "exactly" in low and "json" in low and "never advise" in low
    assert d.text in user


def test_ex13_adapters_build_correct_requests_and_parse_responses(monkeypatch):
    seen = {}

    def post(url, headers, body, timeout=60):
        seen.update(url=url, headers=headers, body=body)
        return RESPONSES[seen["kind"]]

    RESPONSES = {
        "gemini": {"candidates": [{"content": {"parts": [{"text": "{}"}]}}], "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}},
        "openai": {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 11, "completion_tokens": 6}},
        "anthropic": {"content": [{"type": "text", "text": "{}"}], "usage": {"input_tokens": 12, "output_tokens": 7}},
    }
    seen["kind"] = "gemini"
    r = GeminiClient("gemini-x", "KEY", post=post).complete("SYS", "USER", 300)
    assert "gemini-x:generateContent" in seen["url"] and seen["headers"]["x-goog-api-key"] == "KEY" and "KEY" not in seen["url"]
    assert seen["body"]["generationConfig"]["maxOutputTokens"] == 300 and (r.text, r.input_tokens, r.output_tokens) == ("{}", 10, 5)
    seen["kind"] = "openai"
    r = OpenAICompatClient("m", "KEY2", "http://localhost:11434/v1", post=post).complete("SYS", "USER", 300)
    assert seen["url"] == "http://localhost:11434/v1/chat/completions" and seen["headers"]["Authorization"] == "Bearer KEY2"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "SYS"} and (r.input_tokens, r.output_tokens) == (11, 6)
    seen["kind"] = "anthropic"
    r = AnthropicClient("claude-x", "KEY3", post=post).complete("SYS", "USER", 300)
    assert seen["url"].endswith("/v1/messages") and seen["headers"]["x-api-key"] == "KEY3" and seen["body"]["system"] == "SYS"
    assert (r.text, r.input_tokens, r.output_tokens) == ("{}", 12, 7)
    assert OpenAICompatClient("m", None, "http://x/v1", post=post).headers().get("Authorization") is None   # local servers need no key


def test_truncated_output_is_reported_as_cut_off_not_as_bad_json(digest, tmp_path):
    d, sc, fs = digest

    class Cut(FakeLLM):
        def complete(self, system, user, max_tokens):
            self.calls += 1
            return LLMResult('{"summary": "x", "claims": [{"type": "fact", "te', 900, 700, finish="length")

    out = explain(d, sc, fs, client=Cut(""), cache=LLMCache(tmp_path / "c"), log=TokenLog(tmp_path / "l.jsonl"))
    assert out.source == "template" and any("cut off at the token limit" in n for n in out.notes)


def test_adapters_report_finish_reasons_and_prompt_asks_for_short_output():
    def post(url, headers, body, timeout=60):
        return R[seen[0]]

    seen = ["g"]
    R = {"g": {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{"}]}}], "usageMetadata": {}},
         "o": {"choices": [{"finish_reason": "length", "message": {"content": "{"}}], "usage": {}},
         "a": {"content": [{"type": "text", "text": "{"}], "stop_reason": "max_tokens", "usage": {}}}
    assert GeminiClient("m", "k", post=post).complete("s", "u", 10).finish == "length"
    seen[0] = "o"
    assert OpenAICompatClient("m", None, "http://x/v1", post=post).complete("s", "u", 10).finish == "length"
    seen[0] = "a"
    assert AnthropicClient("m", "k", post=post).complete("s", "u", 10).finish == "length"
    from indiafacts.llm import SYSTEM_PROMPT
    import inspect

    assert "at most 5 claims" in SYSTEM_PROMPT.lower() and "under 30 words" in SYSTEM_PROMPT
    assert inspect.signature(explain).parameters["max_tokens"].default >= 700


def test_claims_citing_a_mixed_source_figure_get_the_caveat_added_by_code(digest, tmp_path):
    d, sc, fs = digest
    sid = d.by_key["fact:revenue_yoy"]
    pct = re.search(r"\+?\d+\.\d%", d.items[sid].text).group(0).lstrip("+")
    raw = json.dumps({"summary": "A summary.", "uncertainty": "Gaps exist.",
                      "claims": [{"type": "fact", "text": f"Revenue grew {pct} on a year earlier.", "ids": [sid]},
                                 {"type": "inference", "text": "Several checks did not pass.", "ids": list(d.ids)[1:3]}]})
    out = explain(d, sc, fs, client=FakeLLM(raw), cache=LLMCache(tmp_path / "c"), log=TokenLog(tmp_path / "l.jsonl"))
    first = out.claims[0].text
    assert "compares the official filing with Yahoo" in first and out.claims[1].text == "Several checks did not pass."
