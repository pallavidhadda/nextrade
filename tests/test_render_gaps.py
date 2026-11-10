"""Render-side gaps: published-file addresses from the snapshot base, gaps filled by another source or name, EV after Market Lens."""
from datetime import date, datetime, timezone
from decimal import Decimal

from indiafacts import published
from indiafacts.completeness import attention_items
from indiafacts.models import Entity, Fact, FactSet, PeriodType, Status
from indiafacts.pipeline import _refresh_market_value

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
KEY = "RELIANCE.NS"


def fact(metric, value, source, end, status=Status.ok, ptype=PeriodType.point, unit="ratio", reason=""):
    return Fact.make(entity_key=KEY, metric=metric, value=None if value is None else Decimal(str(value)), unit=unit,
                     period_end=end, period_type=ptype, source=source, retrieved_at=NOW, status=status, reason=reason)


def gap(metric, end=date(2026, 11, 10), ptype=PeriodType.point):
    return fact(metric, None, "yahoo", end, status=Status.gap, ptype=ptype, reason="not provided by Yahoo")


# ---- published.url -----------------------------------------------------------------------------------------

def test_url_derived_from_snapshot_base(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_SNAPSHOT_BASE", "https://example.org/snap/")
    monkeypatch.delenv("INDIAFACTS_POOL_METRICS_URL", raising=False)
    assert published.url("INDIAFACTS_POOL_METRICS_URL", "pool_metrics.json") == "https://example.org/snap/pool_metrics.json"
    assert published.url("INDIAFACTS_NSE_COPY_BASE", "nse/") == "https://example.org/snap/nse/"


def test_explicit_variable_wins_and_empty_switches_off(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_SNAPSHOT_BASE", "https://example.org/snap")
    monkeypatch.setenv("INDIAFACTS_POOL_METRICS_URL", "file:///tmp/p.json")
    assert published.url("INDIAFACTS_POOL_METRICS_URL", "pool_metrics.json") == "file:///tmp/p.json"
    monkeypatch.setenv("INDIAFACTS_POOL_METRICS_URL", "")
    assert published.url("INDIAFACTS_POOL_METRICS_URL", "pool_metrics.json") == ""


def test_no_snapshot_base_means_nothing(monkeypatch):
    monkeypatch.delenv("INDIAFACTS_SNAPSHOT_BASE", raising=False)
    monkeypatch.delenv("INDIAFACTS_MARKETLENS_URL", raising=False)
    assert published.url("INDIAFACTS_MARKETLENS_URL", "marketlens.json") == ""


# ---- attention_items -----------------------------------------------------------------------------------------

def test_point_gap_filled_by_other_source_a_day_apart():
    items = attention_items([gap("pe_ttm"), fact("pe_ttm", 18.68, "nse_marketlens", date(2026, 11, 9))])
    assert items == []


def test_point_gap_kept_when_other_figure_is_old():
    g = gap("pe_ttm")
    assert attention_items([g, fact("pe_ttm", 18.68, "nse_marketlens", date(2026, 9, 1))]) == [g]


def test_alias_fills_vendor_gap():
    facts = [gap("insider_holding"), gap("institutional_holding"), gap("roe"), gap("payout_ratio"),
             fact("sh_promoter", 0.5, "nse_shp", date(2026, 9, 30)), fact("sh_domestic_inst", 0.2, "nse_shp", date(2026, 9, 30)),
             fact("fy_roe", 0.09, "computed:fundamentals", date(2026, 3, 31))]
    assert [f.metric for f in attention_items(facts)] == ["payout_ratio"]


def test_quarter_gap_not_filled_by_other_quarter():
    g = gap("revenue", end=date(2025, 9, 30), ptype=PeriodType.Q)
    other = fact("revenue", 1, "nse_filing", date(2025, 12, 31), ptype=PeriodType.Q, unit="INR")
    assert attention_items([g, other]) == [g]


def test_conflict_never_hidden():
    c = fact("pe_ttm", 20, "computed:selfvalue", date(2026, 11, 10), status=Status.conflict, reason="sources disagree")
    assert attention_items([c, fact("pe_ttm", 18.68, "nse_marketlens", date(2026, 11, 9))]) == [c]


# ---- EV after Market Lens -----------------------------------------------------------------------------------

def _fs(facts):
    return FactSet(entity=Entity.from_ticker(KEY).model_copy(update={"sector": "Energy", "industry": "Oil & Gas Refining & Marketing"}),
                   facts=facts, retrieved_at=NOW)


def _annual():
    fy = date(2026, 3, 31)
    return [fact(m, v, "yahoo", fy, ptype=PeriodType.FY, unit="INR") for m, v in
            (("fy_total_debt", 300), ("fy_cash", 100), ("fy_ebitda", 200), ("fy_free_cash_flow", 50))]


def test_ev_recomputed_when_market_value_arrives_later():
    fy = date(2026, 3, 31)
    stale = [fact(m, None, "computed:fundamentals", fy, status=Status.unavailable, reason="market value unavailable")
             for m in ("ev", "ev_ebitda", "fy_fcf_yield")]
    facts = _annual() + stale + [fact("market_cap", 1000, "nse_marketlens", date(2026, 11, 9), unit="INR")]
    out = {f.metric: f for f in _refresh_market_value(_fs(facts), facts) if f.metric in ("ev", "ev_ebitda", "fy_fcf_yield")}
    assert out["ev"].status == Status.ok and float(out["ev"].value) == 1200
    assert float(out["ev_ebitda"].value) == 6
    assert float(out["fy_fcf_yield"].value) == 0.05
    assert len(_refresh_market_value(_fs(facts), facts)) == len(facts)          # replaced, not duplicated


def test_ev_left_alone_without_market_value():
    fy = date(2026, 3, 31)
    facts = _annual() + [fact("ev", None, "computed:fundamentals", fy, status=Status.unavailable, reason="market value unavailable")]
    assert _refresh_market_value(_fs(facts), facts) == facts
