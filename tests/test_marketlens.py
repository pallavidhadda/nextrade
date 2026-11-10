import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from indiafacts import marketlens as ml
from indiafacts.analysis import SOURCE_RANK
from indiafacts.models import Status
from indiafacts.peers import marketlens_peers
from indiafacts.pipeline import _marketlens_facts
from tests.test_scoring import mkfs

FIX = Path(__file__).parent / "fixtures" / "marketlens_petroleum_products.json"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def rows():
    body = json.loads(FIX.read_text())
    return {r["id"]: {**r, "_sectorId": "petroleum products"} for r in body["data"]}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(calls):
    body = json.loads(FIX.read_text())

    def opener(req, timeout=None):
        calls.append(req)
        if req.full_url.endswith("/api/sectors"):
            return Resp(json.dumps({"success": True, "data": [{"id": "petroleum products", "name": "Petroleum Products"}]}).encode())
        return Resp(json.dumps(body).encode())
    return opener


def by_metric(facts):
    return {f.metric: f for f in facts}


def test_mapping_and_units():
    m = by_metric(ml.facts_for("RELIANCE", rows()["RELIANCE"], NOW))
    assert float(m["market_cap"].value) == pytest.approx(17922494283416.8)
    assert float(m["pe_ttm"].value) == 18.68 and float(m["pb"].value) == 1.64
    assert float(m["debt_to_equity"].value) == 0.41
    assert float(m["dividend_yield"].value) == pytest.approx(0.0045)
    assert float(m["sh_promoter"].value) == pytest.approx(0.5044) and float(m["sh_public"].value) == pytest.approx(0.4956)
    assert m["ml_roce"].status == Status.unverified and float(m["ml_roce"].value) == pytest.approx(0.0919)
    f = m["pe_ttm"]
    assert f.source == "nse_marketlens" and f.period_end.isoformat() == "2026-11-09"
    assert f.evidence == "NSE Market Lens /api/sectors/petroleum products/stocks field peRatio, lastUpdated 2026-11-09T16:00:27"


def test_placeholder_zeros_and_bad_fields_skipped():
    m = by_metric(ml.facts_for("RELIANCE", rows()["RELIANCE"], NOW))
    assert not {"roe", "revenue_growth", "industry_pe", "avg_volume", "net_profit", "pat_growth"} & set(m)
    castrol = by_metric(ml.facts_for("CASTROLIND", rows()["CASTROLIND"], NOW))
    assert "pb" not in castrol                       # pbRatio 0
    r = {**rows()["RELIANCE"], "promoterHolding": 10, "publicHolding": 10}
    assert "sh_promoter" not in by_metric(ml.facts_for("RELIANCE", r, NOW))   # does not add to 100


def test_source_rank():
    assert SOURCE_RANK.index("nse_shp") < SOURCE_RANK.index("nse_marketlens") < SOURCE_RANK.index("computed:selfvalue") < SOURCE_RANK.index("yahoo")


def test_pe_conflict_is_shown_with_both_values():
    fs = mkfs("RELIANCE.NS", {"pe_ttm": 21.8, "market_cap": 17.9e12})
    notices = []
    out = _marketlens_facts(fs, list(fs.facts), rows(), notices)
    chk = [f for f in out if f.metric == "pe_ttm_source_check"][0]
    assert chk.status == Status.conflict and "18.68" in chk.reason and "21.8" in chk.reason
    assert not [f for f in out if f.metric == "market_cap_source_check" and f.status == Status.conflict]
    assert any(f.metric == "pe_ttm" and f.source == "nse_marketlens" for f in out)


def test_official_shareholding_not_overridden():
    fs = mkfs("RELIANCE.NS", {"sh_promoter": 0.5044})
    out = _marketlens_facts(fs, list(fs.facts), rows(), [])
    assert not [f for f in out if f.metric == "sh_promoter"]


def test_not_in_universe_adds_nothing():
    fs = mkfs("TCS.NS", {"pe_ttm": 25})
    assert _marketlens_facts(fs, list(fs.facts), rows(), []) == []


def test_peers_from_sector():
    fs = mkfs("RELIANCE.NS", {"market_cap": 17.9e12, "pe_ttm": 21.8})
    got = marketlens_peers(fs, rows())
    assert got is not None
    g, cmps = got
    assert "RELIANCE.NS" not in [p.ticker for p in g.picks]
    assert g.picks and all(p.tier == 1 for p in g.picks)
    assert any("NSE Market Lens sector 'Petroleum Products'" in n for n in g.notes)
    pe = [c for c in cmps if c.metric == "pe_ttm"][0]
    assert pe.status == "ok" and pe.n >= 3
    assert marketlens_peers(mkfs("TCS.NS", {"market_cap": 1e12}), rows()) is None


def test_client_errors_never_raise():
    def boom(req, timeout=None):
        raise OSError("down")

    c = ml.Client(opener=boom, sleep=lambda s: None)
    assert c.sectors()[0] == [] and "unavailable" in c.sectors()[1]
    assert c.sector_stocks("x")[0] == []
    assert ml.fetch_universe(c)[0] == {}

    def junk(req, timeout=None):
        return Resp(b"<html>not json")
    assert ml.Client(opener=junk, sleep=lambda s: None).sectors()[0] == []


