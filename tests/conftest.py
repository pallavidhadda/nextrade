import pandas as pd
import pytest


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
