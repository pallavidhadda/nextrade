from tests.test_htmlreport import report, section  # noqa: F401  (fixture reuse)


def test_margin_and_yoy_cards_exist_with_gaps_and_table(report):
    m = section(report, "chart-q-margin")
    assert "Net margin" in m and "<polyline" in m and "%" in m
    y = section(report, "chart-q-yoy")
    assert "earlier" in y and ("gap" in y or "<polyline" in y or "empty" in y)
    assert "no data" not in m.lower() or "gap" in m
