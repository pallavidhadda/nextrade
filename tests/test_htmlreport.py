import re
from datetime import date

import pandas as pd
import pytest

from indiafacts.cli import main
from indiafacts.render import DISCLAIMER
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
from tests.pricefakes import FakePrices, frame
from tests.test_nsefiling import HTML as FILING_HTML

END = date(2026, 10, 23)
NSE_CSV = """Company Name,Industry,Symbol,Series,ISIN Code
Reliance Industries Ltd.,Oil Gas & Consumable Fuels,RELIANCE,EQ,INE002A01018
Peer One Ltd.,Oil Gas & Consumable Fuels,PEERA,EQ,INE000000001
Peer Two Ltd.,Oil Gas & Consumable Fuels,PEERB,EQ,INE000000002
Peer Three Ltd.,Oil Gas & Consumable Fuels,PEERC,EQ,INE000000003
Peer Four Ltd.,Oil Gas & Consumable Fuels,PEERD,EQ,INE000000004
Other Ltd.,Financial Services,OTHER,EQ,INE000000005
"""


def prices_for(symbols, n=1400):
    d = list(pd.bdate_range(end=END, periods=n).date)
    frames = {}
    for k, sym in enumerate(symbols + ["^NSEI"]):
        close, c = [], 100.0
        for i in range(n):
            c *= 1 + (0.0004 + 0.0002 * k if i % 3 else -0.0003)
            close.append(c)
        frames[sym] = frame(d, close)
    return FakePrices(frames)


SYMS = ["RELIANCE.NS", "PEERA.NS", "PEERB.NS", "PEERC.NS", "PEERD.NS", "OTHER.NS"]


def make(tmp_path, prices=True, filing=True, csv=NSE_CSV, name="report.html", extra=()):
    c = tmp_path / "ind.csv"
    c.write_text(csv, encoding="utf-8")
    f = tmp_path / "f.html"
    f.write_text(FILING_HTML, encoding="utf-8")
    out = tmp_path / "sub" / name
    argv = ["RELIANCE.NS", "--score", "--universe", str(c), "--html", str(out), "--no-tej", *extra]
    if filing:
        argv += ["--filing", str(f)]
    if not prices:
        argv += ["--no-prices"]
    info = {**INFO, "industry": "Refining"}
    code = main(argv, client=FakeClient(stmt=QUARTERLY, info=info), sleep=lambda s: None, price_client=prices_for(SYMS))
    return code, out.read_text(encoding="utf-8") if out.exists() else ""


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("HOME", str(tmp_path_factory.mktemp("home")))        # module scope: the autouse HOME isolation does not apply
    import indiafacts.tej as tej

    def offline(url):
        raise ConnectionError("offline in tests")

    mp.setattr(tej, "_http_fetch", offline)
    try:
        code, html = make(tmp_path_factory.mktemp("r"))
    finally:
        mp.undo()
    assert code == 0
    return html


def section(html, ident):
    m = re.search(rf'<section[^>]*id="{ident}".*?</section>', html, re.S)
    assert m, f"missing section {ident}"
    return m.group(0)


def test_vr14_cli_writes_file_and_creates_parent_dir(tmp_path, capsys):
    code, html = make(tmp_path)
    assert code == 0 and html.startswith("<!doctype html>")
    assert "wrote" in capsys.readouterr().out


def test_vr3_self_contained_no_network_references(report):
    assert "http" not in report and "<script src" not in report and "@import" not in report and "<link" not in report


def test_vr4_disclaimer_data_age_and_no_advice_words(report):
    assert DISCLAIMER in report and "Data as of" in report
    visible = re.sub(r"<(script|style).*?</\1>", "", report, flags=re.S)
    assert not re.search(r"\b(buy|sell)\b", visible.lower())


def test_vr5_light_and_dark_scopes_and_toggle(report):
    assert "prefers-color-scheme: dark" in report and '[data-theme="dark"]' in report and "color-scheme" in report
    assert 'id="theme-toggle"' in report


def test_vr6_price_chart_has_two_lines_legend_and_table_twin(report):
    s = section(report, "chart-price")
    assert s.count("<polyline") == 2 and 'role="img"' in s and "rebased to 100" in s
    assert "RELIANCE.NS" in s and "Nifty 50 (price index)" in s
    assert "<details" in s and "<table" in s


