"""ETL Orchestrator — entry point cho ETL pod trên K3s.

Chạy toàn bộ pipeline: Bronze → Silver → Gold cho source chỉ định.

Usage:
    python -m etl.orchestrator --source stock
    python -m etl.orchestrator --source stock --date 2026-03-20
    python -m etl.orchestrator --source stock --step silver  # Chỉ Bronze → Silver
    python -m etl.orchestrator --source stock --step gold    # Chỉ Silver → Gold
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from ingestion.common.utils import vn_today

load_dotenv()
log = logging.getLogger("etl.orchestrator")


def run_stock_pipeline(date: str, step: str | None = None):
    """Chạy stock ETL pipeline."""
    if step is None or step == "silver":
        log.info(f"=== Bronze → Silver ({date}) ===")
        from etl.stock.bronze_to_silver import process_date
        results = process_date(date)
        ok = sum(1 for r in results.values() if r["status"] == "ok")
        log.info(f"Silver: {ok} files processed")

    if step is None or step == "gold":
        log.info(f"=== Silver → Gold ({date}) ===")
        from etl.stock.silver_to_gold import load_ticks_to_gold
        rows = load_ticks_to_gold(date)
        log.info(f"Gold: {rows} rows processed")


def main():
    parser = argparse.ArgumentParser(description="ETL Orchestrator")
    parser.add_argument("--source", required=True, choices=["stock", "bds"], help="Data source")
    parser.add_argument("--date", default=vn_today(), help="Date (YYYY-MM-DD)")
    parser.add_argument("--step", choices=["silver", "gold"], help="Run specific step only")
    args = parser.parse_args()

    log.info(f"ETL Pipeline: source={args.source}, date={args.date}, step={args.step or 'all'}")

    if args.source == "stock":
        run_stock_pipeline(args.date, args.step)
    elif args.source == "bds":
        log.info("BĐS pipeline: chưa implement")
        sys.exit(0)

    log.info("Pipeline completed.")


if __name__ == "__main__":
    main()
