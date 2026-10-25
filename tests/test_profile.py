import itertools
import json
import re
from datetime import date

import pytest

from indiafacts.cli import main
from indiafacts.pipeline import build_factset
from indiafacts.profile import (InvestorProfile, ProfileError, default_profile, eval_horizon_days, load_presets,
                                load_profile, save_profile, weights_for)
from indiafacts.render import DISCLAIMER, render
from tests.fakes import FakeClient

LEVELS = ["low", "medium", "high"]


def prof(**over):
    base = dict(goal="growth", horizon="5y+", risk_tolerance="medium", risk_capacity="medium",
                max_single_stock_pct=10, liquidity_need="can_lock_away", experience="beginner")
    base.update(over)
    return InvestorProfile(**base)


@pytest.mark.parametrize("tol,cap", list(itertools.product(LEVELS, LEVELS)))
def test_effective_risk_is_the_lower_of_tolerance_and_capacity(tol, cap):
    assert prof(risk_tolerance=tol, risk_capacity=cap).effective_risk == min(tol, cap, key=LEVELS.index)


def test_invalid_values_rejected():
    for bad in (dict(horizon="forever"), dict(risk_tolerance="extreme"), dict(max_single_stock_pct=0),
                dict(max_single_stock_pct=150), dict(experience="guru"), dict(goal="lottery")):
        with pytest.raises(ValueError):
            prof(**bad)


def test_presets_sum_to_one_and_cover_every_horizon():
    p = load_presets(today=date(2026, 10, 26))
    assert set(p) == {"<1y", "1-3y", "3-5y", "5y+"}
    for h, w in p.items():
        assert sum(w.values()) == pytest.approx(1.0) and set(w) == {"value", "quality", "growth", "momentum", "risk"}


def test_bad_presets_rejected(tmp_path):
    data = json.loads(open("indiafacts/data/weight_presets.json").read())
    data["presets"]["5y+"]["value"] = 0.9
    p = tmp_path / "w.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="sum"):
        load_presets(p, today=date(2026, 10, 26))
    data["presets"]["5y+"]["value"] = 0.25
    data["review_by"] = "2026-01-01"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="review"):
        load_presets(p, today=date(2026, 10, 26))


def test_horizon_to_eval_days():
    assert [eval_horizon_days(prof(horizon=h)) for h in ("<1y", "1-3y", "3-5y", "5y+")] == [63, 504, 1008, 1260]


def test_hash_changes_with_any_field_and_is_stable():
    base = prof()
    assert base.profile_hash == prof().profile_hash
    for over in (dict(goal="income"), dict(horizon="1-3y"), dict(risk_tolerance="high"), dict(risk_capacity="low"),
                 dict(max_single_stock_pct=20), dict(liquidity_need="may_need_within_1y"), dict(experience="expert")):
        assert prof(**over).profile_hash != base.profile_hash


def test_view_follows_experience_and_override():
    assert prof(experience="beginner").view == "simple" and prof(experience="expert").view == "pro"


def test_save_load_roundtrip_and_corrupt_file(tmp_path):
    p = tmp_path / "profile.json"
    save_profile(prof(horizon="3-5y"), p)
    assert load_profile(p) == prof(horizon="3-5y")
    p.write_text("{not json")
    with pytest.raises(ProfileError, match="profile"):
        load_profile(p)
    p.write_text(json.dumps({"horizon": "forever"}))
    with pytest.raises(ProfileError):
        load_profile(p)


def test_different_horizons_change_weights_not_facts():
    a = build_factset("RELIANCE.NS", client=FakeClient(), sleep=lambda s: None)
    b = build_factset("RELIANCE.NS", client=FakeClient(), sleep=lambda s: None)
    assert [f.fact_id for f in a.facts] == [f.fact_id for f in b.facts]
    assert weights_for(prof(horizon="5y+")) != weights_for(prof(horizon="<1y"))


def run(capsys, *argv, home=None):
    code = main(list(argv), client=FakeClient(), sleep=lambda s: None)
    return code, capsys.readouterr().out


def test_missing_profile_uses_labelled_default(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    code, out = run(capsys, "RELIANCE.NS", "--no-prices")
    assert code == 0 and "default profile" in out.lower() and "not set by you" in out


def test_profile_line_shows_hash_and_fit_text_is_not_advice(capsys, tmp_path):
    p = tmp_path / "p.json"
    save_profile(prof(horizon="1-3y", risk_tolerance="high", risk_capacity="low"), p)
    code, out = run(capsys, "RELIANCE.NS", "--no-prices", "--profile", str(p))
    h = prof(horizon="1-3y", risk_tolerance="high", risk_capacity="low").profile_hash
    assert h in out and "effective risk low" in out and "1-3y" in out
    assert DISCLAIMER in out and not re.search(r"\b(buy|sell)\b", out.lower())


def test_cli_creates_and_saves_profile_and_view_override(capsys, tmp_path):
    p = tmp_path / "new.json"
    code, out = run(capsys, "RELIANCE.NS", "--no-prices", "--profile", str(p), "--horizon", "3-5y",
                    "--experience", "expert", "--save-profile")
    assert code == 0 and load_profile(p).horizon == "3-5y" and "view pro" in out
    code, out = run(capsys, "RELIANCE.NS", "--no-prices", "--profile", str(p), "--view", "simple")
    assert "view simple" in out


def test_simple_view_hides_pro_only_rows(capsys, tmp_path):
    p = tmp_path / "p.json"
    save_profile(prof(experience="beginner"), p)
    from tests.test_nsefiling import HTML

    f = tmp_path / "f.html"
    f.write_text(HTML, encoding="utf-8")
    _, simple = run(capsys, "RELIANCE.NS", "--no-prices", "--profile", str(p), "--filing", str(f))
    _, pro = run(capsys, "RELIANCE.NS", "--no-prices", "--profile", str(p), "--filing", str(f), "--view", "pro")
    assert "segment_revenue_retail" in pro and "segment_revenue_retail" not in simple.split("SOURCES")[0]
