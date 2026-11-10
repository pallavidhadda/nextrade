"""The daily copy of NSE filings: written by the snapshot job, read where NSE refuses the server. Offline."""
import json
from urllib.error import HTTPError

import pytest

from indiafacts import nseapi
from indiafacts.xbrl import facts_from_nse_xbrl
from tests.test_nseapi import FakeNse, api


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_NSE_API", "1")
    nseapi._copy_cache.clear()
    yield
    nseapi._copy_cache.clear()


def make_copy(tmp_path, monkeypatch, symbol="RELIANCE"):
    """Run the live path against the fixtures with INDIAFACTS_NSE_COPY_OUT set, as the snapshot job does."""
    out = tmp_path / "pub"
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_OUT", str(out))
    a = api(FakeNse(), tmp_path / "c1")
    sh, rows, _ = a.latest_shareholding(symbol)
    parsed, _ = a.quarterly_filings(symbol)
    path = a.save_copy(symbol)
    monkeypatch.delenv("INDIAFACTS_NSE_COPY_OUT")
    return out, path, sh, rows, parsed


def strip(f):
    d = f.model_dump(mode="json")
    d["evidence"] = d["evidence"].split(" | official NSE filing ")[0]
    return d


def test_job_writes_compact_copy(tmp_path, monkeypatch):
    out, path, sh, rows, parsed = make_copy(tmp_path, monkeypatch)
    doc = json.loads(path.read_text())
    assert path == out / "RELIANCE.json" and doc["symbol"] == "RELIANCE" and doc["version"] == 1 and doc["generated_at"]
    assert doc["shareholding"]["as_on"] == "2026-09-30" and 0 < len(doc["shareholding"]["rows"]) <= 8
    r = doc["results"][0]
    assert {"period", "basis", "audited", "filing_date", "xbrl_url", "facts"} <= set(r) and r["xbrl_url"].startswith("https://nsearchives")
    assert len(parsed) == len(doc["results"]) and path.stat().st_size < 400_000


def test_reader_rebuilds_the_same_facts_as_live(tmp_path, monkeypatch):
    out, path, sh, rows, live = make_copy(tmp_path, monkeypatch)
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_BASE", out.as_uri())
    monkeypatch.setenv("INDIAFACTS_NSE_API_LIVE", "0")
    a = api(FakeNse(fail=ConnectionError("must not be called")), tmp_path / "c2")
    sh2, rows2, why = a.latest_shareholding("RELIANCE")
    copied, notes = a.quarterly_filings("RELIANCE")
    assert why == "" and sh2.pct == sh.pct and sh2.as_on == sh.as_on and sh2.pledged_of_promoter == sh.pledged_of_promoter
    assert "daily copy as of" in sh2.source and rows2[0]["date"] == rows[0]["date"] and rows2[0]["pr_and_prgrp"] == rows[0]["pr_and_prgrp"]
    assert len(copied) == len(live) > 0
    for c, l in zip(copied, live):
        assert [strip(f) for f in c.facts] == [strip(f) for f in l.facts]
        assert c.entity == l.entity and c.filings == l.filings
        assert all("nsearchives.nseindia.com" in f.evidence and "daily copy as of" in f.evidence for f in c.facts)
        assert [f.fact_id for f in c.facts] == [f.fact_id for f in l.facts]
    assert a.copy_notice().startswith("official NSE filings from the daily copy as of ") and "does not answer this server directly" in a.copy_notice()


def test_403_falls_back_to_copy_and_stops_hammering(tmp_path, monkeypatch):
    out, *_ = make_copy(tmp_path, monkeypatch)
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_BASE", out.as_uri())
    op = FakeNse(fail=HTTPError("u", 403, "forbidden", {}, None))
    a = api(op, tmp_path / "c3")
    sh, rows, _ = a.latest_shareholding("RELIANCE")
    parsed, _ = a.quarterly_filings("RELIANCE")
    assert sh is not None and parsed and len(op.calls) == 1            # the first refusal ends live attempts for this client
    assert a.copy_dates and a.ok > 0


