import json

from tests.test_explain_cli import run


def test_json_flag_writes_summary(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    assert code == 0
    d = json.loads(out.read_text())
    assert d["ticker"] == "RELIANCE.NS" and d["name"]
    assert "Not financial" in d["disclaimer"]
    assert d["score"]["rank"] and d["score"]["n"] >= 2 and 0 <= d["score"]["overall"] <= 100
    assert ".txt" not in (d["score"]["pool"] or "") and ".csv" not in (d["score"]["pool"] or "")
    assert len(d["checklist"]) == 9 and {"label", "result", "display"} <= set(d["checklist"][0])
    assert d["gaps"] and all("metric" in g and "reason" in g for g in d["gaps"])
    assert d["explanation"]["summary"] and d["explanation"]["claims"]
    assert isinstance(d["notices"], list) and "factors" in d["score"]
    assert {"partial", "evidence_note"} <= set(d["debate"]["stance"])
    assert not any(t["text"].startswith("Needs data") or "Check failed" in t["text"] for t in d["explanation"]["triggers"])
    assert not any(p["text"].startswith("Check ") for p in d["debate"]["bull"] + d["debate"]["bear"])


def test_json_without_score_has_null_score(tmp_path, capsys):
    out = tmp_path / "s.json"
    from indiafacts.cli import main
    from tests.fakes import FakeClient
    from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
    from tests.test_htmlreport import SYMS, prices_for
    code = main(["RELIANCE.NS", "--no-tej", "--no-remember", "--json", str(out)], client=FakeClient(stmt=QUARTERLY, info=INFO),
                sleep=lambda s: None, price_client=prices_for(SYMS))
    assert code == 0
    d = json.loads(out.read_text())
    assert d["score"] is None and d["checklist"] == []


def test_summary_carries_prompt_for_browser_side_llm(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    d = json.loads(out.read_text())
    assert d["llm"]["user"].startswith("DIGEST:") and "JSON" in d["llm"]["system"]
    assert d["llm"]["max_tokens"] == 700 and d["llm"]["ids"] and d["llm"]["ids"][0].startswith("F")
    assert "KEY" not in json.dumps(d).upper().replace("KEY_FACTS", "")


def test_pool_size_limits_the_comparison_pool(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--pool-size", "2", "--json", str(out))
    d = json.loads(out.read_text())
    assert code == 0 and d["score"]["n"] <= 3


def test_valuation_block_in_text_digest_and_json(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, text, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    d = json.loads(out.read_text())
    assert d["valuation"]["method"] == "reverse_dcf_earnings" and len(d["valuation"]["items"]) == 6
    assert "WHAT THE PRICE IMPLIES" in text and "not a forecast" in text
    assert "VALUATION price implies earnings growth" in d["llm"]["digest"]
    lowered = (text + d["llm"]["digest"]).lower()
    assert "undervalued" not in lowered and "overvalued" not in lowered and "fair value of" not in lowered


def test_no_data_at_all_is_a_clear_error_not_an_empty_digest(tmp_path, capsys, monkeypatch):
    from indiafacts import cli
    from indiafacts.models import Entity, FactSet
    from datetime import datetime, timezone

    empty = FactSet(entity=Entity.from_ticker("TCS.NS"), facts=[], retrieved_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
                    notices=["TejHQ data unavailable: ProxyError"])
    monkeypatch.setattr(cli, "build_factset", lambda *a, **k: empty)
    code = cli.main(["TCS.NS", "--score", "--no-remember", "--digest"])
    out = capsys.readouterr()
    assert code == 5
    assert "could not fetch any data" in out.err and "network" in out.err.lower()
    assert "DIGEST" not in out.out


def test_news_debate_and_stance_flow_through_digest_text_and_json(tmp_path, capsys):
    from datetime import datetime, timezone

    from indiafacts.cli import main
    from tests.fakes import FakeClient
    from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
    from tests.test_explain_cli import INFO2
    from tests.test_htmlreport import NSE_CSV, SYMS, prices_for

    class N:
        def news(self, symbol):
            return [{"title": "Reliance wins record order; shares surge", "publisher": "Wire", "providerPublishTime": int(datetime.now(timezone.utc).timestamp()) - 3600}]

    c = tmp_path / "ind.csv"
    c.write_text(NSE_CSV, encoding="utf-8")
    out = tmp_path / "s.json"
    code = main(["RELIANCE.NS", "--score", "--universe", str(c), "--no-tej", "--no-remember", "--explain", "--news", "--json", str(out)],
                client=FakeClient(stmt=QUARTERLY, info=INFO2), sleep=lambda s: None, price_client=prices_for(SYMS), news_client=N())
    text = capsys.readouterr().out
    d = json.loads(out.read_text())
    assert code == 0 and "BULL CASE VERSUS BEAR CASE" in text and "EDUCATIONAL RATING:" in text and "RECENT HEADLINES" in text
    assert d["news"][0]["sentiment_hint"] == "positive" and d["debate"]["stance"]["label"]
    digest = d["llm"]["digest"]
    assert "RATING educational:" in digest and "NEWS " in digest and "[[" not in digest and "(see F" in digest
    assert all("evidence" in p for p in d["debate"]["bull"] + d["debate"]["bear"])


def test_news_is_off_by_default(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, text, _ = run(tmp_path, capsys, "--json", str(out))
    assert "RECENT HEADLINES" not in text and json.loads(out.read_text())["news"] == []


def test_levels_and_risk_lenses_flow_through_text_digest_and_json(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, text, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    d = json.loads(out.read_text())
    assert code == 0 and "REFERENCE LEVELS (NOT TARGETS) AND RISK LENSES" in text and "risk lenses" in text
    assert d["levels"]["last_close"] and {l["name"] for l in d["risk_panel"]["lenses"]} == {"aggressive", "neutral", "conservative"}
    assert "LEVELS last close" in d["llm"]["digest"] and "RISK neutral lens" in d["llm"]["digest"]
    assert "not predictions or price targets" in d["llm"]["digest"]


def test_html_report_includes_debate_levels_and_escapes_headlines(tmp_path, capsys):
    from datetime import datetime, timezone

    from indiafacts.cli import main
    from tests.fakes import FakeClient
    from tests.fixtures.reliance_quarterly import QUARTERLY
    from tests.test_explain_cli import INFO2
    from tests.test_htmlreport import NSE_CSV, SYMS, prices_for

    class N:
        def news(self, symbol):
            return [{"title": "Reliance <script>alert(1)</script> wins deal", "publisher": "Wire", "providerPublishTime": int(datetime.now(timezone.utc).timestamp()) - 60}]

    c = tmp_path / "ind.csv"
    c.write_text(NSE_CSV, encoding="utf-8")
    page = tmp_path / "r.html"
    main(["RELIANCE.NS", "--score", "--universe", str(c), "--no-tej", "--no-remember", "--news", "--html", str(page)],
         client=FakeClient(stmt=QUARTERLY, info=INFO2), sleep=lambda s: None, price_client=prices_for(SYMS), news_client=N())
    html = page.read_text(encoding="utf-8")
    assert "Bull case versus bear case" in html and "Educational rating:" in html and "Reference levels (not targets) and risk lenses" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)" not in html


def test_evidence_index_lines_have_no_unresolved_placeholders(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, text, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    assert "[[" not in text and "]]" not in text
    d = json.loads(out.read_text())
    assert "[[" not in d["llm"]["digest"]
