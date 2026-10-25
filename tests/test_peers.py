import json
import random
from datetime import date
from decimal import Decimal

import pytest

from indiafacts.models import Entity
from indiafacts.peers import compare_peers, load_peer_params, select_peers
from tests.test_scoring import mkfs

TODAY = date(2026, 10, 26)


def co(ticker, sector, industry, cap, pe=20.0, pb=2.0, roe=0.15, margin=0.10, growth=0.10):
    vals = {"market_cap": cap, "pe_ttm": pe, "pb": pb, "roe": roe, "net_margin_q": margin, "net_income_yoy": growth}
    fs = mkfs(ticker, {k: v for k, v in vals.items() if v is not None})
    ent = fs.entity.model_copy(update={"sector": sector, "industry": industry})
    return fs.model_copy(update={"entity": ent})


@pytest.fixture(scope="module")
def params():
    return load_peer_params(today=TODAY)


TARGET = lambda **o: co("TGT.NS", "Energy", "Refining", 1e13, **o)


def pool_of(*cos):
    return {c.entity.ticker: c for c in cos}


def test_pe1_deterministic_under_shuffle(params):
    cos = [co(f"P{i}.NS", "Energy", "Refining", 1e13 * (1 + i / 10), pe=10 + i) for i in range(8)]
    a = select_peers(TARGET(), pool_of(*cos), params=params)
    random.Random(1).shuffle(cos)
    b = select_peers(TARGET(), pool_of(*cos), params=params)
    assert a.model_dump() == b.model_dump()


def test_pe2_tier1_beats_closer_tier2(params):
    t1_far = co("FAR.NS", "Energy", "Refining", 5e11)                  # same industry, 20x smaller
    t2_near = co("NEAR.NS", "Energy", "Coal", 1e13)                     # same sector, identical size
    g = select_peers(TARGET(), pool_of(t1_far, t2_near), k=1, params=params)
    assert [p.ticker for p in g.picks] == ["FAR.NS"] and g.picks[0].tier == 1


def test_pe3_size_ceiling_and_per_tier_floors(params):
    cos = [co("HUGE.NS", "Energy", "Refining", 3e14),                    # 30x larger: out
           co("TINY1.NS", "Energy", "Refining", 1e13 / 150),            # tier 1 floor 1/200: in
           co("TINY2.NS", "Energy", "Coal", 1e13 / 50)]                 # tier 2 floor 1/20: out
    g = select_peers(TARGET(), pool_of(*cos), params=params)
    assert [p.ticker for p in g.picks] == ["TINY1.NS"]
    reasons = {e.ticker: e.reason for e in g.excluded}
    assert "larger than" in reasons["HUGE.NS"] and "smaller than" in reasons["TINY2.NS"]


def test_pe4_member_gate_positive_pe_and_market_cap(params):
    cos = [co("LOSS.NS", "Energy", "Refining", 1e13, pe=-5), co("NOPE.NS", "Energy", "Refining", 1e13, pe=None),
           co("NOCAP.NS", "Energy", "Refining", None), co("OK.NS", "Energy", "Refining", 1e13)]
    g = select_peers(TARGET(), pool_of(*cos), params=params)
    assert [p.ticker for p in g.picks] == ["OK.NS"]
    why = {e.ticker: e.reason for e in g.excluded}
    assert "not positive" in why["LOSS.NS"] and "no P/E" in why["NOPE.NS"] and "no market cap" in why["NOCAP.NS"]


def test_pe5_extreme_pe_stays_member_but_out_of_median(params):
    cos = [co(f"P{i}.NS", "Energy", "Refining", 1e13, pe=pe) for i, pe in enumerate([10, 12, 14, 156])]
    t = TARGET(pe=20)
    g = select_peers(t, pool_of(*cos), params=params)
    assert len(g.picks) == 4
    pe = {c.metric: c for c in compare_peers(t, g, pool_of(*cos), params=params)}["pe_ttm"]
    assert pe.n == 3 and pe.peer_median == 12.0


def test_pe6_k_limit_and_alphabetical_ties(params):
    cos = [co(f"{n}.NS", "Energy", "Refining", 1e13) for n in "EDCBAF"]
    g = select_peers(TARGET(), pool_of(*cos), k=3, params=params)
    assert [p.ticker for p in g.picks] == ["A.NS", "B.NS", "C.NS"]


def test_pe7_target_never_its_own_peer(params):
    t = TARGET()
    g = select_peers(t, pool_of(t, co("O.NS", "Energy", "Refining", 1e13)), params=params)
    assert [p.ticker for p in g.picks] == ["O.NS"]


