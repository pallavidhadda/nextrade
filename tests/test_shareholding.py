from datetime import date

import pytest

from indiafacts.shareholding import (Shareholding, fetch_latest, history, parse_shp, poll, save_snapshot, shareholding_facts)

CTX = """<xbrli:context id="{id}"><xbrli:entity><xbrli:identifier scheme="s">X</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>{d}</xbrli:instant></xbrli:period>
<xbrli:scenario><xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:{m}</xbrldi:explicitMember></xbrli:scenario></xbrli:context>"""


def xml(d="2026-09-30", prom=0.52, pledged=10, pshares=100, fii=0.12, dii=0.08, sym="ABC"):
    cats = {"p": "ShareholdingOfPromoterAndPromoterGroupMember", "f": "InstitutionsForeignMember", "d": "InstitutionsDomesticMember",
            "u": "PublicShareholdingMember", "t": "ShareholdingPatternMember"}
    ctx = "".join(CTX.format(id=i, d=d, m=m) for i, m in cats.items())
    facts = (f'<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="p">{prom}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>'
             f'<in-bse-shp:NumberOfFullyPaidUpEquityShares contextRef="p">{pshares}</in-bse-shp:NumberOfFullyPaidUpEquityShares>'
             f'<in-bse-shp:NumberOfSharesEncumberedUnderPledged contextRef="p">{pledged}</in-bse-shp:NumberOfSharesEncumberedUnderPledged>'
             f'<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="f">{fii}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>'
             f'<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="d">{dii}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>'
             f'<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="u">{1 - prom}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>'
             f'<in-bse-shp:NumberOfShareholders contextRef="t">5000</in-bse-shp:NumberOfShareholders>'
             f'<in-bse-shp:Symbol contextRef="m">{sym}</in-bse-shp:Symbol><in-bse-shp:ISIN contextRef="m">INE000A01010</in-bse-shp:ISIN>'
             f'<in-bse-shp:NameOfTheCompany contextRef="m">ABC LIMITED</in-bse-shp:NameOfTheCompany>')
    return (f'<?xml version="1.0"?><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
            f'xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp/in-bse-shp">{ctx}{facts}</xbrli:xbrl>').encode()


def test_parse_reads_categories_pledge_and_date():
    sh = parse_shp(xml())
    assert sh.symbol == "ABC" and sh.as_on == date(2026, 9, 30) and sh.isin == "INE000A01010"
    assert sh.pct["promoter"] == 0.52 and sh.pct["foreign_inst"] == 0.12 and sh.pct["domestic_inst"] == 0.08
    assert sh.pledged_of_promoter == pytest.approx(0.10) and sh.shareholders == 5000


def test_parse_rejects_other_files_and_garbage():
    with pytest.raises(ValueError):
        parse_shp(b"<a/>")
    with pytest.raises(ValueError):
        parse_shp(b"not xml")


def test_store_keeps_one_row_per_date_and_builds_history(tmp_path):
    p = tmp_path / "s.csv"
    a, b = parse_shp(xml("2026-06-30", prom=0.55)), parse_shp(xml("2026-09-30", prom=0.52))
    assert save_snapshot(a, p) and save_snapshot(b, p) and not save_snapshot(b, p)
    h = history("ABC.NS", [p])
    assert [x.as_on for x in h] == [date(2026, 6, 30), date(2026, 9, 30)]


def test_facts_carry_filed_source_and_quarter_change(tmp_path):
    p = tmp_path / "s.csv"
    for d, prom in (("2026-06-30", 0.55), ("2026-09-30", 0.52)):
        save_snapshot(parse_shp(xml(d, prom=prom)), p)
    facts = {f.metric: f for f in shareholding_facts("ABC.NS", history("ABC", [p]))}
    assert float(facts["sh_promoter"].value) == 0.52 and facts["sh_promoter"].source == "nse_shp"
    assert float(facts["sh_promoter_change"].value) == pytest.approx(-0.03)
    assert float(facts["sh_promoter_pledged"].value) == pytest.approx(0.10)


class R:
    def __init__(self, b): self.b = b
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self, n=-1): return self.b


FEED = b"""<rss><channel><item><title>ABC Limited</title><link>https://nsearchives.nseindia.com/corporate/xbrl/SHP_1_2_WEB.xml</link></item></channel></rss>"""


def opener_for(url_map):
    def op(req, timeout):
        return R(url_map[req.full_url])
    return op


def test_feed_lookup_matches_by_name_and_soft_fails():
    urls = {"https://nsearchives.nseindia.com/content/RSS/Shareholding_Pattern.xml": FEED,
            "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1_2_WEB.xml": xml()}
    sh, note = fetch_latest("ABC.NS", "ABC Ltd.", opener_for(urls))
    assert sh is not None and sh.symbol == "ABC" and note == ""
    sh, note = fetch_latest("XYZ.NS", "XYZ Ltd", opener_for(urls))
    assert sh is None and "latest feed" in note
    def boom(req, timeout): raise TimeoutError()
    sh, note = fetch_latest("ABC.NS", "ABC", boom)
    assert sh is None and "could not be read" in note


