"""Data quality checks cho ETL pipelines."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

log = logging.getLogger("etl.quality")


@dataclass
class QualityResult:
    passed: bool
    check_name: str
    message: str
    details: dict | None = None


def check_not_empty(df: pl.DataFrame, source: str) -> QualityResult:
    """Kiểm tra DataFrame không rỗng."""
    if len(df) == 0:
        return QualityResult(False, "not_empty", f"{source}: DataFrame rỗng")
    return QualityResult(True, "not_empty", f"{source}: {len(df)} rows")


def check_no_duplicates(df: pl.DataFrame, subset: list[str], source: str) -> QualityResult:
    """Kiểm tra không có duplicate rows theo subset columns."""
    dupes = len(df) - len(df.unique(subset=subset))
    if dupes > 0:
        return QualityResult(
            False, "no_duplicates",
            f"{source}: {dupes} duplicate rows on {subset}",
            {"duplicate_count": dupes},
        )
    return QualityResult(True, "no_duplicates", f"{source}: no duplicates")


def check_row_count_delta(
    original: int, processed: int, max_delta_pct: float = 5.0, source: str = ""
) -> QualityResult:
    """Kiểm tra row count delta không quá lớn."""
    if original == 0:
        return QualityResult(True, "row_delta", f"{source}: original is empty")
    delta_pct = abs(original - processed) / original * 100
    passed = delta_pct <= max_delta_pct
    return QualityResult(
        passed, "row_delta",
        f"{source}: delta {delta_pct:.1f}% (orig={original}, proc={processed})",
        {"delta_pct": round(delta_pct, 2)},
    )


def run_checks(checks: list[QualityResult]) -> bool:
    """Chạy tất cả checks, log kết quả, return True nếu all passed."""
    all_passed = True
    for check in checks:
        if check.passed:
            log.info(f"  PASS: {check.message}")
        else:
            log.warning(f"  FAIL: {check.message}")
            all_passed = False
    return all_passed