def test_drawdown_chart_is_a_separate_single_series(report):
    s = section(report, "chart-drawdown")
    assert "<path" in s and s.count("<polyline") == 1 and "worst fall" in s.lower()


def test_vr7_quarterly_bars_show_missing_quarter_as_no_data_slot(report):
    s = section(report, "chart-q-net_income")
    assert s.count('class="bar"') == 5                       # five quarters have data; Sep-25 does not
    assert "no data" in s and "Q2 FY26" in s
    assert "₹20,946 cr" in s                                  # latest bar labelled
    assert section(report, "chart-q-revenue")                 # revenue is its own chart (never a second axis)


def test_vr8_score_bars_and_unavailable_reason(report):
    s = section(report, "chart-scores")
    for name in ("value", "quality", "growth", "momentum", "risk", "overall"):
        assert name in s
    assert s.count('class="bar"') >= 1


def test_vr9_checklist_nine_rows_with_icon_and_text(report):
    s = section(report, "checklist")
    rows = re.findall(r'<li class="check ', s)
    assert len(rows) == 9
    assert ("✓" in s or "✗" in s) and "pass" in s


def test_vr10_peer_dot_plot_marks_target_median_and_peers(report):
    s = section(report, "chart-peers-pe_ttm")
    assert s.count('class="dot peer"') >= 3 and s.count('class="dot target"') == 1 and 'class="median"' in s
    assert "PEERA.NS" in s                                    # tooltip text names the peer


def test_vr13_marks_carry_fact_ids_that_exist_in_sources(report):
    ids = set(re.findall(r'data-fact="([0-9a-f]{16})"', report))
    assert ids
    src = section(report, "sources")
    assert all(i in src for i in ids)


def test_vr11_untrusted_names_are_escaped(tmp_path):
    evil = NSE_CSV.replace("Reliance Industries Ltd.", "<img src=x onerror=alert(1)>").replace(
        "RELIANCE,EQ", "RELIANCE,EQ").replace("Oil Gas & Consumable Fuels,RELIANCE", "<b>Oil</b>,RELIANCE")
    code, html = make(tmp_path, csv=evil, filing=False)
    assert code == 0 and "<img src=x" not in html and "&lt;img src=x" in html
    assert "<b>Oil</b>" not in html and "&lt;b&gt;Oil&lt;/b&gt;" in html


def test_vr12_no_prices_means_message_not_chart(tmp_path):
    code, html = make(tmp_path, prices=False)
    s = section(html, "chart-price")
    assert "unavailable" in s.lower() and "<polyline" not in s


def test_segment_charts_only_with_a_filing(report, tmp_path):
    s = section(report, "chart-seg-revenue")
    assert "Retail" in s and 'class="bar"' in s
    _, html = make(tmp_path, filing=False)
    assert 'id="chart-seg-revenue"' not in html


def test_page_has_title_viewport_and_stat_tiles(report):
    assert "<title>" in report and 'name="viewport"' in report and 'class="tile"' in report


def test_half_width_cards_use_a_narrower_canvas_so_text_stays_readable(report):
    for ident in ("chart-q-net_income", "chart-scores", "chart-seg-revenue"):
        assert 'viewBox="0 0 520 ' in section(report, ident), ident
    assert 'viewBox="0 0 760 ' in section(report, "chart-price")


def test_text_columns_are_left_aligned_and_numbers_right_aligned(report):
    dq = section(report, "data-quality")
    assert '<td class="">ebitda</td>' in dq or "<td>ebitda</td>" in dq
    assert not re.search(r'<td class="num">appears to be EBIT', dq)          # reason text is not right-aligned
    q = section(report, "chart-q-net_income")
    assert re.search(r'<td class="num">₹20,946 cr</td>', q)


def test_every_table_is_in_a_horizontal_scroll_wrapper_and_peer_notes_are_separated(report):
    assert report.count("<table") == report.count('<div class="tablewrap"><table')
    assert "overflow-x:auto" in report
    assert "; sector-level peers" in report or "coarse comparison" not in report
