import io
import os
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from indiafacts.tej import (TejStore, TejUnavailable, isin_for, price_affecting_dates, symbol_changes_from_history,
                            universe_members)


def D(s):
    return date.fromisoformat(s)


def hist():
    rows = [
        ("INE758T01015", "ZOMATO", "2021-07-23", "2025-04-08"), ("INE758T01015", "ETERNAL", "2025-04-09", "2026-10-23"),
        ("INE155A01014", "TATAMOTORS", "2010-01-04", "2011-09-12"), ("INE155A01022", "TATAMOTORS", "2011-09-13", "2025-10-23"),
        ("INE155A01022", "TMPV", "2025-10-24", "2026-10-23"), ("INE1TAE01010", "TMCV", "2025-11-12", "2026-10-23"),
        ("INE_OLD", "REUSED", "2010-01-04", "2012-12-31"), ("INE_NEW", "REUSED", "2018-01-01", "2026-10-23"),
        ("INE002A01018", "RELIANCE", "2010-01-04", "2026-10-23"),
    ]
    return pd.DataFrame([dict(exchange="NSE", isin=i, symbol=s, valid_from=D(a), valid_to=D(b), trading_days=100)
                         for i, s, a, b in rows])


def actions():
    rows = [("TMPV", "INE155A01022", "2025-10-14", "demerger"), ("TMPV", "INE155A01022", "2025-06-04", "dividend"),
            ("OLDMRG", "INE_MRG", "2024-03-01", "merger"), ("ETERNAL", "INE758T01015", "2025-05-01", "bonus")]
    return pd.DataFrame([dict(exchange="NSE", symbol=s, isin=i, ex_date=D(d), type=t) for s, i, d, t in rows])


def universe():
    rows = []
    for rd, members in (("2020-01-01", ["AAA", "BBB", "CCC"]), ("2020-02-01", ["BBB", "DDD", "AAA"])):
        for r, s in enumerate(members, 1):
            rows.append(dict(exchange="NSE", rebalance_date=D(rd), valid_to=D("2030-01-01"), rank=r, symbol=s,
                             isin=f"INE{s}", name=f"{s} LTD", avg_turnover_63d=1000.0 - r))
    return pd.DataFrame(rows)


def parquet_bytes(df):
    b = io.BytesIO()
    df.to_parquet(b)
    return b.getvalue()


# ---- T1 store -------------------------------------------------------------
def test_store_downloads_once_then_serves_cache(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return parquet_bytes(hist())

    s = TejStore(tmp_path, fetch)
    a = s.load("symbol_history/nse.parquet")
    b = s.load("symbol_history/nse.parquet")
    assert len(calls) == 1 and calls[0].endswith("symbol_history/nse.parquet") and a.equals(b)


def test_store_refetches_after_a_day_and_rebuilds_corrupt_cache(tmp_path):
    calls = []
    s = TejStore(tmp_path, lambda u: (calls.append(u), parquet_bytes(hist()))[1])
    s.load("symbol_history/nse.parquet")
    later = datetime.now(timezone.utc) + timedelta(days=2)
    TejStore(tmp_path, lambda u: (calls.append(u), parquet_bytes(hist()))[1], now=lambda: later).load("symbol_history/nse.parquet")
    assert len(calls) == 2
    for f in tmp_path.iterdir():
        f.write_bytes(b"not parquet")
    s.load("symbol_history/nse.parquet")
    assert len(calls) == 3


def test_store_failure_raises_tej_unavailable_unless_stale_cache_exists(tmp_path):
    def boom(url):
        raise ConnectionError("down")

    with pytest.raises(TejUnavailable):
        TejStore(tmp_path, boom).load("symbol_history/nse.parquet")
    TejStore(tmp_path, lambda u: parquet_bytes(hist())).load("symbol_history/nse.parquet")
    later = datetime.now(timezone.utc) + timedelta(days=5)
    store = TejStore(tmp_path, boom, now=lambda: later)
    stale_ok = store.load("symbol_history/nse.parquet")
    assert len(stale_ok) == len(hist())          # stale data beats no data, and the age is exposed
    assert store.last_age_days is not None and store.last_age_days >= 5


# ---- T2 identity ----------------------------------------------------------
def test_symbol_changes_from_history_matches_known_renames():
    ch = {(c.old, c.new): c.effective for c in symbol_changes_from_history(hist())}
    assert ch[("ZOMATO", "ETERNAL")] == D("2025-04-09")
    assert ch[("TATAMOTORS", "TMPV")] == D("2025-10-24")
    assert ("TATAMOTORS", "TATAMOTORS") not in ch                      # ISIN change under the same symbol is not a rename
    assert not any(c.old == "TMCV" or c.new == "TMCV" for c in symbol_changes_from_history(hist()))


def test_isin_for_uses_validity_window_and_handles_reused_symbols():
    h = hist()
    assert isin_for(h, "RELIANCE") == "INE002A01018"
    assert isin_for(h, "ZOMATO", D("2024-01-01")) == "INE758T01015"
    assert isin_for(h, "ETERNAL") == "INE758T01015"
    assert isin_for(h, "REUSED", D("2011-01-01")) == "INE_OLD" and isin_for(h, "REUSED", D("2020-01-01")) == "INE_NEW"
    assert isin_for(h, "REUSED", D("2015-01-01")) is None               # gap: nobody traded under it
    assert isin_for(h, "NOSUCH") is None


# ---- T3 actions -----------------------------------------------------------
def test_price_affecting_dates_are_demergers_and_mergers_only_across_renames():
    a, h = actions(), hist()
    assert price_affecting_dates(a, h, "TMPV") == [D("2025-10-14")]
    assert price_affecting_dates(a, h, "TATAMOTORS") == [D("2025-10-14")]       # same ISIN as TMPV
    assert price_affecting_dates(a, h, "ETERNAL") == []                          # bonus is already adjusted in Close
    assert price_affecting_dates(a, h, "NOSUCH") == []


# ---- T4 universe ----------------------------------------------------------
def test_universe_uses_latest_rebalance_on_or_before_as_of_without_lookahead():
    u = universe()
    assert [m.symbol for m in universe_members(u, D("2020-01-15"))] == ["AAA", "BBB", "CCC"]
    assert [m.symbol for m in universe_members(u, D("2020-02-01"))] == ["BBB", "DDD", "AAA"]
    assert [m.symbol for m in universe_members(u, D("2020-03-01"), top_n=2)] == ["BBB", "DDD"]
    assert universe_members(u, D("2019-12-31")) == []
    m = universe_members(u, D("2020-01-15"))[0]
    assert (m.rank, m.isin, m.name) == (1, "INEAAA", "AAA LTD")
