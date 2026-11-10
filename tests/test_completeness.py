import json
from datetime import date, datetime, timezone

from indiafacts.completeness import completeness, load_completeness_params
from indiafacts.fundamentals import LENDER_REASON
from indiafacts.models import Entity, FactSet
from tests.factories import fact
from tests.test_explain_cli import run

AS_OF = date(2026, 10, 26)
NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def fsof(facts, ticker="ABC.NS"):
    return FactSet(entity=Entity.from_ticker(ticker), facts=facts, retrieved_at=NOW)


def pt(metric, end=AS_OF, **kw):
    return fact(metric=metric, value=kw.pop("value", "1"), period_type="point", period_end=end, **kw)


def pillar_facts(key, end=AS_OF, source="yahoo"):
    p = load_completeness_params()["pillars"][key]
    return [pt(e.split("|")[0], end, source=source) for e in p["expected"]]


def full(end=AS_OF):
    return [f for k in ("price_history", "valuation", "balance_sheet", "ownership") for f in pillar_facts(k, end)] + \
        [pt(m, end) for m in ("revenue", "net_income", "eps_diluted", "ebitda", "revenue_yoy", "net_income_yoy", "net_margin_q",
                              "net_income_ttm", "eps_diluted_ttm", "fy_revenue", "fy_net_income", "roe")] + \
        [pt(m, end, source="nse_xbrl") for m in ("revenue", "net_income", "profit_before_tax", "eps_diluted")]


def test_full_data_is_high_with_every_pillar_covered():
    c = completeness(fsof(full()), AS_OF)
    assert c["level"] == "High" and c["overall_coverage_pct"] == 100.0
    assert all(v["coverage_pct"] == 100.0 and v["stale_n"] == 0 for v in c["pillars"].values())
    assert set(c["pillars"]) == {"price_history", "fundamentals", "valuation", "balance_sheet", "ownership", "filings"}


def test_missing_valuation_makes_it_insufficient_and_lists_what_is_missing():
    facts = [f for f in full() if f.metric not in ("pe_ttm", "pb", "eps_ttm", "market_cap", "shares_outstanding")]
    c = completeness(fsof(facts), AS_OF)
    v = c["pillars"]["valuation"]
    assert c["level"] == "Insufficient" and "valuation" in c["reason"]
    assert v["present_ok"] == 1 and v["expected_n"] == 6 and set(v["missing"]) >= {"pe_ttm", "pb", "market_cap"}


def test_issues_counted_by_status_and_lender_not_applicable_excluded():
    facts = full() + [pt("roa", status="unavailable", value=None, reason="not provided"),
                      pt("pe_ttm_source_check", status="conflict", reason="differ"),
                      pt("debt_to_equity", status="unavailable", value=None, reason=LENDER_REASON, source="computed")]
    c = completeness(fsof(facts), AS_OF)
    assert c["issues_total"] == 2 and c["issues_by_status"] == {"unavailable": 1, "conflict": 1}
    assert c["pillars"]["fundamentals"]["issues"] == {"unavailable": 1} and c["pillars"]["valuation"]["issues"] == {"conflict": 1}


def test_lender_only_metric_is_not_expected():
    facts = [f for f in full() if f.metric != "debt_to_equity"] + [
        pt("debt_to_equity", status="unavailable", value=None, reason=LENDER_REASON, source="computed")]
    b = completeness(fsof(facts), AS_OF)["pillars"]["balance_sheet"]
    assert "debt_to_equity" in b["not_applicable"] and "debt_to_equity" not in b["expected"] and b["coverage_pct"] == 100.0


def test_stale_prices_and_quarter_are_counted_not_covered():
    old = date(2026, 10, 20)                                          # 6 days: over the 4-day price limit
    facts = [f for f in full() if f.metric != "last_close"] + [pt("last_close", old)]
    c = completeness(fsof(facts), AS_OF)
    p = c["pillars"]["price_history"]
    assert p["stale_n"] == 1 and p["stale"][0]["metric"] == "last_close" and p["stale"][0]["age_days"] == 6
    assert p["present_ok"] == 12 and p["fresh_ok"] == 11 and c["stale_total"] == 1
    weekend = completeness(fsof([f for f in full() if f.metric != "last_close"] + [pt("last_close", date(2026, 10, 23))]), date(2026, 10, 26))
    assert weekend["pillars"]["price_history"]["stale_n"] == 0       # Friday close on a Monday is fresh
    q = [f for f in full() if f.metric != "revenue"] + [fact(metric="revenue", period_end=date(2026, 3, 31), period_type="Q")]
    assert any(s["metric"] == "revenue" and s["max_age_days"] == 150 for s in completeness(fsof(q), AS_OF)["pillars"]["fundamentals"]["stale"])
    sh = [f for f in full() if f.metric != "sh_promoter"] + [pt("sh_promoter", date(2026, 6, 30), source="nse_shp")]
    assert completeness(fsof(sh), AS_OF)["pillars"]["ownership"]["stale_n"] == 0       # 118 days is inside 120
    sh = [f for f in full() if f.metric != "sh_promoter"] + [pt("sh_promoter", date(2026, 6, 1), source="nse_shp")]
    assert completeness(fsof(sh), AS_OF)["pillars"]["ownership"]["stale_n"] == 1


def test_frozen_facts_are_not_mutated():
    facts = full()
    before = [f.model_dump() for f in facts]
    completeness(fsof(facts), date(2027, 6, 1))
    assert [f.model_dump() for f in facts] == before


def test_conflict_lists_both_values_and_sources():
    a = pt("pb", value="2", source="computed:selfvalue")
    b = pt("pb", value="3", source="yahoo")
    chk = pt("pb_source_check", status="conflict", reason="computed:selfvalue 2 vs yahoo 3: sources differ by 50.0%",
             source="computed", related_fact_ids=[a.fact_id, b.fact_id])
    c = completeness(fsof(full() + [a, b, chk]), AS_OF)
    assert c["conflicts"] == [{"metric": "pb", "period": str(AS_OF), "chosen": {"value": "2", "source": "computed:selfvalue", "unit": "INR"},
                               "alternative": {"value": "3", "source": "yahoo", "unit": "INR"},
                               "reason": chk.reason, "fact_id": chk.fact_id}]


def test_news_pillar_only_when_news_was_fetched():
    assert "news" not in completeness(fsof(full()), AS_OF)["pillars"]
    assert completeness(fsof(full()), AS_OF, news=[])["pillars"]["news"]["coverage_pct"] == 0.0
    assert completeness(fsof(full()), AS_OF, news=[object()])["pillars"]["news"]["coverage_pct"] == 100.0


def test_json_summary_carries_completeness(tmp_path, capsys):
    out = tmp_path / "s.json"
    code, _, _ = run(tmp_path, capsys, "--explain", "--json", str(out))
    d = json.loads(out.read_text())
    assert code == 0 and d["completeness"]["level"] in ("High", "Medium", "Low", "Insufficient")
    assert {"pillars", "issues_total", "conflicts", "stale_total"} <= set(d["completeness"])
