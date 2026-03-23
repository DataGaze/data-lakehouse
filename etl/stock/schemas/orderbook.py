"""Schema definition cho orderbook data."""
from __future__ import annotations

import polars as pl

SILVER_SCHEMA = pl.Schema({
    "symbol": pl.Utf8,
    "bid_price_1": pl.Float64,
    "bid_vol_1": pl.Int64,
    "ask_price_1": pl.Float64,
    "ask_vol_1": pl.Int64,
    "timestamp": pl.Datetime("ms", "Asia/Ho_Chi_Minh"),
    "exchange": pl.Utf8,
    "date": pl.Date,
})
