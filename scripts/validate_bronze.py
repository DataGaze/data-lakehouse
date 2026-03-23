"""Validate Bronze data integrity trên SeaweedFS.

Kiểm tra: files tồn tại, format Parquet hợp lệ, size > 0.

Usage:
    python scripts/validate_bronze.py
    python scripts/validate_bronze.py --date 2026-03-20
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

import polars as pl
from dotenv import load_dotenv

from ingestion.common.s3_client import download_file, list_objects
from ingestion.common.utils import vn_today

load_dotenv()
log = logging.getLogger("validate_bronze")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

EXPECTED_CHANNELS = ["ticks", "index", "misc"]
EXPECTED_EXCHANGES = ["HOSE"]  # HNX, UPCOM optional


def validate_date(date: str) -> tuple[int, int]:
    """Validate Bronze data cho 1 ngày. Returns (passed, failed)."""
    prefix = f"bronze/stock/{date}/"
    objects = list_objects(prefix)

    if not objects:
        log.warning(f"{date}: Không có data trong Bronze")
        return 0, 1

    passed = 0
    failed = 0

    for s3_key in objects:
        if not s3_key.endswith(".parquet"):
            continue

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            download_file(s3_key, tmp_path)

            # Check size > 0
            if tmp_path.stat().st_size == 0:
                log.warning(f"  FAIL {s3_key}: file rỗng")
                failed += 1
                continue

            # Check valid Parquet
            df = pl.read_parquet(tmp_path)
            if len(df) == 0:
                log.warning(f"  FAIL {s3_key}: 0 rows")
                failed += 1
            else:
                log.info(f"  OK   {s3_key}: {len(df)} rows, {len(df.columns)} cols")
                passed += 1
        except Exception as e:
            log.error(f"  FAIL {s3_key}: {e}")
            failed += 1
        finally:
            tmp_path.unlink(missing_ok=True)

    return passed, failed


def main():
    parser = argparse.ArgumentParser(description="Validate Bronze data")
    parser.add_argument("--date", default=vn_today(), help="Date (YYYY-MM-DD)")
    args = parser.parse_args()

    log.info(f"Validating Bronze: {args.date}")
    passed, failed = validate_date(args.date)
    log.info(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
