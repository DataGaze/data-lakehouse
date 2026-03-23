"""Sync stock Parquet files từ Cloudflare R2 → SeaweedFS Bronze zone.

Backup path khi VPS không truy cập được.

Usage:
    python -m ingestion.stock.sync_r2_to_bronze
    python -m ingestion.stock.sync_r2_to_bronze --date 2026-03-20
"""
from __future__ import annotations

import argparse
import logging
import os
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv

from ingestion.common.s3_client import get_s3_client, object_exists
from ingestion.common.utils import vn_today

load_dotenv()
log = logging.getLogger("ingestion.stock.r2_to_bronze")


def get_r2_client():
    """Tạo boto3 client cho Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def sync_date_from_r2(date: str) -> dict:
    """Sync Parquet files của 1 ngày từ R2 → Bronze."""
    r2 = get_r2_client()
    seaweed = get_s3_client()
    r2_bucket = os.environ["R2_BUCKET"]
    s3_bucket = os.environ["S3_BUCKET"]
    stats = {"uploaded": 0, "skipped": 0, "errors": 0}

    # R2 key format: {YYYY}/{MM}/{DD}/{channel}/{file}.parquet
    r2_prefix = date.replace("-", "/")[:10].replace("-", "/")
    # Convert YYYY-MM-DD to YYYY/MM/DD
    parts = date.split("-")
    r2_prefix = f"{parts[0]}/{parts[1]}/{parts[2]}/"

    paginator = r2.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=r2_bucket, Prefix=r2_prefix):
        for obj in page.get("Contents", []):
            r2_key = obj["Key"]
            # R2: 2026/03/20/ticks/HOSE.parquet → Bronze: bronze/stock/2026-03-20/ticks/HOSE.parquet
            relative = r2_key[len(r2_prefix):]
            s3_key = f"bronze/stock/{date}/{relative}"

            if object_exists(s3_key, s3_bucket):
                stats["skipped"] += 1
                continue

            try:
                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                    tmp_path = tmp.name

                r2.download_file(r2_bucket, r2_key, tmp_path)
                seaweed.upload_file(tmp_path, s3_bucket, s3_key)
                stats["uploaded"] += 1
                log.info(f"R2→Bronze: {s3_key}")
            except Exception as e:
                stats["errors"] += 1
                log.error(f"Failed {r2_key}: {e}")
            finally:
                Path(tmp_path).unlink(missing_ok=True)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Sync CF R2 → SeaweedFS Bronze")
    parser.add_argument("--date", default=vn_today(), help="Date (YYYY-MM-DD)")
    args = parser.parse_args()

    log.info(f"Syncing R2 → Bronze for {args.date}...")
    stats = sync_date_from_r2(args.date)
    log.info(f"Done. {stats}")


if __name__ == "__main__":
    main()
