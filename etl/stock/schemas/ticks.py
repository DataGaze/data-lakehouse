"""Schema definition cho stock ticks data."""
from __future__ import annotations

import polars as pl

# Bronze schema — raw từ SSI pipeline (as-is)
BRONZE_SCHEMA = {
    "Symbol": pl.Utf8,
    "Last": pl.Float64,
    "Vol": pl.Float64,
    "TotalVol": pl.Float64,
    "TotalVal": pl.Float64,
    "Time": pl.Utf8,
}

# Silver schema — cleaned, validated
SILVER_SCHEMA = pl.Schema({
    "symbol": pl.Utf8,
    "price": pl.Float64,
    "volume": pl.Int64,
    "total_volume": pl.Int64,
    "total_value": pl.Float64,
    "timestamp": pl.Datetime("ms", "Asia/Ho_Chi_Minh"),
    "exchange": pl.Utf8,
    "date": pl.Date,
})

# Gold schema — aggregated daily OHLCV
GOLD_DAILY_OHLCV = pl.Schema({
    "date": pl.Date,
    "symbol": pl.Utf8,
    "exchange": pl.Utf8,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
    "value": pl.Float64,
})
