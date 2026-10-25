# TejHQ adapter plan (compact)
Source: huggingface.co/datasets/tejhq/indian-markets (MIT tag; "redistributable"; verify exchange terms before commercial use). Educational, non-commercial project; attribute TejHQ.
Goal: identity (ISIN, rename history), price-affecting corporate action dates, and a point-in-time top-N universe from TejHQ parquet, with a one-day local cache and graceful degradation.
T1 `indiafacts/tej.py` TejStore: `load(path) -> DataFrame` via injectable `fetch(url)->bytes`, cache in ~/.indiafacts/tej, refetch after 1 day, corrupt cache rebuilt, failure raises TejUnavailable. Tests: cache hit, stale refetch, corrupt file, failure.
T2 `symbol_changes_from_history(df) -> SymbolChanges` (same ISIN, symbol A then B => A->B at B.valid_from; same symbol with new ISIN ignored; reused symbol handled) and `isin_for(df, symbol, as_of)`. Tests with synthetic ZOMATO/ETERNAL, TATAMOTORS/TMPV/TMCV rows.
T3 `price_affecting_dates(actions_df, history_df, symbol) -> list[date]` for types demerger and merger over all symbols sharing the ISIN. Tests.
T4 `universe_members(df, as_of, top_n)` latest rebalance on/before as_of (no look-ahead), ordered by rank; CLI `--universe tej` / `tej:N`. Tests.
T5 Pipeline/CLI wiring: `tej=True` in CLI (flag `--no-tej`), library default False; identity falls back to Tej when no symbolchange.csv; ISIN filled from Tej when no filing; price-flag dates = curated + Tej; notice when Tej unavailable. Tests offline with fake fetcher; one live test.
