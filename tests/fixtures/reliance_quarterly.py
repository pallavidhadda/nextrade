"""Spec Fixture Q: real RELIANCE.NS quarterly figures from Yahoo, fetched 2026-10-25 (INR).
Sep-25 is absent in the vendor response; that gap is the point."""
import pandas as pd

COLS = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30", "2025-03-31"]

QUARTERLY = pd.DataFrame(
    {
        "Net Income Common Stockholders": [209460000000.0, 169710000000.0, 186450000000.0, 269940000000.0, 194070000000.0],
        "EBITDA": [389670000000.0, 337800000000.0, 363100000000.0, 441820000000.0, 352580000000.0],
        "Interest Expense": [83370000000.0, 65850000000.0, 66130000000.0, 70360000000.0, 61550000000.0],
        "Diluted EPS": [15.48, 12.54, 13.78, 19.95, 14.34],
    },
    index=pd.to_datetime(COLS),
).T

INFO = {
    "trailingPE": 21.550163, "trailingEps": 55.22, "currentPrice": 1190.0,
    "totalRevenue": 11296050249728, "netIncomeToCommon": 747269980160,
    "financialCurrency": "INR", "currency": "INR", "marketCap": 16103642234880,
    "returnOnEquity": None,
}
