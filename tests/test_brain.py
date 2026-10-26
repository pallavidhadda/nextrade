from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from indiafacts.brain import Brain
from indiafacts.models import Entity, FactSet
from tests.factories import fact

T0 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
T1 = T0 + timedelta(days=7)
Q = date(2026, 6, 30)


def fs(*facts, ticker="RELIANCE.NS"):
    return FactSet(entity=Entity.from_ticker(ticker), facts=list(facts), retrieved_at=T0)


def rep(value, source="nse_filing", avail="2026-07-17", period=Q, metric="net_income", status="ok", reason="", **o):
    return fact(period, metric=metric, value=value, source=source, status=status, reason=reason,
                evidence=f"{source} row", available_from=date.fromisoformat(avail), **o)


@pytest.fixture
def brain(tmp_path):
    return Brain(tmp_path / "brain.db")


def test_br1_identical_runs_dedupe_observations_but_keep_both_runs(brain):
    a = fs(rep("100"), rep("5", metric="revenue"))
    r1, r2 = brain.record_run(a, None, None, T0), brain.record_run(a, None, None, T1)
    assert r2 > r1 and brain.stats() == {"runs": 2, "observations": 2}


def test_br2_changed_value_keeps_both_versions_with_dates(brain):
    old, new = rep("100", avail="2026-07-17"), rep("90", avail="2026-09-05")
    brain.record_run(fs(old), None, None, T0)
    brain.record_run(fs(new), None, None, T1)
    v = brain.versions(old.fact_id)
    assert [str(x.value) for x in v] == ["100", "90"] and [x.available_from for x in v] == ["2026-07-17", "2026-09-05"]


def test_br3_possible_restatement_cites_both_filing_dates_and_values(brain):
    brain.record_run(fs(rep("100", avail="2026-07-17")), None, None, T0)
    brain.record_run(fs(rep("90", avail="2026-09-05")), None, None, T1)
    ch = [c for c in brain.changes("RELIANCE.NS") if c.kind == "possible_restatement"]
    assert len(ch) == 1 and ch[0].severity == "attention"
    assert "100" in ch[0].text and "90" in ch[0].text and "2026-07-17" in ch[0].text and "2026-09-05" in ch[0].text


def test_br4_vendor_revision_is_not_called_a_restatement(brain):
    brain.record_run(fs(rep("100", source="yahoo")), None, None, T0)
    brain.record_run(fs(rep("101", source="yahoo")), None, None, T1)
    kinds = {c.kind for c in brain.changes("RELIANCE.NS")}
    assert "vendor_revision" in kinds and "possible_restatement" not in kinds


def test_br5_gap_closed_gap_opened_status_changed_and_new_figure(brain):
    gap = fact(date(2025, 9, 30), metric="net_income", value=None, status="gap", reason="not returned", source="yahoo")
    brain.record_run(fs(rep("100", source="yahoo"), gap), None, None, T0)
    filled = fact(date(2025, 9, 30), metric="net_income", value="80", source="yahoo", evidence="e")
    newq = rep("110", source="yahoo", period=date(2026, 9, 30), avail="2026-11-10")
    degraded = rep("100", source="yahoo", status="unverified", reason="ebit")
    brain.record_run(fs(degraded, filled, newq), None, None, T1)
    kinds = {c.kind for c in brain.changes("RELIANCE.NS")}
    assert {"gap_closed", "new_figure", "status_changed"} <= kinds


def test_br6_checklist_flip_rank_move_and_score_change(brain):
    from types import SimpleNamespace as NS

    def sc(rank, overall, check):
        return {"result": NS(status="ok", rank=rank, overall=overall, config_hash="c", factors={}), "n": 30,
                "checklist": [NS(id="earnings_growing", result=check, value=0.1)]}

    brain.record_run(fs(rep("1")), sc(24, 45.0, "fail"), None, T0)
    brain.record_run(fs(rep("1")), sc(20, 49.0, "pass"), None, T1)
    kinds = {c.kind: c.text for c in brain.changes("RELIANCE.NS")}
    assert "checklist_flip" in kinds and "fail" in kinds["checklist_flip"] and "pass" in kinds["checklist_flip"]
    assert "rank_moved" in kinds and "24" in kinds["rank_moved"] and "20" in kinds["rank_moved"]
    assert "score_changed" in kinds


