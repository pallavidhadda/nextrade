import os

import pandas as pd
import pytest

os.environ["INDIAFACTS_NSE_API"] = "0"            # likewise: module-scoped fixtures must never reach NSE
os.environ["INDIAFACTS_MARKETLENS"] = "0"        # set at import so module-scoped fixtures are offline too


class _NoNetworkPrices:
    def history(self, symbol):
        return pd.DataFrame()


@pytest.fixture(autouse=True)
def _offline_prices(monkeypatch, request):
    """Default price client is a stub so ordinary tests never touch the network (live tests opt out)."""
    if request.node.get_closest_marker("live"):
        return
    import indiafacts.pipeline as pipeline

    monkeypatch.setattr(pipeline, "YfinancePriceClient", _NoNetworkPrices)


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    """Never read or write the real ~/.indiafacts during tests."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@pytest.fixture(autouse=True)
def _offline_tej(monkeypatch, request):
    """TejHQ downloads are stubbed to fail in ordinary tests; tests inject their own store."""
    if request.node.get_closest_marker("live"):
        return
    import indiafacts.tej as tej

    def offline(url):
        raise ConnectionError("offline in tests")

    monkeypatch.setattr(tej, "_http_fetch", offline)


@pytest.fixture(autouse=True)
def _offline_marketlens(monkeypatch):
    """NSE Market Lens is off in ordinary tests; marketlens tests switch it on with an injected opener or rows."""
    monkeypatch.setenv("INDIAFACTS_MARKETLENS", "0")
    monkeypatch.delenv("INDIAFACTS_MARKETLENS_URL", raising=False)
    monkeypatch.delenv("INDIAFACTS_MARKETLENS_CACHE", raising=False)


@pytest.fixture(autouse=True)
def _isolated_shareholding_store(monkeypatch, tmp_path):
    """Tests never read or write the real shareholding store."""
    monkeypatch.setenv("INDIAFACTS_SHP_STORE", str(tmp_path / "shp_home.csv"))
    monkeypatch.setenv("INDIAFACTS_SHP_REPO", str(tmp_path / "shp_repo.csv"))
    monkeypatch.setenv("INDIAFACTS_FIIDII_STORE", str(tmp_path / "fiidii.csv"))


@pytest.fixture(autouse=True)
def _offline_nse_api(monkeypatch, tmp_path):
    """NSE's website API is off in ordinary tests; its tests switch it on with an injected opener and a temp cache."""
    monkeypatch.setenv("INDIAFACTS_NSE_API", "0")
    monkeypatch.setenv("INDIAFACTS_NSE_CACHE", str(tmp_path / "nse_cache"))
    monkeypatch.delenv("INDIAFACTS_NSE_BROWSER_HEADERS", raising=False)
