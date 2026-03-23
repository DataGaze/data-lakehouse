# CLAUDE.md — Data Lakehouse Platform

## Tổng quan

Data Lakehouse cho thị trường tài chính Việt Nam. Thu thập, xử lý, và phục vụ dữ liệu chứng khoán (và BĐS trong tương lai) qua kiến trúc 3 tầng:

- **Bronze:** Raw Parquet trên SeaweedFS (S3-compatible) — dữ liệu nguyên gốc từ source
- **Silver:** Cleaned Parquet trên SeaweedFS — đã dedup, validate, enforce schema
- **Gold:** PostgreSQL — aggregated, analytics-ready, phục vụ apps (stock bot, dashboard, API)

## Kiến trúc

```
VPS (SSI Pipeline)                    K3s Cluster (Home Lab)
┌──────────────┐                     ┌─────────────────────────┐
│ SSI SignalR   │                     │ SeaweedFS (S3)          │
│ → WAL → Parq │──── ingestion/ ────▶│ bronze/stock/{date}/    │
│ → CF R2      │                     │ silver/stock/{date}/    │
└──────────────┘                     ├─────────────────────────┤
                                     │ ETL (KEDA CronJob)      │
                                     │ etl/ code runs here     │
                                     ├─────────────────────────┤
                                     │ PostgreSQL (Gold)       │
                                     │ gold/ migrations here   │
                                     └─────────────────────────┘
```

## Quy tắc

### Code
- Python 3.11+, type hints bắt buộc
- Polars cho data processing (KHÔNG dùng pandas)
- boto3 cho S3 (SeaweedFS compatible)
- psycopg2 / SQLAlchemy cho PostgreSQL
- Alembic cho database migrations
- `pathlib.Path` cho file paths

### Naming
- Files: `snake_case.py`
- Folders: `snake_case/`
- SQL migrations: `NNN_description.py` (Alembic auto)
- SQL views: `snake_case.sql`
- Config: `config.yaml`

### Data Zones

| Zone | Storage | Format | Retention | Mô tả |
|------|---------|--------|-----------|-------|
| Bronze | SeaweedFS `bronze/` | Parquet (as-is) | Indefinite | Raw từ source, không sửa đổi |
| Silver | SeaweedFS `silver/` | Parquet (cleaned) | Indefinite | Dedup, validate, schema enforced |
| Gold | PostgreSQL | Tables | Indefinite | Aggregated, queryable by apps |

### SeaweedFS S3 Paths

```
lakehouse/bronze/stock/{YYYY-MM-DD}/{channel}/{exchange}.parquet
lakehouse/silver/stock/{YYYY-MM-DD}/{channel}/{exchange}.parquet
```

Channels: `ticks`, `index`, `misc`, `orderbook`, `backfill`
Exchanges: `HOSE`, `HNX`, `UPCOM`

### Environment Variables

```bash
# SeaweedFS S3
S3_ENDPOINT=http://192.168.0.102:30333
S3_ACCESS_KEY=***
S3_SECRET_KEY=***
S3_BUCKET=lakehouse

# PostgreSQL (Gold)
PG_HOST=***
PG_PORT=5432
PG_DATABASE=stock_market
PG_USER=***
PG_PASSWORD=***

# VPS (Source)
VPS_HOST=14.225.0.201
VPS_PORT=2222
VPS_USER=trongnq
VPS_DATA_DIR=/home/trongnq/Projects/SSI_Conection/data/export
```

### Quality Gates
1. Bronze: file tồn tại + đúng format Parquet + size > 0
2. Silver: schema match + no duplicates + row count delta < 5%
3. Gold: migration thành công + row count khớp Silver

### Infra
- K3s manifests cho data workloads nằm ở repo `05-Homelab`
- Dockerfiles cho ETL/ingestion cũng ở `05-Homelab/docker/`
- Repo này chỉ chứa **code** — không chứa K8s manifests hay Dockerfiles

## Lệnh nhanh

```bash
make ingest-stock    # Chạy ingestion: VPS → Bronze
make etl-stock       # Chạy ETL: Bronze → Silver → Gold
make test            # Chạy tests
make validate        # Validate Bronze data integrity
make migrate         # Chạy Alembic migrations
make backfill        # Backfill historical data
```
