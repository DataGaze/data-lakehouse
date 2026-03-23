"""Schema definition cho misc data (foreign trading, open interest)."""
from __future__ import annotations

import polars as pl

SILVER_SCHEMA = pl.Schema({
    "symbol": pl.Utf8,
    "foreign_buy_vol": pl.Int64,
    "foreign_sell_vol": pl.Int64,
    "foreign_net_vol": pl.Int64,
    "timestamp": pl.Datetime("ms", "Asia/Ho_Chi_Minh"),
    "exchange": pl.Utf8,
    "date": pl.Date,
})
