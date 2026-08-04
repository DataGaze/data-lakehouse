# Incident Response — Cloudflare R2 Unreachable

> Version: 1.0 | Last Updated: 2026-04-13 | Status: Draft

## Overview

Khi R2 không reachable tại thời điểm pull (17:30 ICT), flow retry với exponential backoff, fail soft sau 3 lần, alert operator. Operator quyết định wait-out hoặc fallback sang rsync trực tiếp từ bizfly. Post-incident verify data completeness.

## Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant PF as Điều phối<br/>(Dagster — chưa dựng)
    participant LH as lakehouse-gold<br/>(LXC 202, worker)
    participant R2 as Cloudflare R2
    participant Biz as Bizfly VPS<br/>(ssi-connection, fallback)
    participant PG as Postgres<br/>(Gold, schema=prod)
    participant TG as Telegram Bot
    participant CF as status.cloudflare.com

    Note over PF,LH: 17:30 — Daily ingest trigger
    PF->>LH: Dispatch flow ingest_daily (date=2026-04-13)
    LH->>R2: LIST bronze/stock/2026-04-13/**
    R2-->>LH: HTTP 500 / timeout

    rect rgb(255, 235, 235)
    Note over LH,R2: Retry with exponential backoff
    LH->>R2: Retry #1 (after 30s)
    R2-->>LH: HTTP 500
    LH->>R2: Retry #2 (after 60s)
    R2-->>LH: timeout (60s)
    LH->>R2: Retry #3 (after 120s)
    R2-->>LH: HTTP 503
    end

    LH-->>PF: Task state=Failed<br/>(error: R2_UNREACHABLE, 3 retries exhausted)
    PF->>PF: Flow state=Failed, halt downstream tasks
    PF->>TG: ALERT flow ingest_daily FAILED<br/>reason: R2_UNREACHABLE<br/>date=2026-04-13, retries=3

    Note over Op,TG: Human decision point — T0+5min
    TG-->>Op: Incident notification
    Op->>TG: /ack (acknowledge, on-call)
    Op->>CF: Open status.cloudflare.com
    CF-->>Op: "R2 Storage — degraded performance (APAC)"

    alt Wait strategy (ETA < 30min)
        Op->>PF: Manual retry after 20min<br/>chạy lại pipeline cho ngày đó
        PF->>LH: Re-dispatch flow
        LH->>R2: LIST (R2 recovered)
        R2-->>LH: 200 OK, object list
        LH->>LH: Proceed normal Bronze→Silver→Gold
    else Fallback strategy (ETA > 30min or unknown)
        Op->>Biz: ssh bizfly<br/>verify /home/trongnq/Projects/SSI_Conection/data/export/2026-04-13/ exists
        Biz-->>Op: Parquet files present (15 files, 478 MB)
        Op->>LH: ssh lakehouse-gold<br/>trigger fallback rsync:<br/>python -m ingestion.rsync_bizfly --date 2026-04-13
        LH->>Biz: rsync -avz bizfly:~/SSI_Conection/data/export/2026-04-13/ /tmp/bronze_staging/
        Biz-->>LH: Parquet files transferred
        LH->>LH: Bronze→Silver→Gold (same transforms)
        LH->>PG: dbt run + test (target=prod)
        PG-->>LH: PASS
    end

    Note over LH,PG: Post-incident verification
    LH->>PG: SELECT date, count(*) FROM gold.daily_summary<br/>WHERE date='2026-04-13'
    PG-->>LH: rows=1618 (expected ~1620)
    LH->>LH: Compare vs Silver row count & prior day baseline
    LH->>TG: Incident resolved<br/>mode: {wait|rsync}, rows=1618, delta=-0.12%<br/>RCA: see runbook §Post-mortem template
    TG-->>Op: Confirmation

    Op->>Op: Write post-mortem (RCA + prevention)
```

## Notes

- **Timing SLA**:
  - Detection: T0 = 17:30 ICT (flow start), alert gửi lúc T0+~4m (sau 3 retries)
  - Acknowledge: trong 10 phút (operator on-call)
  - Resolution target: trước 20:00 ICT để MarketPulse catch up cùng ngày
- **Retry policy** (mục tiêu, khai ở tầng Dagster): 3 lần, delay [30, 60, 120] giây (exponential, capped). Không retry với lỗi 4xx (client error — fail fast).
- **Decision criteria wait vs fallback**:
  - Wait: CF status báo ETA recovery < 30 phút, < 15:00 UTC của cùng ngày
  - Fallback rsync: ETA > 30 phút, hoặc status không rõ, hoặc đã 19:00 ICT
- **Failure modes**:
  - Bizfly cũng unreachable → escalate user, không có path khác (single producer, P1 incident)
  - Rsync completed nhưng row count delta > 5% → dbt test `freshness` fail → treat as partial ingest, flag trong post-mortem
  - R2 recover nhưng dữ liệu 2026-04-13 chưa được bizfly upload xong → check bizfly cron log, có thể phải chờ hoặc force upload thủ công
- **Prevention followup**: xem xét dual-write bizfly → R2 + bizfly → lakehouse direct (nếu R2 outage lặp lại > 2 lần/quý). Tracked ở ADR backlog.
- **References**: ADR-2026-04-13 (D3 ingestion path), `ssi-connection` ADR-011 (R2 as SoT, bizfly là producer), `data-lakehouse/CLAUDE.md` (Production awareness — VPS 24/7).
