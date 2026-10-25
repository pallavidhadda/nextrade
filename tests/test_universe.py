from datetime import datetime, timedelta, timezone

import pytest

from indiafacts.models import Entity
from indiafacts.universe import DEFAULT_POOL, build_universe, read_tickers
from tests.test_scoring import mkfs

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)


def test_read_tickers_skips_comments_blank_lines_and_dedupes(tmp_path):
    p = tmp_path / "u.txt"
    p.write_text("# pool\nreliance.ns\n\n TCS.NS \nRELIANCE.NS\nM&M.NS\n")
    assert read_tickers(p) == ["RELIANCE.NS", "TCS.NS", "M&M.NS"]


def test_read_tickers_rejects_bad_symbols(tmp_path):
    p = tmp_path / "u.txt"
    p.write_text("RELIANCE.NS\n../etc/passwd\n")
    with pytest.raises(ValueError, match="invalid ticker"):
        read_tickers(p)


def test_default_pool_has_thirty_valid_unique_tickers():
    t = read_tickers(DEFAULT_POOL)
    assert len(t) == 30 and len(set(t)) == 30 and "RELIANCE.NS" in t


def builder_factory(calls):
    def build(t):
        calls.append(t)
        return mkfs(t, {"pe_ttm": 10.0})
    return build


def test_cache_hit_skips_builder_and_stale_cache_refetches(tmp_path):
    calls = []
    b = builder_factory(calls)
    fs, failed = build_universe(["A.NS", "B.NS"], b, tmp_path, now=NOW)
    assert sorted(calls) == ["A.NS", "B.NS"] and not failed and set(fs) == {"A.NS", "B.NS"}
    calls.clear()
    build_universe(["A.NS", "B.NS"], b, tmp_path, now=NOW + timedelta(hours=2))
    assert calls == []                                                   # fresh cache
    build_universe(["A.NS"], b, tmp_path, now=NOW + timedelta(days=2))
    assert calls == ["A.NS"]                                              # older than 1 day


def test_one_failing_ticker_is_reported_not_fatal(tmp_path):
    def b(t):
        if t == "BAD.NS":
            raise ConnectionError("down")
        return mkfs(t, {"pe_ttm": 10.0})

    fs, failed = build_universe(["OK.NS", "BAD.NS"], b, tmp_path, now=NOW)
    assert set(fs) == {"OK.NS"} and "BAD.NS" in failed and "ConnectionError" in failed["BAD.NS"]


def test_unresolved_entities_are_excluded_with_reason(tmp_path):
    def b(t):
        f = mkfs(t, {"pe_ttm": 10.0})
        return f.model_copy(update={"entity": f.entity.unresolved("no data")}) if t == "GONE.NS" else f

    fs, failed = build_universe(["OK.NS", "GONE.NS"], b, tmp_path, now=NOW)
    assert set(fs) == {"OK.NS"} and "no data" in failed["GONE.NS"]


def test_corrupt_cache_file_is_ignored_and_rebuilt(tmp_path):
    (tmp_path / "A.NS.json").write_text("{broken")
    calls = []
    build_universe(["A.NS"], builder_factory(calls), tmp_path, now=NOW)
    assert calls == ["A.NS"]


def test_cache_written_by_an_older_schema_is_rebuilt(tmp_path):
    import json

    calls = []
    b = builder_factory(calls)
    build_universe(["A.NS"], b, tmp_path, now=NOW)
    f = tmp_path / "A.NS.json"
    blob = json.loads(f.read_text())
    assert blob["schema"] >= 2
    blob.pop("schema")                                   # what a cache from before the chart data looks like
    f.write_text(json.dumps(blob))
    calls.clear()
    build_universe(["A.NS"], b, tmp_path, now=NOW + timedelta(hours=1))
    assert calls == ["A.NS"]