def test_pe8_too_few_valid_peers_is_unavailable_with_reason(params):
    cos = [co("A.NS", "Energy", "Refining", 1e13), co("B.NS", "Energy", "Refining", 1e13)]
    t = TARGET()
    cmp = compare_peers(t, select_peers(t, pool_of(*cos), params=params), pool_of(*cos), params=params)
    pe = {c.metric: c for c in cmp}["pe_ttm"]
    assert pe.status == "unavailable" and "fewer than 3" in pe.reason and pe.peer_median is None
    empty = select_peers(t, {}, params=params)
    assert empty.picks == [] and "no peers" in empty.unavailable_reason


def test_pe9_median_not_mean_and_pe10_premium_math(params):
    cos = [co(f"P{i}.NS", "Energy", "Refining", 1e13, pe=pe) for i, pe in enumerate([10, 12, 16, 18, 70])]
    t = TARGET(pe=20)
    cmp = {c.metric: c for c in compare_peers(t, select_peers(t, pool_of(*cos), params=params), pool_of(*cos), params=params)}
    pe = cmp["pe_ttm"]
    assert pe.peer_median == 16.0                      # mean would be 25.2
    assert pe.premium == pytest.approx(0.25) and pe.higher_than == 4 and pe.of == 5


def test_pe12_missing_target_inputs(params):
    no_cap = co("T.NS", "Energy", "Refining", None)
    g = select_peers(no_cap, pool_of(co("A.NS", "Energy", "Refining", 1e13)), params=params)
    assert g.picks == [] and "target market cap" in g.unavailable_reason
    no_ind = co("T.NS", None, None, 1e13)
    g = select_peers(no_ind, pool_of(co("A.NS", "Energy", "Refining", 1e13)), params=params)
    assert g.picks == [] and "industry or sector" in g.unavailable_reason


def test_pe13_sector_only_target_uses_tier2(params):
    t = co("T.NS", "Energy", None, 1e13)
    g = select_peers(t, pool_of(co("A.NS", "Energy", "Coal", 1e13), co("B.NS", "Tech", "Software", 1e13)), params=params)
    assert [(p.ticker, p.tier) for p in g.picks] == [("A.NS", 2)]


def test_pe14_trace_on_every_pick(params):
    t = TARGET()
    g = select_peers(t, pool_of(co("A.NS", "Energy", "Refining", 2e13)), params=params)
    p = g.picks[0]
    assert p.tier == 1 and p.size_ratio == pytest.approx(2.0) and p.reason and p.fact_ids


def test_peer_params_validation(tmp_path):
    d = json.load(open("indiafacts/data/peer_params.json"))
    d["review_by"] = "2026-01-01"
    p = tmp_path / "p.json"
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="review"):
        load_peer_params(p, today=TODAY)
    assert load_peer_params(p, today=TODAY, strict=False)["overdue"]


def test_pe15_sector_only_peer_set_is_called_coarse(params):
    t = TARGET()
    g = select_peers(t, pool_of(co("A.NS", "Energy", "Coal", 1e13)), params=params)
    assert any("no same-industry peers" in n for n in g.notes)
    g2 = select_peers(t, pool_of(co("A.NS", "Energy", "Refining", 1e13)), params=params)
    assert not any("no same-industry peers" in n for n in g2.notes)


def test_pe16_rates_are_compared_by_difference_not_ratio_of_percentages(params):
    cos = [co(f"P{i}.NS", "Energy", "Refining", 1e13, pe=16, roe=0.15, growth=0.006 + i * 1e-4) for i in range(4)]
    t = TARGET(pe=20, roe=0.20, growth=-0.224)
    cmp = {c.metric: c for c in compare_peers(t, select_peers(t, pool_of(*cos), params=params), pool_of(*cos), params=params)}
    assert cmp["pe_ttm"].premium == pytest.approx(0.25) and cmp["pe_ttm"].diff is None
    assert cmp["roe"].premium is None and cmp["roe"].diff == pytest.approx(0.05)
    assert cmp["net_income_yoy"].premium is None and cmp["net_income_yoy"].diff == pytest.approx(-0.224 - 0.00615, abs=1e-4)


def test_pe17_same_industry_label_but_different_sector_is_not_a_peer(params):
    t = TARGET()                                                   # Energy / Refining
    g = select_peers(t, pool_of(co("X.NS", "Autos", "Refining", 1e13), co("Y.NS", "Energy", "Refining", 1e13)), params=params)
    assert [p.ticker for p in g.picks] == ["Y.NS"]
