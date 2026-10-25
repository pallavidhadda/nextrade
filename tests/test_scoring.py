import copy
import json
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from indiafacts.models import Entity, Fact, FactSet
from indiafacts.profile import InvestorProfile, weights_for
from indiafacts.scoring import load_score_config, rank_diff, score_facts, score_universe

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
AS_OF = date(2026, 10, 26)
CFG_PATH = "indiafacts/data/score_metrics.json"

SPEC = {  # metric -> (base, step)
    "pe_ttm": (10, 2), "pb": (1, 0.2), "roe": (0.05, 0.01), "net_margin_q": (0.05, 0.01),
    "debt_to_equity": (0.2, 0.05), "net_income_yoy": (-0.1, 0.03), "revenue_yoy": (0.0, 0.02),
    "return_1y": (-0.2, 0.04), "relative_return_1y": (-0.1, 0.02), "pct_from_52w_high": (-0.4, 0.03),
    "volatility_1y": (0.15, 0.02), "max_drawdown_3y": (-0.5, 0.03), "beta_1y": (0.6, 0.05),
}


def mkfs(ticker, vals, retrieved=NOW, available_from=None):
    facts = [Fact.make(entity_key=ticker, metric=m, value=None if v is None else Decimal(str(v)), unit="ratio",
                       period_end=AS_OF, period_type="point", source="yahoo", retrieved_at=retrieved,
                       available_from=available_from, status="ok" if v is not None else "unavailable",
                       reason="" if v is not None else "missing")
             for m, v in vals.items()]
    return FactSet(entity=Entity.from_ticker(ticker), facts=facts, retrieved_at=retrieved)


def universe(n=12, **overrides):
    out = {}
    for i in range(n):
        t = f"A{i:02d}.NS"
        vals = {m: round(b + s * i, 6) for m, (b, s) in SPEC.items()}
        vals.update(overrides.get(t, {}))
        out[t] = mkfs(t, {k: v for k, v in vals.items() if v is not None or k in vals})
    return out


def profile(**o):
    return InvestorProfile(**{**dict(horizon="5y+"), **o})


@pytest.fixture(scope="module")
def cfg():
    return load_score_config(CFG_PATH, today=date(2026, 10, 26))


def run(fsets, cfg, prof=None):
    return score_universe(fsets, weights_for(prof or profile()), cfg, AS_OF, NOW)


def ranks(res):
    return {t: r.rank for t, r in res.items()}


def test_s1_shuffled_input_gives_identical_output(cfg):
    u = universe()
    items = list(u.items())
    random.Random(3).shuffle(items)
    a, b = run(u, cfg), run(dict(items), cfg)
    assert {t: r.model_dump() for t, r in a.items()} == {t: r.model_dump() for t, r in b.items()}


def test_s2_config_hash_changes_with_weights_and_metrics(cfg, tmp_path):
    u = universe()
    h1 = run(u, cfg, profile(horizon="5y+"))["A00.NS"].config_hash
    assert h1 == run(u, cfg, profile(horizon="5y+"))["A00.NS"].config_hash
    assert h1 != run(u, cfg, profile(horizon="<1y"))["A00.NS"].config_hash
    data = json.load(open(CFG_PATH))
    data["metrics"][0]["valid_max"] = 60
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    assert h1 != run(u, load_score_config(p, today=AS_OF))["A00.NS"].config_hash


def test_s3_bad_config_rejected(tmp_path):
    base = json.load(open(CFG_PATH))
    for mutate in (lambda d: d["metrics"][0].update(direction="sideways"),
                   lambda d: d["metrics"][0].update(valid_min=80),
                   lambda d: d["metrics"][0].pop("factor")):
        d = copy.deepcopy(base)
        mutate(d)
        p = tmp_path / "c.json"
        p.write_text(json.dumps(d))
        with pytest.raises(ValueError):
            load_score_config(p, today=AS_OF)
    d = copy.deepcopy(base)
    d["review_by"] = "2026-01-01"
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="review"):
        load_score_config(p, today=AS_OF)
    assert load_score_config(p, today=AS_OF, strict=False).overdue


def test_s4_raising_a_higher_is_better_metric_never_lowers_that_names_score(cfg):
    base = run(universe(), cfg)["A05.NS"].factors["quality"].score
    better = run(universe(**{"A05.NS": {"roe": 0.30}}), cfg)["A05.NS"].factors["quality"].score
    assert better >= base


def test_s5_negative_pe_is_not_scored_as_cheap(cfg):
    r = run(universe(**{"A03.NS": {"pe_ttm": -10}}), cfg)["A03.NS"]
    assert any("pe_ttm" in f and "outside valid range" in f for f in r.flags)
    assert "pe_ttm" not in r.metric_scores
    assert r.factors["value"].score is None and "coverage" in r.factors["value"].reason
    assert r.status == "ok"                                              # other factors still score it


def test_s6_pe_above_cap_excluded_but_name_stays(cfg):
    base = run(universe(), cfg)
    r = run(universe(**{"A11.NS": {"pe_ttm": 200}}), cfg)
    assert r["A11.NS"].status == "ok" and "pe_ttm" not in r["A11.NS"].metric_scores
    assert any("pe_ttm" in f for f in r["A11.NS"].flags)


def test_s7_unit_error_flagged_and_other_names_keep_their_order(cfg):
    base = run(universe(), cfg)
    bad = run(universe(**{"A05.NS": {"roe": 18}}), cfg)
    assert any("roe" in f and "outside valid range" in f for f in bad["A05.NS"].flags)
    order = lambda res: [t for t, _ in sorted(((t, r.rank) for t, r in res.items() if t != "A05.NS"), key=lambda x: x[1])]
    assert order(base) == order(bad)


def test_s8_missing_value_is_not_zero_and_changes_only_coverage(cfg):
    base = run(universe(), cfg)
    r = run(universe(**{"A05.NS": {"roe": None}}), cfg)["A05.NS"]
    assert r.factors["quality"].coverage == pytest.approx(2 / 3, abs=1e-3) and r.factors["quality"].score is not None
    assert r.factors["growth"].score == base["A05.NS"].factors["growth"].score
    assert "roe" not in r.metric_scores


def test_s9_low_coverage_gives_unavailable_with_reason(cfg):
    r = run(universe(**{"A05.NS": {"roe": None, "net_margin_q": None}}), cfg)["A05.NS"]
    assert r.factors["quality"].score is None and "coverage" in r.factors["quality"].reason


def test_s10_fewer_than_two_valid_factors_abstains(cfg):
    only_value = {m: None for m in SPEC if m not in ("pe_ttm", "pb")}
    r = run(universe(**{"A05.NS": only_value}), cfg)["A05.NS"]
    assert r.status == "abstain" and r.overall is None and "fewer than 2 valid factors" in r.reason and r.rank is None


def test_s11_absurd_outliers_do_not_reshuffle_the_rest(cfg):
    base = run(universe(), cfg)
    extra = universe(14, **{"A12.NS": {"pe_ttm": 10000}, "A13.NS": {"return_1y": 9.9}})
    res = run(extra, cfg)
    assert any("pe_ttm" in f for f in res["A12.NS"].flags)
    for t in base:
        assert abs(base[t].rank - res[t].rank) <= 2          # two extra names can displace by at most their count


def test_s12_stale_facts_are_excluded_and_flagged(cfg):
    u = universe()
    old = NOW - timedelta(days=30)
    u["A05.NS"] = mkfs("A05.NS", {m: round(b + s * 5, 6) for m, (b, s) in SPEC.items()}, retrieved=old)
    r = run(u, cfg)["A05.NS"]
    assert r.status == "abstain" and any("stale" in f for f in r.flags)


def test_s15_rank_diff_reports_what_moved(cfg):
    base = run(universe(), cfg)
    corrupt = run(universe(**{"A02.NS": {"roe": 1.4, "return_1y": 9.0, "net_income_yoy": 9.0}}), cfg)
    diff = rank_diff(base, corrupt)
    assert diff and diff[0].ticker == "A02.NS" and diff[0].delta != 0
    assert all(abs(d.delta) <= abs(diff[0].delta) for d in diff)


def test_s16_provenance_on_every_score_fact(cfg):
    u = universe(**{"A05.NS": {"roe": None, "net_margin_q": None}})
    res = run(u, cfg)
    facts = score_facts(res["A05.NS"], u["A05.NS"].facts[0].retrieved_at)
    assert facts
    for f in facts:
        assert f.source == "computed" and "scorecard:config=" in f.source_field
        if f.status == "ok":
            assert f.related_fact_ids
        else:
            assert f.reason


def test_s17_ties_break_alphabetically(cfg):
    u = universe()
    u["B00.NS"] = mkfs("B00.NS", {m: round(b + s * 5, 6) for m, (b, s) in SPEC.items()})   # same numbers as A05
    res = run(u, cfg)
    assert res["A05.NS"].overall == res["B00.NS"].overall and res["A05.NS"].rank < res["B00.NS"].rank


def test_s19_not_yet_public_facts_excluded(cfg):
    u = universe()
    u["A05.NS"] = mkfs("A05.NS", {m: round(b + s * 5, 6) for m, (b, s) in SPEC.items()},
                       available_from=AS_OF + timedelta(days=10))
    r = run(u, cfg)["A05.NS"]
    assert r.status == "abstain" and any("not yet public" in f for f in r.flags)


def test_s20_golden_percentiles(tmp_path):
    d = {"review_by": "2027-01-01", "reviewed_on": "2026-10-26",
         "params": {"winsorise_low": 0.05, "winsorise_high": 0.95, "winsorise_min_n": 10, "min_universe": 5,
                    "min_factor_coverage": 0.6, "min_valid_factors": 1, "max_age_days": 7},
         "metrics": [{"id": "pb", "factor": "value", "direction": "lower", "valid_min": 0, "valid_max": 50}]}
    p = tmp_path / "g.json"
    p.write_text(json.dumps(d))
    g = load_score_config(p, today=AS_OF)
    fsets = {f"G{i}.NS": mkfs(f"G{i}.NS", {"pb": float(i + 1)}) for i in range(5)}
    res = score_universe(fsets, {"value": 1.0}, g, AS_OF, NOW)
    assert [float(res[f"G{i}.NS"].metric_scores["pb"]) for i in range(5)] == [100.0, 75.0, 50.0, 25.0, 0.0]
    assert res["G0.NS"].overall == 100.0 and res["G0.NS"].rank == 1 and res["G4.NS"].rank == 5
