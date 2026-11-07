import io

from indiafacts.nsefeed import parse_feed, recent_for, _CACHE

XML = """<rss version="2.0"><channel>
<item><title>Reliance Industries Limited</title><link>https://nsearchives.nseindia.com/corporate/RELIANCE_07112026184235_Result.pdf</link>
<description>Reliance has informed the Exchange about Financial Results |SUBJECT: Outcome of Board Meeting</description><pubDate>07-Nov-2026 18:42:52</pubDate></item>
<item><title>3M India Limited</title><link>https://nsearchives.nseindia.com/corporate/3MINDIALTD_07112026184235_NPADQ2.pdf</link>
<description>x |SUBJECT: Newspaper</description><pubDate>07-Nov-2026 18:40:00</pubDate></item>
</channel></rss>"""


class R(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_symbol_comes_from_the_file_name_and_matching_ignores_other_companies():
    _CACHE.clear()
    items, note = recent_for("RELIANCE.NS", opener=lambda req, timeout: R(XML.encode()))
    assert [a.symbol for a in items] == ["RELIANCE"] and items[0].subject == "Outcome of Board Meeting" and note == ""
    assert items[0].published.year == 2026


def test_no_match_and_failure_are_soft():
    _CACHE.clear()
    items, note = recent_for("TCS.NS", opener=lambda req, timeout: R(XML.encode()))
    assert items == [] and "latest feed" in note
    _CACHE.clear()
    def boom(req, timeout): raise TimeoutError()
    items, note = recent_for("TCS.NS", opener=boom)
    assert items == [] and "could not be read" in note
