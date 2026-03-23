"""Shared utilities cho ingestion pipelines."""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def vn_today() -> str:
    """Trả về ngày hôm nay theo múi giờ VN (YYYY-MM-DD)."""
    return datetime.now(VN_TZ).strftime("%Y-%m-%d")


def trading_dates(start: str, end: str) -> list[str]:
    """Trả về danh sách ngày giao dịch (Mon-Fri) trong khoảng."""
    from datetime import timedelta

    dates: list[str] = []
    current = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while current <= end_dt:
        if current.weekday() < 5:  # Mon-Fri
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates
