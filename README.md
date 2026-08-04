# Data Lakehouse Platform

> **Infra layer** cho DataGaze data platform — K3s manifests, Postgres DDL, SeaweedFS setup, Terraform/Ansible.
> Runtime logic (dbt models, Polars transforms, tầng điều phối) nằm ở repo `data-pipeline` (separate, per ADR D1).

## Architecture

```
Bizfly VPS (ssi-connection)   Cloudflare R2 (SoT)    lakehouse-gold LXC 202
SSI SignalR → WAL → Parquet ─▶  s3://lakehouse/ ────▶ Bronze (SeaweedFS)
                                 ingestion/YYYY-MM-DD    │
                                                         ▼
                                           Silver (SeaweedFS) ─── Polars transform
                                                         │
                                                         ▼
                                           Gold (Postgres datagaze.prod) ─── dbt run
                                                         │
                                                         ▼
                                              MarketPulse / Consumers
```

**Orchestrator:** chưa có. Prefect gỡ bỏ 2026-08-05 sau 4 tháng với 0 flow run; Dagster đang được
dựng thay thế (xem [ADR 2026-08-05](docs/adr/2026-08-05-retire-prefect-adopt-dagster.md)).
Tới khi Dagster chạy, ETL chỉ chạy khi gọi tay. Ingestion path via R2 (ADR D3), không rsync trực tiếp bizfly.

## Quick Start (infra provisioning)

```bash
# Chỉ áp dụng phần infra của repo này (K3s, DB schema, storage)
make setup                  # install tools
cp .env.example .env        # fill R2 + Postgres credentials (hoặc SOPS decrypt)
make migrate                # apply Postgres DDL
make validate               # verify SeaweedFS + Postgres reachable

# Để chạy ETL/pipeline → xem repo data-pipeline
```

## Structure

```
terraform/     Proxmox + Cloudflare + K3s IaC (planned)
k8s/           K3s manifests (KEDA, cronjobs)
gold/          PostgreSQL migrations (Alembic/Flyway)
ingestion/     Reference ingestion schema (runtime ở data-pipeline)
etl/           Reference ETL schema (runtime ở data-pipeline)
scripts/       Provisioning + backup utilities
tests/         Infra smoke tests
docs/          FAANG-grade docs (xem bên dưới)
```

## 📚 Documentation

| Doc | Purpose | Audience |
|-----|---------|----------|
| [Architecture](docs/architecture.md) | System overview, components, data flow | Everyone |
| [Data Contract](docs/data-contract.md) | Schema Bronze/Silver/Gold, types, versioning | Dev, Consumer |
| [Runbook](docs/runbook.md) | Operations + on-call playbook | Ops, On-call |
| [SLA/SLO](docs/sla.md) | Service level targets + error budget | Stakeholder, Ops |
| [Security](docs/security.md) | Threat model, secrets, RBAC | Dev, Security |
| [Cost Model](docs/cost.md) | Infra cost breakdown + projection | Stakeholder |
| [Onboarding](docs/onboarding.md) | New dev setup guide | New joiner |
| [ADR — Platform Decisions](docs/adr/2026-04-13-platform-decisions.md) | 7 key decisions D1-D7 | Architect, Dev |

### Sequence Diagrams

- [Ingestion Flow](docs/sequences/ingestion-flow.md)
- [Backfill Flow](docs/sequences/backfill-flow.md)
- [Incident Response — R2 Down](docs/sequences/incident-r2-down.md)

## Data Sources

| Source | Status | Frequency | Volume |
|--------|--------|-----------|--------|
| Stock (SSI) | Production | Daily 17:00 | ~50MB/day |
| BĐS | Planned (W14+) | TBD | TBD |

## Infrastructure

- **K3s cluster:** 2 nodes (home lab)
- **lakehouse-gold LXC 202** (Proxmox, 192.168.0.113): Postgres 16 Docker `postgres-gold` (`prefect-worker` đã gỡ 2026-08-05)
- **prefect-server LXC 201** (192.168.0.112): service đã ngừng, container giữ để tái dùng cho Dagster
- **SeaweedFS:** S3-compatible object storage (Bronze + Silver)
- **Cloudflare R2:** Durable archive + source of truth (ADR D3)
- **Bizfly VPS:** Producer only (ssi-connection) — không consumer trực tiếp
- **Tailscale mesh:** zero-trust between hosts
- **KEDA:** Event-driven autoscaling for ETL jobs (planned)
