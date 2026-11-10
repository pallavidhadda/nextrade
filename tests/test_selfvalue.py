from datetime import date, datetime, timezone
from decimal import Decimal

from indiafacts.models import Entity, FactSet, Status
from indiafacts.scoring import _extract, load_score_config
from indiafacts.selfvalue import self_valuation_facts
from indiafacts.shareholding import parse_shp, shareholding_facts
from tests.factories import fact
from tests.test_shareholding import xml

D = date(2026, 10, 24)


def base():
    return [
        fact(metric="last_close", value="100", period_type="point", period_end=D, source="computed:price", unit="INR"),
        fact(metric="shares_outstanding", value="1000", period_type="point", period_end=date(2026, 9, 30), source="nse_shp", unit="shares"),
        fact(metric="eps_diluted_ttm", value="5", period_type="TTM", period_end=date(2026, 6, 30), source="computed", unit="INR_per_share"),
        fact(metric="equity_owners", value="50000", period_type="point", period_end=date(2026, 6, 30), source="nse_xbrl"),
    ]


def by(out, m):
    return {f.metric: f for f in out}[m]


def test_market_cap_pe_pb_use_scoring_metric_names_with_provenance():
    out = self_valuation_facts(base())
    mc, pe, pb = by(out, "market_cap"), by(out, "pe_ttm"), by(out, "pb")
    assert mc.value == Decimal(100000) and pe.value == Decimal(20) and pb.value == Decimal(2)
    assert mc.source == pe.source == pb.source == "computed:selfvalue"
    assert mc.related_fact_ids and pe.related_fact_ids and pb.related_fact_ids
    assert "x" in mc.reason and "/" in pe.reason and "/" in pb.reason
    assert {"pe_ttm", "pb"} <= {m.id for m in load_score_config(strict=False).metrics}


def test_missing_inputs_give_no_fact_and_nothing_is_invented():
    assert self_valuation_facts([f for f in base() if f.metric != "shares_outstanding"]) == []
    out = self_valuation_facts([f for f in base() if f.metric != "equity_owners"])
    assert not [f for f in out if f.metric == "pb"]


def test_pe_falls_back_to_ttm_net_profit_per_share():
    fs = [f for f in base() if f.metric != "eps_diluted_ttm"] + [
        fact(metric="net_income_ttm", value="4000", period_type="TTM", unit="INR", source="computed")]
    out = self_valuation_facts(fs)
    assert by(out, "eps_ttm").value == Decimal(4) and by(out, "pe_ttm").value == Decimal(25)


def test_negative_earnings_state_pe_unavailable():
    fs = [f for f in base() if f.metric != "eps_diluted_ttm"] + [
        fact(metric="eps_diluted_ttm", value="-2", period_type="TTM", unit="INR_per_share", source="computed")]
    pe = by(self_valuation_facts(fs), "pe_ttm")
    assert pe.status == Status.unavailable and pe.value is None and pe.reason


def test_official_shares_preferred_over_yahoo_and_yahoo_is_fallback():
    y = fact(metric="shares_outstanding", value="2000", period_type="point", period_end=D, source="yahoo", unit="shares")
    out = self_valuation_facts(base() + [y])
    assert by(out, "market_cap").value == Decimal(100000)
    assert by(out, "shares_outstanding_source_check").status == Status.conflict            # 1000 vs 2000
    only_yahoo = self_valuation_facts([f for f in base() if f.metric != "shares_outstanding"] + [y])
    assert by(only_yahoo, "market_cap").value == Decimal(200000)


def test_vendor_value_that_differs_over_5pct_is_flagged_and_both_remain():
    ypb = fact(metric="pb", value="3", period_type="point", period_end=D, source="yahoo", unit="ratio")
    out = self_valuation_facts(base() + [ypb])
    chk = by(out, "pb_source_check")
    assert chk.status == Status.conflict and len(chk.related_fact_ids) == 2 and "differ" in chk.reason
    assert ypb.status == Status.ok and by(out, "pb").status == Status.ok


def test_agreeing_vendor_value_passes_check():
    ype = fact(metric="pe_ttm", value="20.5", period_type="point", period_end=D, source="yahoo", unit="ratio")
    assert by(self_valuation_facts(base() + [ype]), "pe_ttm_source_check").status == Status.ok


def test_scoring_prefers_computed_over_yahoo_snapshot():
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    ype = fact(metric="pe_ttm", value="40", period_type="point", period_end=date(2026, 10, 25), source="yahoo", unit="ratio")
    fs = FactSet(entity=Entity.from_ticker("RELIANCE.NS"), facts=self_valuation_facts(base()) + [ype], retrieved_at=now)
    out, _ = _extract(fs, load_score_config(strict=False), D, now)
    assert out["pe_ttm"][0] == 20.0


def test_shareholding_parses_total_share_count_into_a_fact():
    raw = xml().decode().replace("</xbrli:xbrl>",
        '<in-bse-shp:NumberOfFullyPaidUpEquityShares contextRef="t">1234567</in-bse-shp:NumberOfFullyPaidUpEquityShares></xbrli:xbrl>').encode()
    sh = parse_shp(raw)
    assert sh.total_shares == 1234567
    f = {x.metric: x for x in shareholding_facts("ABC", [sh])}["shares_outstanding"]
    assert f.value == Decimal(1234567) and f.source == "nse_shp"


def test_pipeline_computes_market_cap_from_yahoo_share_count_when_overview_lacks_it():
    from indiafacts.pipeline import build_factset
    from tests.fakes import FakeClient
    from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
    from tests.test_price_integration import long_pair

    info = {k: v for k, v in INFO.items() if k not in ("marketCap", "priceToBook", "trailingPE", "trailingEps")}
    info["sharesOutstanding"] = 13_000_000_000
    fs = build_factset("RELIANCE.NS", client=FakeClient(QUARTERLY, info), prices=True, price_client=long_pair(), sleep=lambda s: None)
    mc = [f for f in fs.facts if f.metric == "market_cap" and f.source == "computed:selfvalue"]
    assert mc and mc[0].status == Status.ok and len(mc[0].related_fact_ids) == 2
    assert mc[0].value == Decimal(13_000_000_000) * [f for f in fs.facts if f.metric == "last_close"][0].value
