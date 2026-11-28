"""Currency guard on Yahoo annual figures, and symbol matching when NSE filings carry old and new symbols."""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from indiafacts.fundamentals import ROWS, annual_facts
from indiafacts.models import Status
from indiafacts.nsefiling import _company_key, merge_filings
from indiafacts.pipeline import _symbol_canonicalizer


def _statements(col="2026-03-31"):
    frames: dict[str, pd.DataFrame] = {}
    for _metric, (st_name, names) in ROWS.items():
        df = frames.setdefault(st_name, pd.DataFrame(columns=[pd.Timestamp(col)], dtype=float))
        df.loc[names[0], pd.Timestamp(col)] = 1000.0
    return frames


def test_usd_annual_figures_are_unverified_not_ok():
    facts = annual_facts("INFY.NS", _statements(), reported_ccy="USD")
    valued = [f for f in facts if f.value is not None]
    assert valued, "expected some figures from the synthetic statements"
    assert all(f.status == Status.unverified for f in valued)
    assert all("reported in USD, not INR; not converted" in f.reason for f in valued)


def test_inr_annual_figures_stay_ok():
    facts = annual_facts("INFY.NS", _statements(), reported_ccy="INR")
    valued = [f for f in facts if f.value is not None]
    assert valued and all(f.status == Status.ok for f in valued)


def test_missing_currency_is_not_treated_as_usd():
    facts = annual_facts("INFY.NS", _statements(), reported_ccy=None)
    valued = [f for f in facts if f.value is not None]
    assert valued and all(f.status == Status.ok for f in valued)


def test_company_key_ignores_punctuation_only():
    assert _company_key("BAJAJ-AUTO") == _company_key("BAJAJAUTO") == "BAJAJAUTO"
    assert _company_key("ETERNAL") != _company_key("ZOMATO")


def _filing(symbol):
    return SimpleNamespace(entity=SimpleNamespace(nse_symbol=SimpleNamespace(value=symbol)))


def test_merge_refuses_different_companies_without_a_rename_map():
    with pytest.raises(ValueError, match="filings are for different companies"):
        merge_filings([_filing("ZOMATO"), _filing("ETERNAL")])


def test_merge_does_not_refuse_when_canonical_symbol_collapses_a_rename():
    canon = {"ZOMATO": "ETERNAL", "ETERNAL": "ETERNAL"}.get
    try:
        merge_filings([_filing("ZOMATO"), _filing("ETERNAL")], canonical=canon)
    except ValueError as exc:
        assert "different companies" not in str(exc)
    except Exception:
        pass  # the fake filings have no figures; only the symbol check is under test


def test_merge_still_refuses_when_canonical_symbols_differ():
    canon = {"TATAMOTORS": "TATAMOTORS", "TMPV": "TMPV"}.get
    with pytest.raises(ValueError, match="filings are for different companies"):
        merge_filings([_filing("TATAMOTORS"), _filing("TMPV")], canonical=canon)


def test_canonicalizer_is_none_without_a_rename_list(tmp_path: Path):
    assert _symbol_canonicalizer(tmp_path / "missing.csv") is None


def test_nse_archive_on_either_host_is_downloaded(tmp_path, monkeypatch):
    from indiafacts import nseapi

    monkeypatch.setattr(nseapi, "enabled", lambda: True)
    monkeypatch.setattr(nseapi, "live_enabled", lambda: True)
    api = nseapi.NseApi(cache=tmp_path)
    monkeypatch.setattr(api, "_request", lambda url, accept: (b"<?xml version='1.0'?><x/>", ""))
    for url in ("https://nsearchives.nseindia.in/corporate/xbrl/A_WEB.xml",
                "https://nsearchives.nseindia.com/corporate/xbrl/A_WEB.xml"):
        path, why = api.get_file(url)
        assert path is not None and why == "", url
    assert api.reasons == []


def test_foreign_archive_host_is_refused_and_recorded(tmp_path, monkeypatch):
    from indiafacts import nseapi

    monkeypatch.setattr(nseapi, "enabled", lambda: True)
    monkeypatch.setattr(nseapi, "live_enabled", lambda: True)
    api = nseapi.NseApi(cache=tmp_path)
    path, why = api.get_file("https://example.org/A_WEB.xml")
    assert path is None and "not an NSE archive URL" in why
    assert api.reasons and "example.org" in api.reasons[-1]


def test_punctuation_match_does_not_apply_a_rename():
    # NSE's list maps BAJAJAUTO -> BAJAJHLDNG (a different company). Bajaj Auto's own filings use both spellings of BAJAJ-AUTO;
    # they must still merge, so the rename must not be applied when the punctuation-free symbols already agree.
    canon = {"BAJAJAUTO": "BAJAJHLDNG"}.get
    try:
        merge_filings([_filing("BAJAJ-AUTO"), _filing("BAJAJAUTO")], canonical=canon)
    except ValueError as exc:
        assert "different companies" not in str(exc)
    except Exception:
        pass


def test_download_symbol_changes_rejects_non_csv_and_falls_through(tmp_path, monkeypatch):
    from indiafacts import securitymaster

    calls = []

    class FakeResp:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return self.body

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        if "nseindia.com" in req.full_url:
            return FakeResp(b"<html>blocked</html>")
        return FakeResp(b"NAME OF THE COMPANY,OLD SYMBOL,NEW SYMBOL,EFFECTIVE DATE\nZOMATO LTD,ZOMATO,ETERNAL,09-APR-2025\n")

    monkeypatch.setattr(securitymaster.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "symbolchange.csv"
    assert securitymaster.download_symbol_changes(dest) == dest and dest.exists()
    assert len(calls) == 2 and "nsearchives.nseindia.in" in calls[1]


def test_rename_list_format_resolves_renames_and_demergers(tmp_path: Path):
    # Same columns and date format as NSE's public symbolchange.csv; a few rows only.
    from indiafacts.securitymaster import load_curated, load_symbol_changes, resolve_symbol

    csv_path = tmp_path / "symbolchange.csv"
    csv_path.write_text("NAME OF THE COMPANY,OLD SYMBOL,NEW SYMBOL,EFFECTIVE DATE\n"
                        "ZOMATO LTD,ZOMATO,ETERNAL,09-APR-2025\n"
                        "L&T TECHNOLOGY,LTIM,LTM,09-NOV-2023\n", encoding="utf-8")
    ch = load_symbol_changes(csv_path)
    cu = load_curated(strict=False)
    assert resolve_symbol("ZOMATO", ch, cu).symbols == ["ETERNAL"]
    assert resolve_symbol("LTIM", ch, cu).symbols == ["LTM"]
    assert resolve_symbol("TATAMOTORS", ch, cu).kind == "split"
