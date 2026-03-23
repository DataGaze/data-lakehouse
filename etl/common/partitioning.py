"""Partition strategies cho data lake."""
from __future__ import annotations


def bronze_key(source: str, date: str, channel: str, filename: str) -> str:
    """Tạo S3 key cho Bronze zone."""
    return f"bronze/{source}/{date}/{channel}/{filename}"


def silver_key(source: str, date: str, channel: str, filename: str) -> str:
    """Tạo S3 key cho Silver zone."""
    return f"silver/{source}/{date}/{channel}/{filename}"
