from datetime import date, timedelta

import pandas as pd
import pytest

from indiafacts.cli import main
from indiafacts.pipeline import build_factset
from indiafacts.render import DISCLAIMER, render
from indiafacts.securitymaster import corporate_action_dates, load_curated
from tests.fakes import FakeClient
from tests.pricefakes import FakePrices, frame

END = date(2026, 10, 23)
NS = dict(sleep=lambda s: None)


def long_pair(symbol="RELIANCE.NS", n=400):
    d = list(pd.bdate_range(end=END, periods=n).date)
    r = [0.004 if i % 2 else -0.002 for i in range(n - 1)]
    b, s = [100.0], [100.0]
    for x in r:
        b.append(b[-1] * (1 + x))
        s.append(s[-1] * (1 + 1.5 * x))
    return FakePrices({symbol: frame(d, s), "^NSEI": frame(d, b)})


def facts_of(fs, metric):
    return [f for f in fs.facts if f.metric == metric]


def test_prices_added_with_provenance_and_rendered():
    fs = build_factset("RELIANCE.NS", as_of=END, client=FakeClient(), prices=True, price_client=long_pair(), **NS)
    r1 = facts_of(fs, "return_1y")[0]
    assert r1.status == "ok" and "series:" in r1.source_field and "basis:split_adjusted_close" in r1.source_field
    out = render(fs, as_of=END)
    assert "PRICE HISTORY" in out and "split-adjusted" in out and "Nifty 50 price index" in out and DISCLAIMER in out
    assert "relative_return_1y" not in out.split("PRICE HISTORY")[0]          # not in other sections
    assert "return_1y" not in out.split("COMPUTED CHECKS")[1].split("\n\n")[0] if "COMPUTED CHECKS" in out else True


def test_benchmark_failure_keeps_stock_metrics_and_says_why():
    pc = long_pair()
    pc.frames.pop("^NSEI")
    fs = build_factset("RELIANCE.NS", as_of=END, client=FakeClient(), prices=True, price_client=pc, **NS)
    assert facts_of(fs, "return_1y")[0].status == "ok"
    assert facts_of(fs, "relative_return_1y")[0].status == "unavailable"
    assert "benchmark unavailable" in facts_of(fs, "relative_return_1y")[0].reason


def test_price_fetch_exception_does_not_crash_and_is_noticed():
    class Boom:
        def history(self, symbol):
            raise ConnectionError("down")

    fs = build_factset("RELIANCE.NS", client=FakeClient(), prices=True, price_client=Boom(), **NS)
    assert any("price history unavailable" in n for n in fs.notices)
    assert facts_of(fs, "net_income")                                  # rest of the report intact


def test_prices_off_means_no_price_client_calls():
    pc = long_pair()
    fs = build_factset("RELIANCE.NS", client=FakeClient(), prices=False, price_client=pc, **NS)
    assert pc.calls == [] and not facts_of(fs, "return_1y")


def test_cli_no_prices_flag(capsys):
    code = main(["RELIANCE.NS", "--no-prices"], client=FakeClient(), sleep=lambda s: None)
    assert code == 0 and "PRICE HISTORY" not in capsys.readouterr().out


def test_cli_prices_on_by_default_with_injected_client(capsys):
    code = main(["RELIANCE.NS"], client=FakeClient(), sleep=lambda s: None, price_client=long_pair())
    assert code == 0 and "PRICE HISTORY" in capsys.readouterr().out


def test_demerger_date_flags_windows_unverified():
    assert date(2025, 10, 1) in corporate_action_dates("TMPV.NS", load_curated())
    assert date(2025, 10, 1) in corporate_action_dates("tmcv", load_curated())
    assert corporate_action_dates("RELIANCE.NS", load_curated()) == []
    fs = build_factset("TMPV.NS", as_of=END, client=FakeClient(), prices=True,
                       price_client=long_pair("TMPV.NS", n=1000), **NS)
    r3 = facts_of(fs, "return_3y")[0]
    assert r3.status == "unverified" and "2025-10-01" in r3.reason       # 3y window spans the demerger
    assert facts_of(fs, "return_1y")[0].status == "ok"                    # 1y window starts after it


@pytest.mark.live
def test_live_prices_reliance_and_nifty():
    from indiafacts.prices import YfinancePriceClient, load_series

    c = YfinancePriceClient()
    stock, bench = load_series("RELIANCE.NS", c), load_series("^NSEI", c)
    assert len(stock.dates) > 5000 and len(bench.dates) > 4000
    assert (date.today() - stock.dates[-1]).days <= 7
