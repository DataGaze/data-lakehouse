# Manual Backfill Flow (R2 Replay)

> Version: 1.0 | Last Updated: 2026-04-13 | Status: Draft

## Overview

Khi operator phát hiện gap ở Gold (ví dụ MarketPulse report thiếu ngày 2026-04-11), backfill bằng cách replay từ R2 với flag `--date=YYYY-MM-DD`. Flow đảm bảo idempotent qua `ON CONFLICT UPDATE` ở Postgres Gold.

## Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant MP as MarketPulse<br/>(gap detector)
    participant PF as Prefect Server<br/>(LXC 201)
    participant LH as lakehouse-gold<br/>(LXC 202, worker)
    participant R2 as Cloudflare R2<br/>(SoT bucket)
    participant PG as Postgres<br/>(Gold, schema=prod)
    participant TG as Telegram Bot

    Note over MP,Op: Discovery — 2026-04-12 08:00
    MP->>PG: SELECT count(*) FROM gold.daily_summary<br/>WHERE date BETWEEN '2026-04-10' AND '2026-04-12'
    PG-->>MP: rows: {04-10: 1620, 04-11: 0, 04-12: 1615}
    MP->>TG: ALERT gap detected for 2026-04-11
    TG-->>Op: Notify

    Note over Op,PF: Manual trigger via SSH
    Op->>PF: ssh prefect@LXC-201<br/>prefect deployment run ingest_daily<br/>--param date=2026-04-11 --param mode=backfill
    PF-->>Op: Flow run scheduled (id=abc-123)
    PF->>LH: Dispatch flow run (date=2026-04-11, mode=backfill)

    Note over LH,R2: Idempotent replay from R2
    LH->>R2: HEAD bronze/stock/2026-04-11/**
    R2-->>LH: Objects exist (15 files, ~470 MB)
    LH->>R2: GET objects (parallel)
    R2-->>LH: Parquet bytes

    LH->>LH: Write Bronze (overwrite local staging)
    LH->>LH: Polars Bronze → Silver<br/>(same transform as daily flow)

    rect rgb(230, 245, 230)
    Note over LH,PG: Idempotent Gold load
    LH->>PG: dbt run --target prod --vars '{date: 2026-04-11}'<br/>MERGE ON (trade_date, symbol, channel)<br/>ON CONFLICT DO UPDATE SET ...
    PG-->>LH: rows_inserted=0, rows_updated=1620
    end

    LH->>PG: SELECT count(*) FROM gold.daily_summary<br/>WHERE date='2026-04-11'
    PG-->>LH: 1620 rows (matches Silver row count)
    LH->>LH: dbt test --select tag:freshness tag:unique
    LH-->>PF: Report state=Completed

    PF->>TG: Flow ingest_daily (backfill 2026-04-11) COMPLETED<br/>rows: 1620, duration: 4m12s
    TG-->>Op: Notify success
    Op->>MP: Re-trigger report generation (optional)
```

## Notes

- **Timing SLA**: Backfill 1 ngày thường hoàn tất trong 4–6 phút (R2 download ~2m, Polars ~1m, dbt ~1m). Backfill > 7 ngày nên chunk theo batch để tránh OOM.
- **Idempotency guarantees** (D6 ADR):
  - Bronze: overwrite theo date partition (R2 object key làm natural key)
  - Silver: Parquet overwrite theo `date=YYYY-MM-DD` partition
  - Gold: `ON CONFLICT (trade_date, symbol, channel) DO UPDATE` — chạy lại nhiều lần không double-count
- **Failure modes**:
  - R2 HEAD trả 404 (bước 10) → flow fail ngay với message `NO_R2_DATA_FOR_DATE`, không tạo Bronze trống. Operator phải check bizfly WAL archive thủ công.
  - Silver row count mismatch với Gold (bước 18 vs Silver) → dbt test `unique_trade_date_symbol` fail → rollback bằng `DELETE FROM gold.daily_summary WHERE date='2026-04-11'` rồi re-run.
  - Gap > 7 ngày: dùng `--param mode=backfill_range --param start=... --param end=...` (loop internal).
- **References**: ADR-2026-04-13 (D3 R2 ingestion, D6 schema separation), `data-lakehouse/CLAUDE.md` (Quality Gate #3: Gold row count khớp Silver).
