import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from indiafacts import marketlens, poolstore
from indiafacts.models import Entity, Fact, FactSet, PeriodType, Status
from indiafacts.profile import default_profile, weights_for
from indiafacts.scoring import (extract_facts, factsets_from_sources, load_score_config, load_source_policy,
                                score_universe)

FIX = Path(__file__).parent / "fixtures" / "marketlens_petroleum_products.json"
TODAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
ROWS = {r["id"]: r for r in json.loads(FIX.read_text())["data"]}        # 12 companies, sector "Petroleum Products"
SYMS = sorted(ROWS)
TARGET = "RELIANCE.NS"
POLICY = load_source_policy()
CFG = load_score_config(strict=False)


def mkfs(ticker, metrics, sector=None, source="yahoo"):
    ent = Entity.from_ticker(ticker).model_copy(update={"sector": sector})
    facts = [Fact.make(entity_key=ticker, metric=m, value=Decimal(str(v)), unit="x", period_end=TODAY, period_type=PeriodType.point,
                       source=source, retrieved_at=NOW, status=Status.ok) for m, v in metrics.items()]
    return FactSet(entity=ent, facts=facts, retrieved_at=NOW)


def store_of(per_ticker, nifty=None):
    m = {t: {k: {"value": v, "source": "yahoo", "as_of": TODAY.isoformat()} for k, v in d.items()} for t, d in per_ticker.items()}
    if nifty is not None:
        m["^NSEI"] = {"return_1y": {"value": nifty, "source": "yahoo", "as_of": TODAY.isoformat()}}
    return {"meta": {"generated_at": NOW.isoformat(), "commit": "t", "policy_hash": "x", "n": len(per_ticker)}, "metrics": m}


def build(store, target_metrics, ml_rows=ROWS, symbols=SYMS):
    tfs = mkfs(TARGET, target_metrics)
    return factsets_from_sources([s + ".NS" for s in symbols], tfs, store, ml_rows, POLICY, CFG, TODAY, NOW, nifty_1y=0.05, store_at=NOW)


def sources_of(fsets, metric):
    return {f.source for fs in fsets.values() for f in fs.facts if f.metric == metric}


def test_one_source_per_metric_and_switch_to_market_lens_when_store_thin():
    full_pe = {t + ".NS": {"pe_ttm": ROWS[t]["peRatio"]} for t in SYMS}
    thin_pb = {TARGET: {"pb": 1.64}, "IOC.NS": {"pb": 1.08}}                      # 2 of 12 with a store value
    store = store_of({t: {**full_pe[t], **thin_pb.get(t, {})} for t in full_pe})
    fsets, sources = build(store, {"pe_ttm": 18.68, "pb": 1.64})
    assert sources["pe_ttm"] == {"source": "pool_store", "covered": 12, "of": 12}
    assert sources["pb"]["source"] == "nse_marketlens" and sources["pb"]["of"] == 12
    assert sources["pb"]["covered"] == 11                                        # CASTROLIND's pbRatio is a 0 placeholder
    assert sources_of(fsets, "pe_ttm") == {"pool_store:yahoo"}
    assert sources_of(fsets, "pb") == {"nse_marketlens"}                         # never a mix, the target included
    tgt_pb = next(f for f in fsets[TARGET].facts if f.metric == "pb")
    assert tgt_pb.source == "nse_marketlens" and float(tgt_pb.value) == 1.64


def test_metric_with_no_qualifying_source_is_unscored():
    store = store_of({TARGET: {"roe": 0.1}, "IOC.NS": {"roe": 0.2}})              # 2 of 12; Market Lens has no roe
    fsets, sources = build(store, {"roe": 0.1})
    assert sources["roe"] == {"source": None, "covered": 2, "of": 12}
    assert sources_of(fsets, "roe") == set()
    res = score_universe(fsets, weights_for(default_profile()), CFG, TODAY, NOW)
    assert "roe" not in res[TARGET].metric_scores


