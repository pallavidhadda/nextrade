from indiafacts.summary import KEY_METRICS


def test_glance_returns_are_key_facts():
    """The web 'At a glance' tile reads the 1-year returns from key_facts: the full facts list is stripped from the
    job response the page polls, so these must stay in KEY_METRICS or the tile goes blank for every company."""
    assert "return_1y" in KEY_METRICS and "relative_return_1y" in KEY_METRICS
    assert {"price", "market_cap", "pe_ttm"} <= set(KEY_METRICS)