def test_br7_market_moves_listed_only_when_material_the_rest_counted(brain):
    def mk(ret, pe):
        a = fact(date(2026, 10, 25), metric="return_1y", value=ret, period_type="point", source="computed",
                 evidence="", source_field="series:abc|window:1y")
        b = fact(date(2026, 10, 25), metric="pe_ttm", value=pe, period_type="point", source="yahoo", evidence="e")
        return fs(a, b)

    brain.record_run(mk("-0.178", "21.5"), None, None, T0)
    brain.record_run(mk("-0.175", "21.6"), None, None, T1)            # small
    first = brain.changes("RELIANCE.NS")
    assert not [c for c in first if c.kind == "market_move"] and any("small market" in c.text for c in first)
    brain.record_run(mk("-0.120", "21.6"), None, None, T1 + timedelta(days=7))   # 5.5 points
    assert any(c.kind == "market_move" and "return_1y" in c.text for c in brain.changes("RELIANCE.NS"))


def test_br8_first_run_has_no_changes_and_previous_is_per_ticker(brain):
    brain.record_run(fs(rep("1")), None, None, T0)
    assert brain.changes("RELIANCE.NS") == []
    brain.record_run(fs(rep("2", source="yahoo"), ticker="TCS.NS"), None, None, T1)
    assert brain.changes("RELIANCE.NS") == []                         # TCS runs do not count as RELIANCE history
    assert brain.changes("TCS.NS") == []


def test_br9_computed_facts_alone_are_never_reported(brain):
    a = fact(Q, metric="net_income_yoy", value="0.1", source="computed", evidence="")
    b = fact(Q, metric="net_income_yoy", value="0.2", source="computed", evidence="")
    brain.record_run(fs(a), None, None, T0)
    brain.record_run(fs(b), None, None, T1)
    assert brain.changes("RELIANCE.NS") == []


def test_br10_storage_failure_is_reported_not_raised(tmp_path):
    bad = tmp_path / "dir_instead_of_file"
    bad.mkdir()
    b = Brain(bad)
    assert b.safe_record_run(fs(rep("1")), None, None, T0) is None and b.last_error


# ---- CLI, terminal and HTML wiring ---------------------------------------------------------------
import re

from indiafacts.cli import main
from tests.fakes import FakeClient
from tests.fixtures.reliance_quarterly import INFO, QUARTERLY


def run_cli(tmp_path, capsys, *extra, qtr=None, brain=None, html=None):
    stmt = QUARTERLY.copy()
    if qtr is not None:
        stmt.loc["Net Income Common Stockholders", stmt.columns[1]] = qtr          # Mar-26 quarter restated by the vendor
    argv = ["RELIANCE.NS", "--no-prices", "--no-tej", *extra]
    if html:
        argv += ["--html", str(html)]
    code = main(argv, client=FakeClient(stmt=stmt, info=INFO), sleep=lambda s: None, brain=brain)
    o = capsys.readouterr()
    return code, o.out, o.err


def test_br11_second_run_prints_what_changed_and_the_db_lives_under_home(tmp_path, capsys):
    run_cli(tmp_path, capsys)
    code, out, _ = run_cli(tmp_path, capsys, qtr=170000000000.0)
    assert code == 0 and "WHAT CHANGED SINCE" in out and "vendor_revision" in out.replace(" ", "_") or "changed at yahoo" in out
    from pathlib import Path
    assert (Path.home() / ".indiafacts" / "brain.db").exists()


def test_br12_changes_flag_explains_a_first_run_and_no_remember_leaves_no_db(tmp_path, capsys):
    from pathlib import Path

    code, out, _ = run_cli(tmp_path, capsys, "--changes", "--no-remember")
    assert code == 0 and "nothing to compare" in out and not (Path.home() / ".indiafacts" / "brain.db").exists()
    code, out, _ = run_cli(tmp_path, capsys, "--changes")
    assert "first run" in out


def test_br13_storage_failure_is_a_notice_and_the_report_still_prints(tmp_path, capsys):
    bad = tmp_path / "blocked"
    bad.mkdir()
    code, out, _ = run_cli(tmp_path, capsys, brain=Brain(bad))
    assert code == 0 and "could not save the snapshot" in out and "RELIANCE.NS" in out


def test_br14_html_gets_a_changes_card_with_escaped_text(tmp_path, capsys):
    run_cli(tmp_path, capsys)
    page = tmp_path / "r.html"
    run_cli(tmp_path, capsys, qtr=170000000000.0, html=page)
    s = re.search(r'<section[^>]*id="changes".*?</section>', page.read_text(encoding="utf-8"), re.S)
    assert s and "Mar" not in s.group(0) or "changed at yahoo" in s.group(0)
    assert "<script" not in s.group(0)
