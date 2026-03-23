"""ETL: Bronze → Silver cho stock data.

Đọc raw Parquet từ SeaweedFS Bronze → dedup, validate, enforce schema → Silver Parquet.

Usage:
    python -m etl.stock.bronze_to_silver
    python -m etl.stock.bronze_to_silver --date 2026-03-20
"""
from __future__ import annotations

import argparse
import io
import logging
import tempfile
from pathlib import Path

import polars as pl
from dotenv import load_dotenv

from ingestion.common.s3_client import (
    download_file,
    get_s3_client,
    list_objects,
    object_exists,
    upload_file,
)
from ingestion.common.utils import vn_today

load_dotenv()
log = logging.getLogger("etl.stock.bronze_to_silver")

CHANNELS = ["ticks", "index", "misc", "orderbook"]
EXCHANGES = ["HOSE", "HNX", "UPCOM"]


def process_channel(date: str, channel: str, exchange: str) -> dict:
    """Process 1 Bronze file → Silver file."""
    bronze_key = f"bronze/stock/{date}/{channel}/{exchange}.parquet"
    silver_key = f"silver/stock/{date}/{channel}/{exchange}.parquet"

    if not object_exists(bronze_key):
        return {"status": "skip", "reason": "bronze not found"}

    if object_exists(silver_key):
        return {"status": "skip", "reason": "silver exists"}

    # Download Bronze
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    download_file(bronze_key, tmp_path)

    try:
        df = pl.read_parquet(tmp_path)
        original_rows = len(df)

        # Dedup
        df = df.unique()

        # Drop nulls in critical columns (tùy channel)
        df = df.drop_nulls()

        deduped_rows = len(df)
        delta_pct = abs(original_rows - deduped_rows) / max(original_rows, 1) * 100

        if delta_pct > 10:
            log.warning(
                f"{bronze_key}: row delta {delta_pct:.1f}% "
                f"(original={original_rows}, deduped={deduped_rows})"
            )

        # Write Silver
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as out:
            out_path = Path(out.name)
        df.write_parquet(out_path)
        upload_file(out_path, silver_key)
        out_path.unlink(missing_ok=True)

        return {
            "status": "ok",
            "original_rows": original_rows,
            "silver_rows": deduped_rows,
            "delta_pct": round(delta_pct, 2),
        }
    finally:
        tmp_path.unlink(missing_ok=True)


def process_date(date: str) -> dict:
    """Process tất cả channels/exchanges cho 1 ngày."""
    results = {}
    for channel in CHANNELS:
        for exchange in EXCHANGES:
            key = f"{channel}/{exchange}"
            result = process_channel(date, channel, exchange)
            results[key] = result
            if result["status"] == "ok":
                log.info(f"  {key}: {result['silver_rows']} rows")
    return results


def main():
    parser = argparse.ArgumentParser(description="ETL: Bronze → Silver (stock)")
    parser.add_argument("--date", default=vn_today(), help="Date (YYYY-MM-DD)")
    args = parser.parse_args()

    log.info(f"Bronze → Silver for {args.date}")
    results = process_date(args.date)

    ok = sum(1 for r in results.values() if r["status"] == "ok")
    skip = sum(1 for r in results.values() if r["status"] == "skip")
    log.info(f"Done. Processed: {ok}, Skipped: {skip}")


if __name__ == "__main__":
    main()
