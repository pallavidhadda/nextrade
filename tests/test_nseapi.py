import json
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

from indiafacts import nseapi
from indiafacts.pipeline import build_factset
from tests.fakes import FakeClient
from tests.test_shareholding import xml as shp_xml

FX = Path(__file__).parent / "fixtures"
SHP_URL = "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1742991_21102026042504_WEB.xml"
CONS_URL = "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1750537_30102026093254_WEB.xml"
PY_URL = "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1552809_17102025073643_WEB.xml"


class Resp:
    def __init__(self, body):
        self.b = BytesIO(body)

    def read(self, n=-1):
        return self.b.read(n)


class FakeNse:
    """Opener serving fixtures by URL; records requests."""

    def __init__(self, routes=None, fail=None):
        cons = (FX / "nse_ifr_cons_RELIANCE_2026Q2.xml").read_bytes()
        self.routes = {
            "corporate-share-holdings-master": (FX / "nse_corporate-share-holdings-master_RELIANCE.json").read_bytes(),
            "integrated-filing-results": (FX / "nse_integrated-filing-results_RELIANCE.json").read_bytes(),
            "corporates-financial-results": (FX / "nse_corporates-financial-results_RELIANCE.json").read_bytes(),
            SHP_URL: shp_xml("2026-09-30", prom=0.5044, sym="RELIANCE"),
            CONS_URL: cons,
            PY_URL: cons.replace(b"2026-", b"2025-"),
        }
        self.routes.update(routes or {})
        self.fail, self.calls, self.headers = fail, [], []

    def __call__(self, req, timeout=None):
        assert timeout == 15
        self.calls.append(req.full_url)
        self.headers.append(dict(req.header_items()))
        if self.fail:
            raise self.fail
        for k, v in self.routes.items():
            if k in req.full_url:
                return Resp(v)
        raise HTTPError(req.full_url, 404, "nf", {}, None)


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_NSE_API", "1")


def api(opener=None, tmp=None, clock=None):
    t = {"now": 1_000_000.0}
    return nseapi.NseApi(opener=opener or FakeNse(), cache=tmp, sleep=lambda s: t.__setitem__("now", t["now"] + s),
                         clock=clock or (lambda: t["now"]))


def test_shareholding_newest_row_selected_and_parsed(tmp_path):
    rows, why = api(tmp=tmp_path).shareholding_rows("RELIANCE")
    assert why == "" and len(rows) == 23 and rows[0]["date"] == "30-SEP-2026" and rows[0]["pr_and_prgrp"] == "50.44"
    sh, rows, why = api(tmp=tmp_path).latest_shareholding("RELIANCE")
    assert sh.symbol == "RELIANCE" and str(sh.as_on) == "2026-09-30" and sh.pct["promoter"] == pytest.approx(0.5044)
    assert "NSE API" in sh.source and sh.pledged_of_promoter is not None


def test_honest_headers_sent(tmp_path):
    op = FakeNse()
    api(op, tmp_path).shareholding_rows("RELIANCE")
    h = {k.lower(): v for k, v in op.headers[0].items()}
    assert h["user-agent"].startswith("NexTrade-research/0.1") and h["referer"] == "https://www.nseindia.com/"
    assert "cookie" not in h


def test_consolidated_preferred_and_covers_gap(tmp_path):
    entries, why = api(tmp=tmp_path).result_filings("RELIANCE")
    assert why == "" and entries[0]["end"].isoformat() == "2026-09-30" and entries[0]["basis"] == "consolidated"
    assert entries[0]["origin"] == "integrated filing"
    ends = {e["end"].isoformat() for e in entries if e["basis"] == "consolidated"}
    assert {"2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2024-12-31"} <= ends
    paths, notes = api(tmp=tmp_path).quarterly_xbrl("RELIANCE", n=1)
    assert len(paths) == 1 and paths[0].name.endswith("INTEGRATED_FILING_INDAS_1750537_30102026093254_WEB.xml") and notes == []


