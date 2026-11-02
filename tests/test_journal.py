from datetime import date

import pytest

from indiafacts.journal import Journal, render_scoreboard
from tests.pricefakes import FakePrices, bdays, frame

TODAY = date(2026, 11, 20)
DECIDED = date(2026, 10, 5)                   # a Monday; first close after it is Tuesday 2026-10-06


def prices(stock_end=110.0, bench_end=102.0, n=40, stock_start=100.0, bench_start=100.0, start="2026-09-28"):
    d = bdays(start, n)
    stock = [stock_start + (stock_end - stock_start) * i / (n - 1) for i in range(n)]
    bench = [bench_start + (bench_end - bench_start) * i / (n - 1) for i in range(n)]
    return FakePrices({"ABC.NS": frame(d, stock), "^NSEI": frame(d, bench)})


def jr(tmp_path):
    return Journal(tmp_path / "j.db")


def test_j1_record_is_idempotent_per_ticker_day_and_skips_no_rating(tmp_path):
    j = jr(tmp_path)
    assert j.record("ABC.NS", DECIDED, "Buy", "Medium", 71.0, 100.0, "h1", 21) is True
    assert j.record("ABC.NS", DECIDED, "Overweight", "High", 80.0, 101.0, "h1", 21) is True       # same day: replaced, not duplicated
    assert j.record("XYZ.NS", DECIDED, "No rating", "n/a", None, 100.0, "h1", 21) is False
    rows = j.pending()
    assert len(rows) == 1 and rows[0]["rating"] == "Overweight"


def test_j2_settlement_uses_first_close_after_the_decision_and_alpha_vs_benchmark(tmp_path):
    j = jr(tmp_path)
    j.record("ABC.NS", DECIDED, "Buy", "Medium", 71.0, 100.0, "h1", 5)
    res = j.settle(prices(), TODAY, holding_days=5)
    assert len(res.settled) == 1 and not res.failed
    row = j.settled_rows()[0]
    assert row["entry_date"] == "2026-10-06" and row["exit_date"] == "2026-10-13"       # entry + 5 sessions
    assert row["verdict"] == "consistent" and row["alpha"] > 0
    assert row["alpha"] == pytest.approx(row["raw_return"] - row["benchmark_return"])


def test_j3_window_not_traded_yet_stays_pending_without_a_failure(tmp_path):
    j = jr(tmp_path)
    j.record("ABC.NS", date(2026, 11, 18), "Buy", "Low", 60.0, 100.0, "h1", 21)
    res = j.settle(prices(n=45), TODAY, holding_days=21)
    assert res.settled == [] and res.failed == [] and len(j.pending()) == 1


def test_j4_bearish_and_hold_verdicts(tmp_path):
    j = jr(tmp_path)
    falling = prices(stock_end=90.0, bench_end=101.0)
    j.record("ABC.NS", DECIDED, "Sell", "High", 20.0, 100.0, "h", 5)
    j.settle(falling, TODAY, holding_days=5)
    assert j.settled_rows()[0]["verdict"] == "consistent"
    j2 = Journal(tmp_path / "j2.db")
    j2.record("ABC.NS", DECIDED, "Hold", "Medium", 50.0, 100.0, "h", 5)
    j2.settle(prices(stock_end=140.0, bench_end=101.0), TODAY, holding_days=5)
    assert j2.settled_rows()[0]["verdict"] == "inconsistent"
    j3 = Journal(tmp_path / "j3.db")
    j3.record("ABC.NS", DECIDED, "Hold", "Medium", 50.0, 100.0, "h", 5)
    j3.settle(prices(stock_end=101.0, bench_end=100.5), TODAY, holding_days=5)
    assert j3.settled_rows()[0]["verdict"] == "consistent"


def test_j5_price_failure_is_reported_and_the_decision_stays_pending(tmp_path):
    class Boom:
        def history(self, symbol):
            raise ConnectionError("proxy blocked")

    j = jr(tmp_path)
    j.record("ABC.NS", DECIDED, "Buy", "Medium", 71.0, 100.0, "h1", 5)
    res = j.settle(Boom(), TODAY, holding_days=5)
    assert res.settled == [] and len(res.failed) == 1 and "ABC.NS" in res.failed[0][0] and len(j.pending()) == 1
    assert "proxy" not in res.failed[0][2].lower()


def test_j6_scoreboard_groups_by_rating_and_handles_empty(tmp_path):
    j = jr(tmp_path)
    assert j.scoreboard()["overall"]["n"] == 0
    for t, rating, end in (("A.NS", "Buy", 120.0), ("B.NS", "Buy", 90.0), ("C.NS", "Sell", 80.0)):
        j.record(t, DECIDED, rating, "Medium", 60.0, 100.0, "h", 5)
    fp = FakePrices({k: frame(bdays("2026-09-28", 40), [100 + (e - 100) * i / 39 for i in range(40)]) for k, e in (("A.NS", 120.0), ("B.NS", 90.0), ("C.NS", 80.0))} |
                    {"^NSEI": frame(bdays("2026-09-28", 40), [100 + 2 * i / 39 for i in range(40)])})
    j.settle(fp, TODAY, holding_days=5)
    sb = j.scoreboard()
    assert sb["by_rating"]["Buy"]["n"] == 2 and sb["by_rating"]["Buy"]["consistent_rate"] == pytest.approx(0.5)
    assert sb["by_rating"]["Sell"]["consistent_rate"] == 1.0 and sb["overall"]["n"] == 3
    text = render_scoreboard(sb)
    assert "Buy" in text and "not a track record" in text.lower() and "Not financial" in text


def test_j7_cli_records_the_rating_unless_remembering_is_off(tmp_path, capsys):
    from indiafacts.cli import main
    from tests.fakes import FakeClient
    from tests.fixtures.reliance_quarterly import INFO, QUARTERLY
    from tests.test_explain_cli import INFO2
    from tests.test_htmlreport import NSE_CSV, SYMS, prices_for

    c = tmp_path / "ind.csv"
    c.write_text(NSE_CSV, encoding="utf-8")
    base = ["RELIANCE.NS", "--score", "--universe", str(c), "--no-tej"]
    j = Journal(tmp_path / "x.db")
    main([*base, "--no-remember"], client=FakeClient(stmt=QUARTERLY, info=INFO2), sleep=lambda s: None, price_client=prices_for(SYMS), journal=j)
    assert j.pending() == []
    from indiafacts.brain import Brain

    main(base, client=FakeClient(stmt=QUARTERLY, info=INFO2), sleep=lambda s: None, price_client=prices_for(SYMS), journal=j, brain=Brain(tmp_path / "b.db"))
    rows = j.pending()
    assert len(rows) == 1 and rows[0]["ticker"] == "RELIANCE.NS" and rows[0]["rating"] in ("Buy", "Overweight", "Hold", "Underweight", "Sell")
    assert rows[0]["price"] and rows[0]["horizon_days"] == 21
