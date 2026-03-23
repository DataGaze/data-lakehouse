"""Sync stock Parquet files từ VPS → SeaweedFS Bronze zone.

Usage:
    python -m ingestion.stock.sync_vps_to_bronze
    python -m ingestion.stock.sync_vps_to_bronze --date 2026-03-20
    python -m ingestion.stock.sync_vps_to_bronze --from 2026-03-16 --to 2026-03-20
"""
from __future__ import annotations

import argparse
import logging
import os
import tempfile
from pathlib import Path

import paramiko
from dotenv import load_dotenv

from ingestion.common.s3_client import get_s3_client, object_exists
from ingestion.common.utils import vn_today

load_dotenv()
log = logging.getLogger("ingestion.stock.vps_to_bronze")

CHANNELS = ["ticks", "index", "misc", "orderbook", "backfill"]


def get_ssh_client() -> paramiko.SSHClient:
    """Tạo SSH connection tới VPS."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=os.environ["VPS_HOST"],
        port=int(os.environ["VPS_PORT"]),
        username=os.environ["VPS_USER"],
        password=os.environ.get("VPS_PASSWORD"),
    )
    return client


def list_export_dates(ssh: paramiko.SSHClient) -> list[str]:
    """List các ngày có data export trên VPS."""
    data_dir = os.environ["VPS_DATA_DIR"]
    _, stdout, _ = ssh.exec_command(f"ls -1 {data_dir}")
    return sorted(line.strip() for line in stdout if line.strip())


def sync_date(ssh: paramiko.SSHClient, date: str) -> dict:
    """Sync tất cả Parquet files của 1 ngày từ VPS → Bronze."""
    data_dir = os.environ["VPS_DATA_DIR"]
    bucket = os.environ["S3_BUCKET"]
    s3 = get_s3_client()
    sftp = ssh.open_sftp()
    stats = {"uploaded": 0, "skipped": 0, "errors": 0}

    remote_date_dir = f"{data_dir}/{date}"

    for channel in CHANNELS:
        remote_channel_dir = f"{remote_date_dir}/{channel}"
        try:
            files = sftp.listdir(remote_channel_dir)
        except FileNotFoundError:
            continue

        for filename in files:
            if not filename.endswith(".parquet"):
                continue

            s3_key = f"bronze/stock/{date}/{channel}/{filename}"

            if object_exists(s3_key, bucket):
                stats["skipped"] += 1
                continue

            remote_path = f"{remote_channel_dir}/{filename}"
            try:
                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                    tmp_path = tmp.name

                sftp.get(remote_path, tmp_path)
                s3.upload_file(tmp_path, bucket, s3_key)
                stats["uploaded"] += 1
                log.info(f"Uploaded: {s3_key}")
            except Exception as e:
                stats["errors"] += 1
                log.error(f"Failed {s3_key}: {e}")
            finally:
                Path(tmp_path).unlink(missing_ok=True)

    sftp.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Sync VPS Parquet → SeaweedFS Bronze")
    parser.add_argument("--date", help="Sync specific date (YYYY-MM-DD)")
    parser.add_argument("--from", dest="from_date", help="Start date")
    parser.add_argument("--to", dest="to_date", help="End date")
    args = parser.parse_args()

    ssh = get_ssh_client()

    if args.date:
        dates = [args.date]
    elif args.from_date and args.to_date:
        from ingestion.common.utils import trading_dates
        dates = trading_dates(args.from_date, args.to_date)
    else:
        # Default: sync hôm nay
        dates = [vn_today()]

    total = {"uploaded": 0, "skipped": 0, "errors": 0}
    for date in dates:
        log.info(f"Syncing {date}...")
        stats = sync_date(ssh, date)
        for k, v in stats.items():
            total[k] += v
        log.info(f"  {date}: {stats}")

    ssh.close()
    log.info(f"Done. Total: {total}")


if __name__ == "__main__":
    main()