def test_polite_delay_and_headers():
    calls, waits = [], []
    c = ml.Client(opener=fake_opener(calls), sleep=waits.append, delay=0.1, clock=lambda: 0.0)
    out, problems = ml.fetch_universe(c)
    assert "RELIANCE" in out and out["RELIANCE"]["_sectorId"] == "petroleum products" and not problems
    assert len(calls) == 2 and waits == [1.0]                       # delay is never below one second
    assert calls[0].get_header("User-agent") == ml.USER_AGENT
    assert "petroleum%20products" in calls[1].full_url


def test_cache_ttl(monkeypatch, tmp_path):
    monkeypatch.setenv("INDIAFACTS_MARKETLENS", "1")
    monkeypatch.setenv("INDIAFACTS_MARKETLENS_CACHE", str(tmp_path / "ml.json"))
    calls = []
    mk = lambda: ml.Client(opener=fake_opener(calls), sleep=lambda s: None)
    r1, _ = ml.universe_with_reason(mk(), NOW)
    assert "RELIANCE" in r1 and len(calls) == 2
    ml.universe_with_reason(mk(), NOW + timedelta(hours=23))
    assert len(calls) == 2                                          # fresh cache, no new requests
    ml.universe_with_reason(mk(), NOW + timedelta(hours=25))
    assert len(calls) == 4                                          # expired


def test_stale_cache_used_when_refresh_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("INDIAFACTS_MARKETLENS", "1")
    monkeypatch.setenv("INDIAFACTS_MARKETLENS_CACHE", str(tmp_path / "ml.json"))
    ml.universe_with_reason(ml.Client(opener=fake_opener([]), sleep=lambda s: None), NOW)

    def boom(req, timeout=None):
        raise OSError("down")
    r, why = ml.universe_with_reason(ml.Client(opener=boom, sleep=lambda s: None), NOW + timedelta(days=3))
    assert "RELIANCE" in r and "older cache" in why


def test_disabled_by_env(monkeypatch):
    assert ml.universe_with_reason() == ({}, "Market Lens switched off")


# ---- live target path ---------------------------------------------------------------------------------------------

def _copy_file(tmp_path, at="2026-11-09T12:00:00+00:00"):
    p = tmp_path / "daily.json"
    p.write_text(json.dumps({"fetched_at": at, "problems": [], "rows": rows()}))
    return p


def _live_opener(pe, calls):
    body = json.loads(FIX.read_text())
    body["data"] = [{**r, "peRatio": pe} if r["id"] == "RELIANCE" else r for r in body["data"]]

    def opener(req, timeout=None):
        calls.append((req.full_url, timeout))
        return Resp(json.dumps(body).encode())
    return opener


@pytest.fixture
def fresh_state(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_MARKETLENS", "1")
    ml._live.clear()
    ml._mem.update(url=None, at=0.0, rows=None, fetched=None)


def test_live_request_preferred_over_daily_copy(monkeypatch, tmp_path, fresh_state):
    monkeypatch.setenv("INDIAFACTS_MARKETLENS_URL", _copy_file(tmp_path).as_uri())
    calls = []
    row, origin, why = ml.target_row("RELIANCE.NS", opener=_live_opener(19.5, calls), sleep=lambda s: None)
    assert origin == "live" and row["peRatio"] == 19.5
    assert len(calls) == 1 and calls[0][1] == 10 and "petroleum%20products" in calls[0][0]
    again = ml.target_row("RELIANCE", opener=_live_opener(1, calls), sleep=lambda s: None)
    assert again[0]["peRatio"] == 19.5 and len(calls) == 1                  # cached for an hour in this process
    f = [x for x in ml.facts_for("RELIANCE", row, NOW, origin) if x.metric == "pe_ttm"][0]
    assert f.evidence.endswith("lastUpdated 2026-11-09T16:00:27; fetched live")


def test_falls_back_to_daily_copy_when_live_fails(monkeypatch, tmp_path, fresh_state):
    monkeypatch.setenv("INDIAFACTS_MARKETLENS_URL", _copy_file(tmp_path).as_uri())

    def boom(req, timeout=None):
        raise TimeoutError("slow")
    row, origin, why = ml.target_row("RELIANCE", opener=boom, sleep=lambda s: None)
    assert origin == "daily copy as of 2026-11-09" and row["peRatio"] == 18.68 and "live request failed" in why


def test_live_switch_off_and_local_cache_fallback(monkeypatch, tmp_path, fresh_state):
    cache = tmp_path / "ml.json"
    monkeypatch.setenv("INDIAFACTS_MARKETLENS_CACHE", str(cache))
    monkeypatch.setenv("INDIAFACTS_MARKETLENS_LIVE", "0")
    cache.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "problems": [], "rows": rows()}))
    calls = []
    row, origin, _ = ml.target_row("RELIANCE", opener=_live_opener(19.5, calls), sleep=lambda s: None)
    assert origin.startswith("local cache as of") and row["peRatio"] == 18.68 and not calls


def test_pipeline_records_origin_in_evidence_and_notice(monkeypatch, tmp_path, fresh_state):
    monkeypatch.setenv("INDIAFACTS_MARKETLENS_URL", _copy_file(tmp_path).as_uri())
    real, opener = ml.urlopen, _live_opener(19.5, [])
    monkeypatch.setattr(ml, "urlopen", lambda req, timeout=None: real(req, timeout=timeout) if req.full_url.startswith("file:") else opener(req, timeout))
    fs = mkfs("RELIANCE.NS", {"pe_ttm": 21.8})
    notices = []
    out = _marketlens_facts(fs, list(fs.facts), None, notices)
    assert any("fetched live" in n for n in notices)
    assert all("fetched live" in f.evidence for f in out if f.source == "nse_marketlens")
