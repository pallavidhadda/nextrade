from datetime import datetime, timedelta, timezone

from indiafacts.companies import aliases_for
from indiafacts.news import event_type, fetch_news, mentions_company
from indiafacts.nsefeed import Announcement, parse_feed

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
TS = int((NOW - timedelta(days=1)).timestamp())


class Fake:
    def __init__(self, rows):
        self.rows = rows

    def news(self, symbol):
        return self.rows


def row(t):
    return {"title": t, "publisher": "P", "providerPublishTime": TS}


def test_aliases_come_from_company_data():
    a = aliases_for("RELIANCE.NS")
    assert "reliance" in a and "reliance industries" in a and "jio" in a
    assert "m and m" in aliases_for("M&M.NS")


def test_title_must_name_the_company_and_drops_are_counted():
    rows = [row("Reliance Industries Q2 profit rises"), row("Sensex jumps 500 points"), row("Nifty ends flat, Tata Steel leads")]
    items, note = fetch_news("RELIANCE.NS", Fake(rows), now=NOW)
    assert [i.title for i in items] == ["Reliance Industries Q2 profit rises"]
    assert "2 third-party headline(s) dropped" in note
    assert not mentions_company("Relianceville council meets", "RELIANCE.NS")


def test_event_type_keyword_guess():
    assert event_type("Reliance Q2 results: net profit up") == "results"
    assert event_type("Board approves dividend of Rs 10") == "dividend/corporate action"
    assert event_type("Company bags large order") == "order/contract"
    assert event_type("SEBI issues notice") == "regulatory"
    assert event_type("CFO resigns") == "management"
    assert event_type("Crisil reaffirms rating") == "rating"
    assert event_type("Annual general meeting held") == "other"


def test_nse_announcements_lead_with_category():
    ann = Announcement("Reliance", "RELIANCE", "Outcome of Board Meeting", "d", "https://nsearchives.nseindia.com/x.pdf",
                       datetime(2026, 11, 1, 18, 0), "Financial Results")
    items, _ = fetch_news("RELIANCE.NS", Fake([row("Reliance shares jump on order win")]), now=NOW, nse=lambda s: ([ann], ""))
    assert items[0].source_kind == "exchange" and items[0].category == "Financial Results" and items[0].publisher == "NSE"
    assert items[1].source_kind == "media" and items[1].event_type == "order/contract"


def test_feed_category_is_parsed():
    xml = ('<rss><channel><item><title>Reliance</title><link>https://nsearchives.nseindia.com/corporate/RELIANCE_07112026184235_x.pdf</link>'
           '<description>Reliance has informed the Exchange about Financial Results |SUBJECT: Outcome</description>'
           '<pubDate>07-Nov-2026 18:42:52</pubDate></item></channel></rss>')
    assert parse_feed(xml)[0].category == "Financial Results"