def test_poll_stores_everything_in_the_feed(tmp_path):
    urls = {"https://nsearchives.nseindia.com/content/RSS/Shareholding_Pattern.xml": FEED,
            "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1_2_WEB.xml": xml()}
    assert poll(tmp_path / "s.csv", opener_for(urls)) == (1, 0)
    assert poll(tmp_path / "s.csv", opener_for(urls)) == (0, 0)


def test_ownership_view_official_beats_proxy_and_labels_change(tmp_path):
    from datetime import datetime, timezone
    from indiafacts.models import Entity, FactSet
    from indiafacts.ownership_view import ownership, ownership_lines
    p = tmp_path / "s.csv"
    for d, prom, pl in (("2026-06-30", 0.55, 10), ("2026-09-30", 0.52, 40)):
        save_snapshot(parse_shp(xml(d, prom=prom, pledged=pl)), p)
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    fs = FactSet(entity=Entity.from_ticker("ABC.NS"), facts=shareholding_facts("ABC.NS", history("ABC", [p]), now), retrieved_at=now)
    o = ownership(fs)
    assert o["source"] == "official" and o["as_on"] == "2026-09-30"
    rows = {r["metric"]: r for r in o["rows"]}
    assert rows["sh_promoter_pledged"]["reading"] == "high" and "falling" in rows["sh_promoter"]["change"]
    assert "official NSE shareholding pattern" in "\n".join(ownership_lines(fs))


def test_ownership_proxy_fallback_explains_how_to_get_the_real_one():
    from datetime import datetime, timezone
    from indiafacts.fundamentals import holding_facts
    from indiafacts.models import Entity, FactSet
    from indiafacts.ownership_view import ownership
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    fs = FactSet(entity=Entity.from_ticker("ABC.NS"), facts=holding_facts("ABC.NS", {"heldPercentInsiders": 0.5}, now), retrieved_at=now)
    o = ownership(fs)
    assert o["source"] == "proxy" and "--shareholding" in o["how_to"]


def test_pledge_and_promoter_fall_become_bear_points_only_when_official(tmp_path):
    from datetime import datetime, timezone
    from indiafacts.debate import Debate, _ownership_points
    from indiafacts.models import Entity, FactSet
    p = tmp_path / "s.csv"
    for d, prom, pl in (("2026-06-30", 0.55, 10), ("2026-09-30", 0.52, 40)):
        save_snapshot(parse_shp(xml(d, prom=prom, pledged=pl)), p)
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    fs = FactSet(entity=Entity.from_ticker("ABC.NS"), facts=shareholding_facts("ABC.NS", history("ABC", [p]), now), retrieved_at=now)
    d = Debate()
    _ownership_points(fs, d, {})
    assert len(d.bear) == 2 and not d.bull


def test_stored_official_history_is_used_by_default_from_the_repo_store(tmp_path, monkeypatch):
    """The scheduled snapshot job points INDIAFACTS_SHP_REPO at the data branch's csv; no flags are needed."""
    from indiafacts.pipeline import _ownership_facts
    from tests.test_scoring import mkfs
    repo = tmp_path / "databranch" / "shareholding.csv"
    save_snapshot(parse_shp(xml("2026-06-30", prom=0.55), source="SHP_ABC.xml"), repo)
    save_snapshot(parse_shp(xml("2026-09-30", prom=0.52), source="SHP_ABC.xml"), repo)
    monkeypatch.setenv("INDIAFACTS_SHP_REPO", str(repo))
    monkeypatch.setenv("INDIAFACTS_SHP_STORE", str(tmp_path / "empty_home.csv"))
    notices = []
    facts = _ownership_facts(mkfs("ABC.NS", {"market_cap": 1e9}), [], False, notices)
    by = {f.metric: f for f in facts}
    assert by["sh_promoter"].source == "nse_shp" and float(by["sh_promoter"].value) == pytest.approx(0.52)
    assert float(by["sh_promoter_change"].value) == pytest.approx(-0.03)
    assert _ownership_facts(mkfs("ZZZ.NS", {"market_cap": 1e9}), [], False, notices) == []


def test_filed_no_pledge_flag_reads_as_zero_pledged():
    raw = xml(pledged=10).decode()
    raw = raw.replace('<in-bse-shp:NumberOfSharesEncumberedUnderPledged contextRef="p">10</in-bse-shp:NumberOfSharesEncumberedUnderPledged>',
                      '<in-bse-shp:WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged contextRef="p">false</in-bse-shp:WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged>')
    assert parse_shp(raw).pledged_of_promoter == 0.0