def test_copy_missing_keeps_existing_notice(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_BASE", (tmp_path / "none").as_uri())
    a = api(FakeNse(fail=HTTPError("u", 403, "forbidden", {}, None)), tmp_path / "c4")
    assert a.latest_shareholding("RELIANCE")[0] is None and a.quarterly_filings("RELIANCE")[0] == []
    assert a.ok == 0 and a.reasons and a.copy_notice() == ""
    assert "403" in a.reasons[0]


def test_copy_first_skips_live(tmp_path, monkeypatch):
    out, *_ = make_copy(tmp_path, monkeypatch)
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_BASE", out.as_uri())
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_FIRST", "1")
    op = FakeNse()
    a = api(op, tmp_path / "c5")
    assert a.latest_shareholding("RELIANCE")[0] is not None and a.quarterly_filings("RELIANCE")[0] and op.calls == []
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_BASE", (tmp_path / "none").as_uri())          # copy missing: live is tried
    nseapi._copy_cache.clear()
    assert api(op, tmp_path / "c6").latest_shareholding("RELIANCE")[0] is not None and op.calls


def test_memory_cache_one_hour(tmp_path, monkeypatch):
    out, *_ = make_copy(tmp_path, monkeypatch)
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_BASE", out.as_uri())
    t = {"now": 1000.0}
    a = nseapi.NseApi(cache=tmp_path / "c7", clock=lambda: t["now"])
    assert a._copy_doc("RELIANCE")
    (out / "RELIANCE.json").unlink()
    t["now"] += 3000
    assert a._copy_doc("RELIANCE")                                        # still cached
    t["now"] += 700
    assert a._copy_doc("RELIANCE") is None                                # expired, file gone


def test_copy_never_raises_on_garbage(tmp_path, monkeypatch):
    base = tmp_path / "bad"
    base.mkdir()
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_BASE", base.as_uri())
    monkeypatch.setenv("INDIAFACTS_NSE_API_LIVE", "0")
    for body in ("not json", "[]", json.dumps({"version": 1, "symbol": "RELIANCE", "generated_at": "2026-11-10T00:00:00+00:00",
                                              "shareholding": {"sh": {"bogus": 1}}, "results": [{"facts": 3}]}), json.dumps({"version": 9})):
        (base / "RELIANCE.json").write_text(body)
        nseapi._copy_cache.clear()
        a = api(FakeNse(), tmp_path / "c8")
        assert a.latest_shareholding("RELIANCE")[0] is None and a.quarterly_filings("RELIANCE")[0] == []
    assert api(FakeNse(), tmp_path / "c9").latest_shareholding("../x")[0] is None


def test_live_partial_keeps_earlier_results(tmp_path, monkeypatch):
    out, path, *_ = make_copy(tmp_path, monkeypatch)
    before = json.loads(path.read_text())["results"]
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_OUT", str(out))
    a = api(FakeNse({"integrated-filing-results": b"{}", "corporates-financial-results": b"[]"}), tmp_path / "c10")
    a.latest_shareholding("RELIANCE")
    a.quarterly_filings("RELIANCE")
    a.save_copy("RELIANCE")
    assert json.loads(path.read_text())["results"] == before


def test_nothing_written_when_live_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIAFACTS_NSE_COPY_OUT", str(tmp_path / "o"))
    a = api(FakeNse(fail=HTTPError("u", 403, "f", {}, None)), tmp_path / "c11")
    a.latest_shareholding("RELIANCE")
    assert a.save_copy("RELIANCE") is None and not (tmp_path / "o").exists()


def test_snapshot_job_sets_live_first_and_copy_dirs(tmp_path, monkeypatch):
    from indiafacts import snapshots

    monkeypatch.setenv("INDIAFACTS_NSE_COPY_FIRST", "1")
    monkeypatch.setenv("INDIAFACTS_NSE_API_LIVE", "0")
    d = snapshots._prepare_nse_copy(tmp_path)
    import os
    assert d == tmp_path / "nse" and d.is_dir() and os.environ["INDIAFACTS_NSE_COPY_OUT"] == str(d.resolve())
    assert os.environ["INDIAFACTS_NSE_COPY_BASE"].startswith("file://") and os.environ["INDIAFACTS_NSE_COPY_BASE"].endswith("/nse/")
    assert nseapi.live_enabled() and not nseapi.copy_first()
    for k in ("INDIAFACTS_NSE_COPY_OUT", "INDIAFACTS_NSE_COPY_BASE"):
        monkeypatch.delenv(k)


def test_xbrl_unchanged_by_copy(tmp_path):
    from tests.test_nseapi import FX
    assert facts_from_nse_xbrl(FX / "nse_ifr_cons_RELIANCE_2026Q2.xml").facts
