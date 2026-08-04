# End-to-End Ingestion Flow (Happy Path)

> Version: 1.0 | Last Updated: 2026-04-13 | Status: Draft

## Overview

Luồng ingestion hàng ngày từ SSI FastConnect → Bizfly VPS → Cloudflare R2 → lakehouse-gold (Bronze/Silver/Gold) → MarketPulse → Telegram. Flow này chạy mỗi phiên giao dịch, hoàn tất trước 18:00 ICT.

## Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant SSI as SSI FastConnect<br/>(SignalR API)
    participant Biz as Bizfly VPS<br/>(ssi-connection)
    participant R2 as Cloudflare R2<br/>(SoT bucket)
    participant PF as Điều phối<br/>(Dagster — chưa dựng)
    participant LH as lakehouse-gold<br/>(LXC 202, worker)
    participant PG as Postgres<br/>(Gold, schema=prod)
    participant MP as MarketPulse<br/>(Mac mini)
    participant TG as Telegram Bot

    Note over SSI,Biz: Phiên giao dịch 09:00–15:00 ICT
    SSI->>Biz: Stream ticks/index/orderbook (SignalR)
    Biz->>Biz: Append WAL (per-channel, per-exchange)

    Note over Biz: 16:30 — cron compact WAL → Parquet
    Biz->>Biz: Compact WAL → Parquet (HOSE/HNX/UPCOM)

    Note over Biz,R2: 17:03 — cron R2 uploader
    Biz->>R2: PUT bronze/stock/2026-04-13/{channel}/{exchange}.parquet
    R2-->>Biz: 200 OK (ETag)
    Biz->>Biz: Mark WAL as shipped (local cleanup T+2)

    Note over PF,LH: 17:30 — trigger theo lịch (mục tiêu)
    PF->>LH: Dispatch flow run (ingest_daily, date=2026-04-13)
    LH->>R2: LIST bronze/stock/2026-04-13/**
    R2-->>LH: Object list (15 files, ~480 MB)
    LH->>R2: GET objects (parallel, boto3 get_object)
    R2-->>LH: Parquet bytes → Bronze staging

    LH->>LH: Polars transform Bronze → Silver<br/>(dedup, schema enforce, dtype cast)
    LH->>LH: Write Silver Parquet (local + object store)

    LH->>PG: dbt run --target prod (models/silver → models/gold)
    PG-->>LH: rows affected (upsert OK)
    LH->>PG: dbt test (schema + data quality)
    PG-->>LH: All tests PASS

    LH->>PF: Report state=Completed (run metadata)

    Note over MP,PG: 18:00 — MarketPulse scheduled job
    MP->>PG: SELECT from gold.daily_summary WHERE date=2026-04-13
    PG-->>MP: Aggregated rows (top movers, volume, breadth)
    MP->>MP: Polars/DuckDB analysis → claude -p render report
    MP->>TG: sendMessage (markdown report + charts)
    TG-->>Op: Daily report delivered
```

## Notes

- **Timing SLA**:
  - 17:03 ICT: R2 upload complete (bizfly cron, ssi-connection ADR-011)
  - 17:30 ICT: pipeline được trigger theo lịch (mục tiêu — hiện chạy tay)
  - 17:55 ICT: Gold tables ready (dbt run + test finish)
  - 18:00 ICT: MarketPulse report delivered
- **Idempotency**: Bronze uses R2 object key as natural dedup; Gold uses `ON CONFLICT (date, symbol, channel) DO UPDATE` theo ADR D3/D6.
- **Retention**: Bronze/Silver indefinite trên SeaweedFS; WAL trên bizfly T+2 ngày.
- **Failure modes**:
  - R2 timeout at step 14 → retry 3x exponential backoff → run state=Failed → xem `incident-r2-down.md`
  - Silver dedup drift > 5% → dbt test fail → flow fail + Telegram alert (không ghi Gold)
  - MarketPulse miss data → alert ở 18:05 nếu Gold rows < expected threshold
- **References**: ADR-2026-04-13 (D3 ingestion path, D4 Polars+dbt; orchestration → ADR 2026-08-05 Dagster), `data-lakehouse/CLAUDE.md` (quality gates), `ssi-connection` ADR-011 (R2 as SoT).
