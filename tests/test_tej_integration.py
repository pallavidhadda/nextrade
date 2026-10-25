import pandas as pd
import pytest

from indiafacts.cli import main
from indiafacts.pipeline import AmbiguousSymbol, build_factset
from indiafacts.render import render
from indiafacts.tej import TejStore
from tests.fakes import FakeClient
from tests.pricefakes import FakePrices, frame
from tests.test_price_integration import END, long_pair
from tests.test_tej import actions, hist, parquet_bytes, universe

NS = dict(sleep=lambda s: None)


def routes():
    h = pd.concat([hist(), pd.DataFrame([dict(exchange="NSE", isin="INE_MRG", symbol="OLDMRG",
                                              valid_from=pd.Timestamp("2015-01-01").date(),
                                              valid_to=pd.Timestamp("2026-10-23").date(), trading_days=10)])])
    return {"symbol_history/nse.parquet": parquet_bytes(h), "universe/nse_liquid.parquet": parquet_bytes(universe()),
            **{f"actions/nse_{y}.parquet": parquet_bytes(actions()) for y in range(2020, 2027)}}


def store(tmp_path, missing=()):
    r = routes()

    def fetch(url):
        key = url.split("/resolve/main/")[1]
        if key in missing or key not in r:
            raise ConnectionError(f"no route {key}")
        return r[key]

    return TejStore(tmp_path / "tej", fetch)


def test_rename_resolved_from_tej_history_with_attribution(tmp_path):
    fs = build_factset("ZOMATO.NS", client=FakeClient(), tej=True, tej_store=store(tmp_path), **NS)
    assert fs.entity.ticker == "ETERNAL.NS"
    assert any("ZOMATO is now ETERNAL" in n and "TejHQ" in n for n in fs.notices)


def test_isin_filled_from_tej_when_no_filing(tmp_path):
    fs = build_factset("ETERNAL.NS", client=FakeClient(), tej=True, tej_store=store(tmp_path), **NS)
    assert fs.entity.isin.value == "INE758T01015" and fs.entity.isin.status == "ok"
    assert "ISIN INE758T01015" in render(fs)


def test_demerger_still_asks_the_user_with_tej_only(tmp_path):
    with pytest.raises(AmbiguousSymbol):
        build_factset("TATAMOTORS.NS", client=FakeClient(), tej=True, tej_store=store(tmp_path), **NS)


def test_tej_merger_action_flags_price_windows_unverified(tmp_path):
    fs = build_factset("OLDMRG.NS", as_of=END, client=FakeClient(), prices=True, tej=True,
                       price_client=long_pair("OLDMRG.NS", n=1000), tej_store=store(tmp_path), **NS)
    r3 = [f for f in fs.facts if f.metric == "return_3y"][0]
    assert r3.status == "unverified" and "2024-03-01" in r3.reason


def test_tej_unavailable_degrades_with_a_notice_and_the_report_still_renders(tmp_path):
    dead = TejStore(tmp_path / "dead", lambda u: (_ for _ in ()).throw(ConnectionError("down")))
    fs = build_factset("RELIANCE.NS", client=FakeClient(), tej=True, tej_store=dead, **NS)
    assert any("TejHQ data unavailable" in n for n in fs.notices) and fs.facts
    assert fs.entity.isin.status == "unavailable"


def test_cli_universe_tej_top_n_uses_point_in_time_members(tmp_path, capsys):
    code = main(["AAA.NS", "--score", "--universe", "tej:5", "--no-prices", "--as-of", "2020-01-15"],
                client=FakeClient(), sleep=lambda s: None, tej_store=store(tmp_path))
    out = capsys.readouterr().out
    assert code == 0 and "SCORECARD" in out and "inside 3 companies" in out and "TejHQ" in out   # 3 members at the 2020-01-01 rebalance


def test_cli_no_tej_flag_skips_tej(tmp_path, capsys):
    s = store(tmp_path)
    code = main(["ZOMATO.NS", "--no-tej", "--no-prices"], client=FakeClient(), sleep=lambda s_: None, tej_store=s)
    assert code == 0 and "ETERNAL" not in capsys.readouterr().out
