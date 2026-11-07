from datetime import date

from indiafacts.journal import Journal, main


def seeded(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.record("A.NS", date(2026, 10, 1), "Hold", "Medium", 55.0, 100.0)
    j.record("B.NS", date(2026, 10, 2), "Buy", "High", 80.0, 200.0)
    return j


def test_csv_round_trip_keeps_rows_and_ignores_duplicates(tmp_path):
    j = seeded(tmp_path)
    assert j.export_csv(tmp_path / "out" / "j.csv") == 2
    j2 = Journal(tmp_path / "other.db")
    assert j2.import_csv(tmp_path / "out" / "j.csv") == 2
    assert j2.import_csv(tmp_path / "out" / "j.csv") == 0                       # second import adds nothing
    assert {r["ticker"] for r in j2.pending()} == {"A.NS", "B.NS"}


def test_log_rates_a_slice_and_survives_one_failure(tmp_path):
    j = Journal(tmp_path / "j.db")
    pool = tmp_path / "t.txt"
    pool.write_text("# c\nA.NS\nB.NS\nC.NS\n")
    calls = []

    def runner(t):
        calls.append(t)
        if t == "B.NS":
            raise RuntimeError("boom")
        return 0

    import argparse
    from indiafacts.journal import log_batch
    a = argparse.Namespace(tickers=pool, limit=3, pool_size=5)
    assert log_batch(j, a, runner=runner) == 0
    assert sorted(calls) == ["A.NS", "B.NS", "C.NS"]