def test_standalone_fallback_is_labelled(tmp_path):
    rows = json.loads((FX / "nse_integrated-filing-results_RELIANCE.json").read_text())
    rows["data"] = [r for r in rows["data"] if r["consolidated"] == "Standalone"][:1]
    op = FakeNse({"integrated-filing-results": json.dumps(rows).encode(), "corporates-financial-results": b"[]",
                  "INTEGRATED_FILING_INDAS_1750535_30102026093155_WEB.xml": (FX / "nse_ifr_cons_RELIANCE_2026Q2.xml").read_bytes()})
    paths, notes = api(op, tmp_path).quarterly_xbrl("RELIANCE", n=1)
    assert len(paths) == 1 and any("standalone" in n for n in notes)


def test_xbrl_parser_reads_new_taxonomy_and_filing_date(tmp_path):
    from indiafacts.xbrl import facts_from_nse_xbrl

    real = tmp_path / "INTEGRATED_FILING_INDAS_1750537_30102026093254_WEB.xml"      # the filing date is read from the real file name
    real.write_bytes((FX / "nse_ifr_cons_RELIANCE_2026Q2.xml").read_bytes())
    fs = facts_from_nse_xbrl(real)
    m = {(f.metric, f.period_type.value): f for f in fs.facts}
    assert m[("revenue", "Q")].basis.value == "consolidated" and str(m[("revenue", "Q")].available_from) == "2026-10-30"
    assert float(m[("net_income", "Q")].value) > 0 and str(m[("revenue", "Q")].period_end) == "2026-09-30"


def test_list_cache_ttl(tmp_path):
    op, t = FakeNse(), {"now": 1000.0}
    a = nseapi.NseApi(opener=op, cache=tmp_path, sleep=lambda s: None, clock=lambda: t["now"])
    a.shareholding_rows("RELIANCE")
    a.shareholding_rows("RELIANCE")
    assert len(op.calls) == 1
    t["now"] += 25 * 3600
    a.shareholding_rows("RELIANCE")
    assert len(op.calls) == 2


def test_files_cached_forever(tmp_path):
    op, t = FakeNse(), {"now": 1000.0}
    a = nseapi.NseApi(opener=op, cache=tmp_path, sleep=lambda s: None, clock=lambda: t["now"])
    p1, _ = a.get_file(SHP_URL)
    t["now"] += 10 * 365 * 86400
    p2, _ = a.get_file(SHP_URL)
    assert p1 == p2 and len(op.calls) == 1


def test_never_raises_and_returns_reason(tmp_path):
    for i, exc in enumerate((ConnectionError("down"), TimeoutError("slow"), HTTPError("u", 403, "forbidden", {}, None))):
        a = api(FakeNse(fail=exc), tmp_path / str(i))
        rows, why = a.shareholding_rows("X")
        assert rows == [] and why
        assert a.latest_shareholding("X")[0] is None
        assert a.quarterly_xbrl("X")[0] == []
        assert a.get_file(SHP_URL)[0] is None
    assert "403" in api(FakeNse(fail=HTTPError("u", 403, "f", {}, None)), tmp_path / "z").shareholding_rows("X")[1]


def test_garbage_bodies_do_not_raise(tmp_path):
    op = FakeNse({"corporate-share-holdings-master": b"<html>blocked</html>", SHP_URL: b"not xml"})
    assert api(op, tmp_path).latest_shareholding("RELIANCE")[0] is None
    op = FakeNse({SHP_URL: b"<a/>"})
    assert api(op, tmp_path / "b").latest_shareholding("RELIANCE")[0] is None


def test_retries_only_429_503_max_two(tmp_path):
    n = {"c": 0}

    def op(req, timeout=None):
        n["c"] += 1
        raise HTTPError(req.full_url, 429 if "master" in req.full_url else 403, "x", {}, None)
    api(op, tmp_path).shareholding_rows("X")
    assert n["c"] == 3
    n["c"] = 0
    api(op, tmp_path / "b").get_json("other", {})
    assert n["c"] == 1


