# PROGRESS — Data Lakehouse

> Auto-generated: 2026-04-13 | Phase: B1.2

## Tổng quan

**Infra layer** cho DataGaze data platform (ADR D1 — 2026-04-13): K3s manifests, Postgres DDL, SeaweedFS setup, Terraform/Ansible. Runtime logic (Prefect flows, dbt, Polars) sang repo `data-pipeline` (rename từ `stock-data-pipeline`).

Kiến trúc: Bizfly → R2 (SoT) → Bronze SeaweedFS → Silver → Gold Postgres `datagaze.prod` trên LXC 202 lakehouse-gold.

## Trạng thái hiện tại

- **Phase:** B1.2 (Building, ~12% tổng thể)
- **Tiến độ tổng:** ADR + full documentation bundle, infra chưa provisioned
- **Hoạt động gần nhất:** Tạo 7 docs FAANG-grade + 3 sequence diagrams + ADR 7 decisions

## Đã hoàn thành

- [x] Kiến trúc: Bronze/Silver (SeaweedFS) + Gold (Postgres) — quyết định 2026-03-23
- [x] Repo structure: ingestion/, etl/, gold/, scripts/, tests/
- [x] CLAUDE.md, pyproject.toml, Makefile, .env.example
- [x] S3 client wrapper scaffold
- [x] **ADR D1-D7** (2026-04-13): repo split, LXC rename, R2 ingestion, Prefect+Polars+dbt, env config, schema separation, no CI/CD
- [x] **docs/architecture.md** (214 dòng) — overview + mermaid component diagram + scalability path
- [x] **docs/runbook.md** (801 dòng) — 5 incident playbooks + SEV1/2/3 + recovery procedures
- [x] **docs/data-contract.md** (569 dòng) — schema Bronze/Silver/Gold (15 tables) + SemVer versioning
- [x] **docs/sla.md** (270 dòng) — 18 SLOs + 3 SLAs + error budget
- [x] **docs/security.md** (423 dòng) — STRIDE + 13 secrets inventory + SOPS + Tailscale ACL
- [x] **docs/cost.md** (220 dòng) — $54.54/tháng estimate + projection + optimization opportunities
- [x] **docs/onboarding.md** (274 dòng) — 15-phút dev setup path
- [x] **docs/sequences/** — ingestion-flow, backfill-flow, incident-r2-down (80 interactions)
- [x] README updated với docs index + infra rename lakehouse-gold

## Đang làm

- [ ] LXC 202 rename `stock-gold` → `lakehouse-gold` (Proxmox `pct set 202 --hostname`)
- [ ] Postgres DB rename `stock_market` → `datagaze` + schema split `prod` + `dbt_{user}_dev`
- [ ] Repo rename `stock-data-pipeline` → `data-pipeline`

## Chưa làm / Kế hoạch

- [ ] Terraform module cho Proxmox LXC (replace markdown docs trong 02-MyPlan)
- [ ] Alembic migrations setup (Postgres DDL)
- [ ] K3s manifests (KEDA, cronjobs)
- [ ] Provisioning scripts (bootstrap lakehouse-gold từ zero)
- [ ] Infra smoke tests (connectivity, SeaweedFS, Postgres)
- [ ] SOPS setup + .sops.yaml (secrets encrypt)

## Ghi chú

- Runtime pipeline (R2 → Bronze → Silver → Gold) implement ở repo `data-pipeline` (sẽ rename)
- SSI Pipeline (producer) ở repo `ssi-connection` trên Bizfly VPS 14.225.0.201 — đừng động
- SeaweedFS đã chạy trên K3s, bucket `lakehouse` đã có
- Docs index: xem `README.md` section "📚 Documentation"