def test_target_rank_matches_hand_calculation():
    fsets, sources = build(store_of({}), {"pe_ttm": 18.68})                       # empty store: Market Lens P/E for all
    assert sources["pe_ttm"]["source"] == "nse_marketlens"
    res = score_universe(fsets, weights_for(default_profile()), CFG, TODAY, NOW)
    pes = sorted(r["peRatio"] for r in ROWS.values())
    pos = pes.index(18.68)                                                        # 0-based ascending: 9 of 0..11
    expected = 100 - pos / (len(pes) - 1) * 100                                   # lower P/E is better
    assert res[TARGET].metric_scores["pe_ttm"] == pytest.approx(expected, abs=0.01)
    assert res[TARGET].n == 12


def test_pool_store_value_for_target_is_its_fresh_value():
    store = store_of({t + ".NS": {"pe_ttm": 10.0 + i} for i, t in enumerate(SYMS)})
    store["metrics"][TARGET]["pe_ttm"]["value"] = 99.0                            # stale stored value for the target
    fsets, _ = build(store, {"pe_ttm": 18.68})
    f = next(f for f in fsets[TARGET].facts if f.metric == "pe_ttm")
    assert float(f.value) == 18.68


def test_target_always_a_member_even_if_not_listed():
    fsets, sources = build(store_of({}), {"pe_ttm": 18.68}, symbols=[s for s in SYMS if s != "RELIANCE"])
    assert TARGET in fsets and sources["pe_ttm"]["of"] == 12


def test_ml_metrics_ignore_placeholders_and_scale_ratios():
    m = marketlens.score_metrics_for(ROWS["RELIANCE"], nifty_1y=0.05)
    assert m["pe_ttm"] == 18.68 and m["return_1y"] == pytest.approx(-0.1107)
    assert m["relative_return_1y"] == pytest.approx(-0.1107 - 0.05)
    assert m["volatility_1y"] == pytest.approx(0.2942)
    assert m["pct_from_52w_high"] == pytest.approx(1324.4 / 1611.8 - 1)
    assert not {"roe", "beta_1y", "max_drawdown_3y", "revenue_yoy", "net_income_yoy"} & set(m)
    assert "pb" not in marketlens.score_metrics_for(ROWS["CASTROLIND"])
    assert "relative_return_1y" not in marketlens.score_metrics_for(ROWS["RELIANCE"])


def test_sector_members_falls_back_to_subsector_when_small():
    rows = {**ROWS, "TINY1": {**ROWS["IOC"], "sector": "Tiny", "subSector": "Energy"}}
    syms, kind, name = marketlens.sector_members("RELIANCE", rows)
    assert kind == "sector" and name == "Petroleum Products" and len(syms) == 12
    syms, kind, name = marketlens.sector_members("TINY1", rows, min_sector=8)
    assert kind == "subSector" and name == "Energy" and len(syms) == 13 and "TINY1" in syms
    assert marketlens.sector_members("NOPE", rows) is None


# ---- CLI wiring ------------------------------------------------------------------------------------------------

FULL = ("pe_ttm", "pb", "roe", "net_margin_q", "debt_to_equity", "return_1y", "relative_return_1y", "pct_from_52w_high")


def _env(monkeypatch, tmp_path, with_store=True):
    from indiafacts import cli

    monkeypatch.setenv("INDIAFACTS_MARKETLENS", "1")
    monkeypatch.setattr(marketlens, "universe_with_reason", lambda *a, **k: (ROWS, ""))
    monkeypatch.setattr(marketlens, "target_row", lambda *a, **k: (None, "", ""))
    poolstore.reset_cache()
    if with_store:
        per = {t + ".NS": {m: 0.1 + i * 0.01 + j * 0.001 for j, m in enumerate(FULL)} for i, t in enumerate(SYMS)}
        path = poolstore.write(store_of(per, nifty=0.05), tmp_path / "pm.json")
        monkeypatch.setenv("INDIAFACTS_POOL_METRICS_URL", path.as_uri())
    return cli


