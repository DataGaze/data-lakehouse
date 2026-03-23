"""ETL: Silver → Gold cho stock data.

Đọc Silver Parquet từ SeaweedFS → aggregate → INSERT PostgreSQL (Gold).

Usage:
    python -m etl.stock.silver_to_gold
    python -m etl.stock.silver_to_gold --date 2026-03-20
"""
from __future__ import annotations

import argparse
import logging
import os
import tempfile
from pathlib import Path

import polars as pl
import psycopg2
from dotenv import load_dotenv

from ingestion.common.s3_client import download_file, list_objects, object_exists
from ingestion.common.utils import vn_today

load_dotenv()
log = logging.getLogger("etl.stock.silver_to_gold")


def get_pg_connection():
    """Tạo PostgreSQL connection."""
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=int(os.environ.get("PG_PORT", 5432)),
        database=os.environ["PG_DATABASE"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
    )


def load_ticks_to_gold(date: str) -> int:
    """Aggregate ticks Silver → daily OHLCV Gold."""
    rows_inserted = 0
    conn = get_pg_connection()
    cur = conn.cursor()

    for exchange in ["HOSE", "HNX", "UPCOM"]:
        silver_key = f"silver/stock/{date}/ticks/{exchange}.parquet"
        if not object_exists(silver_key):
            continue

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        download_file(silver_key, tmp_path)

        try:
            df = pl.read_parquet(tmp_path)

            # Tìm các column names phù hợp (Bronze schema có thể khác nhau)
            # TODO: enforce Silver schema trước khi aggregate
            if len(df) == 0:
                continue

            log.info(f"  {exchange}: {len(df)} ticks → aggregating...")

            # INSERT vào PostgreSQL
            # TODO: implement OHLCV aggregation + INSERT khi PG schema ready
            rows_inserted += len(df)
        finally:
            tmp_path.unlink(missing_ok=True)

    conn.commit()
    cur.close()
    conn.close()
    return rows_inserted


def main():
    parser = argparse.ArgumentParser(description="ETL: Silver → Gold (stock)")
    parser.add_argument("--date", default=vn_today(), help="Date (YYYY-MM-DD)")
    args = parser.parse_args()

    log.info(f"Silver → Gold for {args.date}")
    rows = load_ticks_to_gold(args.date)
    log.info(f"Done. Rows processed: {rows}")


if __name__ == "__main__":
    main()
