# Data Lakehouse Platform

Data lakehouse cho thị trường tài chính Việt Nam, chạy trên K3s home lab.

## Architecture

```
Source (VPS)          Bronze (SeaweedFS)       Silver (SeaweedFS)       Gold (PostgreSQL)
SSI Pipeline    →     Raw Parquet         →    Cleaned Parquet     →   Aggregated Tables
~50MB/day             as-is from source        dedup + validated       analytics-ready
```

## Quick Start

```bash
# Setup
make setup
cp .env.example .env  # Fill in credentials

# Run pipeline
make ingest-stock     # VPS → Bronze
make etl-stock        # Bronze → Silver → Gold

# Validate
make validate
make test
```

## Structure

```
ingestion/     Source → Bronze (SeaweedFS S3)
etl/           Bronze → Silver → Gold (ETL pipelines)
gold/          PostgreSQL migrations + views
scripts/       Dev/ops utilities
tests/         Test suite
```

## Data Sources

| Source | Status | Frequency | Volume |
|--------|--------|-----------|--------|
| Stock (SSI) | Production | Daily 17:00 | ~50MB/day |
| BĐS | Planned (W14+) | TBD | TBD |

## Infrastructure

- **K3s cluster:** 2 nodes (home lab)
- **SeaweedFS:** S3-compatible object storage (Bronze + Silver)
- **PostgreSQL:** Relational database (Gold)
- **KEDA:** Event-driven autoscaling for ETL jobs
- **Infra configs:** See [05-Homelab](https://github.com/DataGaze/05-Homelab) repo
