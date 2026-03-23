"""Schema definition cho market index data."""
from __future__ import annotations

import polars as pl

SILVER_SCHEMA = pl.Schema({
    "index_name": pl.Utf8,
    "value": pl.Float64,
    "change": pl.Float64,
    "change_pct": pl.Float64,
    "total_volume": pl.Int64,
    "total_value": pl.Float64,
    "timestamp": pl.Datetime("ms", "Asia/Ho_Chi_Minh"),
    "exchange": pl.Utf8,
    "date": pl.Date,
})