def test_paced_at_least_one_second(tmp_path):
    sleeps = []
    t = {"now": 5_000_000.0}
    a = nseapi.NseApi(opener=FakeNse(), cache=tmp_path, sleep=lambda s: (sleeps.append(s), t.__setitem__("now", t["now"] + s)),
                      clock=lambda: t["now"])
    a.shareholding_rows("RELIANCE")
    a.result_filings("RELIANCE")
    assert sleeps and all(s >= 0.99 for s in sleeps)


def test_disabled_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("INDIAFACTS_NSE_API", "0")
    op = FakeNse()
    a = api(op, tmp_path)
    assert a.shareholding_rows("RELIANCE")[0] == [] and a.get_file(SHP_URL)[0] is None and op.calls == []
    fs = build_factset("RELIANCE.NS", client=FakeClient(), sleep=lambda s: None, nse_client=a)
    assert op.calls == [] and not any(f.source == "nse_xbrl" for f in fs.facts)


def test_browser_headers_off_by_default_on_with_switch(monkeypatch, tmp_path):
    op = FakeNse()
    api(op, tmp_path).shareholding_rows("RELIANCE")
    assert "Mozilla" not in str(op.headers[0])
    monkeypatch.setenv("INDIAFACTS_NSE_BROWSER_HEADERS", "1")
    op2 = FakeNse()
    api(op2, tmp_path / "b").shareholding_rows("RELIANCE")
    assert op2.calls[0] == "https://www.nseindia.com/" and "Mozilla" in str(op2.headers[1])


def test_host_allowlist(tmp_path):
    assert api(tmp=tmp_path).get_file("https://evil.example/x.xml")[0] is None


def test_pipeline_official_filings_give_yoy_and_ownership(tmp_path):
    lst = json.loads((FX / "nse_integrated-filing-results_RELIANCE.json").read_text())
    lst["data"] = [r for r in lst["data"] if r["consolidated"] == "Consolidated" and r["qe_Date"] in ("30-SEP-2026", "30-SEP-2025")]
    op = FakeNse({"integrated-filing-results": json.dumps(lst).encode(), "corporates-financial-results": b"[]"})
    fs = build_factset("RELIANCE.NS", client=FakeClient(), sleep=lambda s: None, nse_client=api(op, tmp_path))
    rev = [f for f in fs.facts if f.metric == "revenue_yoy"]
    assert rev and rev[0].status == "ok", [(f.status, f.reason) for f in rev]
    assert any(f.source == "nse_xbrl" and f.metric == "revenue" for f in fs.facts)
    own = {f.metric: f for f in fs.facts if f.source == "nse_shp"}
    assert float(own["sh_promoter"].value) == pytest.approx(0.5044) and "sh_foreign_inst" in own and "sh_promoter_pledged" in own
    assert "sh_promoter_change" in own


def test_row_change_fact_cites_both_rows():
    from indiafacts.pipeline import _row_change_fact

    rows = json.loads((FX / "nse_corporate-share-holdings-master_RELIANCE.json").read_text())
    [f] = _row_change_fact("RELIANCE.NS", rows, datetime.now(timezone.utc))
    assert float(f.value) == pytest.approx(-0.0004) and "30-JUN-2026" in f.evidence and f.source == "nse_shp"


def test_pipeline_unreachable_notice_and_continues(tmp_path):
    a = api(FakeNse(fail=ConnectionError("down")), tmp_path)
    fs = build_factset("RELIANCE.NS", client=FakeClient(), sleep=lambda s: None, nse_client=a)
    assert any("official NSE filings not reachable" in n for n in fs.notices) and fs.facts


def test_as_of_run_skips_api(tmp_path):
    op = FakeNse()
    build_factset("RELIANCE.NS", as_of=date(2026, 1, 1), client=FakeClient(), sleep=lambda s: None, nse_client=api(op, tmp_path))
    assert op.calls == []
