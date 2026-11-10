"""Yahoo fails for the target on a live run: the report is built from NSE Market Lens (+ NSE filings), with a notice."""
import json
from pathlib import Path

import pytest

from indiafacts.cli import main
from indiafacts.models import Status
from indiafacts.pipeline import YAHOO_DOWN_NOTICE, build_factset
from indiafacts.render import render
from tests.fakes import FakeClient

FIX = Path(__file__).parent / "fixtures" / "marketlens_petroleum_products.json"
NS = dict(sleep=lambda s: None)


def _rows():
    return {r["id"]: r for r in json.loads(FIX.read_text())["data"]}


class DeadClient:
    def quarterly_income_stmt(self):
        raise ConnectionError("yahoo down")

    def info(self):
        raise ConnectionError("yahoo down")


def _by(fs):
    return {f.metric: f for f in fs.facts if f.status == Status.ok}


@pytest.mark.parametrize("how", ["dead_client", "env_switch"])
def test_ml_fallback_builds_target(monkeypatch, how):
    if how == "env_switch":
        monkeypatch.setenv("INDIAFACTS_YAHOO_DISABLED", "1")
    client = DeadClient() if how == "dead_client" else FakeClient()
    fs = build_factset("RELIANCE.NS", client=client, marketlens_rows=_rows(), prices=True, **NS)
    assert fs.yahoo_unavailable and fs.entity.resolution == "resolved"
    assert YAHOO_DOWN_NOTICE in fs.notices
    m = _by(fs)
    assert float(m["price"].value) == 1324.4 and m["price"].source == "nse_marketlens"
    assert float(m["return_1y"].value) == pytest.approx(-0.1107)
    assert float(m["return_3y"].value) == pytest.approx(0.1442) and float(m["return_5y"].value) == pytest.approx(0.0388)
    assert float(m["volatility_1y"].value) == pytest.approx(0.2942)
    assert float(m["sma_50"].value) == 1236.95 and float(m["sma_200"].value) == 1323.46
    assert float(m["pct_from_52w_high"].value) == pytest.approx(1324.4 / 1611.8 - 1)
    for k in ("market_cap", "pe_ttm", "pb", "debt_to_equity", "dividend_yield", "high_52w", "low_52w"):
        assert k in m
    assert not fs.charts and "max_drawdown_1y" not in m
    assert "RELIANCE" in render(fs)


def test_no_fallback_without_marketlens_row(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_YAHOO_DISABLED", "1")
    fs = build_factset("NOSUCHCO.NS", client=FakeClient(), marketlens_rows=_rows(), **NS)
    assert not fs.yahoo_unavailable and fs.entity.resolution != "resolved" and not fs.facts


def test_cli_exit_5_only_when_nothing(monkeypatch):
    monkeypatch.setenv("INDIAFACTS_YAHOO_DISABLED", "1")
    rc = main(["NOSUCHCO.NS", "--no-remember", "--no-tej", "--no-feed"], client=FakeClient(), sleep=lambda s: None)
    assert rc == 5