def test_scorecard_sector_mode_needs_no_fetching(monkeypatch, tmp_path):
    cli = _env(monkeypatch, tmp_path)
    fs = mkfs(TARGET, {m: 0.1 + 0.055 + j * 0.001 for j, m in enumerate(FULL)})
    monkeypatch.setattr(cli, "build_factset", lambda *a, **k: pytest.fail("pool member fetched"))
    sc = cli._sector_scorecard(SimpleNamespace(no_marketlens=False, as_of=None), fs, default_profile())
    assert sc["comparison"] == "sector" and sc["n"] == 12 and len(sc["members"]) == 12
    assert sc["pool_label"] == "NSE Market Lens sector 'Petroleum Products' (12 companies)"
    assert sc["metric_sources"]["pe_ttm"] == {"source": "pool_store", "covered": 12, "of": 12}
    assert sc["result"].status == "ok" and isinstance(sc["result"].rank, int)


def test_scorecard_falls_back_to_pool_without_marketlens_or_store(monkeypatch, tmp_path):
    from types import SimpleNamespace as NS

    cli = _env(monkeypatch, tmp_path, with_store=False)
    fs = mkfs(TARGET, {"pe_ttm": 18.0})
    args = NS(no_marketlens=False, as_of=None)
    assert cli._sector_scorecard(args, fs, default_profile()) is None             # no comparison data published
    monkeypatch.setenv("INDIAFACTS_MARKETLENS", "0")
    assert cli._sector_scorecard(args, fs, default_profile()) is None             # Market Lens off
    monkeypatch.setenv("INDIAFACTS_MARKETLENS", "1")
    monkeypatch.setattr(marketlens, "universe_with_reason", lambda *a, **k: ({}, "down"))
    assert cli._sector_scorecard(args, fs, default_profile()) is None             # Market Lens unavailable
    monkeypatch.setattr(marketlens, "universe_with_reason", lambda *a, **k: ({k_: v for k_, v in ROWS.items() if k_ != "RELIANCE"}, ""))
    assert cli._sector_scorecard(args, fs, default_profile()) is None             # target not in Market Lens


def test_summary_exposes_comparison_fields():
    from indiafacts.models import Entity as _E  # noqa: F401
    from indiafacts.summary import summarize_run  # noqa: F401
    # field wiring is covered through the scorecard keys; summary reads them with .get so pool scorecards stay valid
    import inspect
    from indiafacts import summary

    src = inspect.getsource(summary.summarize_run)
    assert '"comparison"' in src and '"metric_sources"' in src and '"set_size"' in src and '"pool_label"' in src


# ---- poolstore -------------------------------------------------------------------------------------------------

def test_metrics_for_equals_scoring_extraction():
    fs = mkfs("TCS.NS", {"pe_ttm": 20.0, "pb": 5.0, "roe": 9.0})                  # roe 9.0 is outside valid range: excluded
    got = poolstore.metrics_for(fs, CFG, TODAY, NOW)
    facts, _ = extract_facts(fs, CFG, TODAY, NOW)
    assert set(got) == set(facts) == {"pe_ttm", "pb"}
    assert got["pe_ttm"] == {"value": 20.0, "source": "yahoo", "as_of": TODAY.isoformat()}


def test_store_round_trip_and_nifty(tmp_path, monkeypatch):
    fs = {"TCS.NS": mkfs("TCS.NS", {"pe_ttm": 20.0, "return_1y": 0.2, "relative_return_1y": 0.15})}
    store = poolstore.from_factsets(fs, CFG, TODAY, NOW, commit="abc")
    assert store["metrics"]["^NSEI"]["return_1y"]["value"] == pytest.approx(0.05)
    assert store["meta"]["commit"] == "abc" and store["meta"]["n"] == 1 and store["meta"]["policy_hash"] == poolstore.policy_hash()
    path = poolstore.write(store, tmp_path / "pool_metrics.json")
    poolstore.reset_cache()
    monkeypatch.setenv("INDIAFACTS_POOL_METRICS_URL", path.as_uri())
    assert poolstore.load() == store


def test_load_never_raises_and_falls_back_to_local_copy(tmp_path, monkeypatch):
    poolstore.reset_cache()
    monkeypatch.delenv("INDIAFACTS_POOL_METRICS_URL", raising=False)
    assert poolstore.load() is None                                               # nothing anywhere
    store = store_of({TARGET: {"pe_ttm": 1.0}})
    poolstore.write(store, poolstore.local_path())
    assert poolstore.load() == store                                              # local fallback
    monkeypatch.setenv("INDIAFACTS_POOL_METRICS_URL", (tmp_path / "missing.json").as_uri())
    poolstore.reset_cache()
    assert poolstore.load() == store                                              # bad URL: still the local copy
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setenv("INDIAFACTS_POOL_METRICS_URL", bad.as_uri())
    poolstore.reset_cache()
    assert poolstore.load() == store
    poolstore.local_path().write_text("garbage")
    assert poolstore.load() is None


def test_load_memory_cache_one_hour(tmp_path, monkeypatch):
    path = poolstore.write(store_of({TARGET: {"pe_ttm": 1.0}}), tmp_path / "a.json")
    monkeypatch.setenv("INDIAFACTS_POOL_METRICS_URL", path.as_uri())
    poolstore.reset_cache()
    first = poolstore.load(mono=lambda: 100.0)
    path.write_text("{}")
    assert poolstore.load(mono=lambda: 200.0) == first                            # within the hour: memory
    assert poolstore.load(mono=lambda: 100.0 + 3700) == first                     # after: re-read fails, memory copy kept


# ---- snapshot stage 1 --------------------------------------------------------------------------------------------

def test_snapshot_stage_writes_pool_metrics(tmp_path, monkeypatch):
    from indiafacts import snapshots

    monkeypatch.setenv("INDIAFACTS_POOL_METRICS_URL", "")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    built = []

    def builder(t):
        built.append(t)
        return mkfs(t, {"pe_ttm": 10.0 + len(built), "return_1y": 0.2, "relative_return_1y": 0.1})

    monkeypatch.setattr("indiafacts.universe.default_cache_dir", lambda: tmp_path / "cache")
    out = tmp_path / "out"
    path = snapshots._prepare_pool_metrics(out, ["TCS.NS", "INFY.NS", "ITC.NS"], builder=builder, log=lambda *a: None)
    assert path == out / "pool_metrics.json" and path.exists()
    data = json.loads(path.read_text())
    assert set(data["metrics"]) == {"TCS.NS", "INFY.NS", "ITC.NS", "^NSEI"} and data["meta"]["n"] == 3
    import os
    assert os.environ["INDIAFACTS_POOL_METRICS_URL"] == path.resolve().as_uri()
    monkeypatch.delenv("INDIAFACTS_POOL_METRICS_URL")


def test_snapshot_stage_never_raises_and_keeps_yesterdays_file(tmp_path, monkeypatch):
    from indiafacts import snapshots

    monkeypatch.setattr("indiafacts.universe.default_cache_dir", lambda: tmp_path / "cache")
    out = tmp_path / "out"
    out.mkdir()
    (out / "pool_metrics.json").write_text(json.dumps(store_of({TARGET: {"pe_ttm": 1.0}})))

    def boom(t):
        raise RuntimeError("yahoo down")

    path = snapshots._prepare_pool_metrics(out, ["TCS.NS"], builder=boom, log=lambda *a: None)
    assert path == out / "pool_metrics.json" and json.loads(path.read_text())["metrics"][TARGET]
    monkeypatch.delenv("INDIAFACTS_POOL_METRICS_URL", raising=False)
