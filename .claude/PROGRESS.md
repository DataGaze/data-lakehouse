# PROGRESS — Data Lakehouse

> Auto-generated: 2026-03-23 | Phase: B1

## Tổng quan

Data lakehouse platform cho thị trường tài chính VN. Kiến trúc 3 tầng: Bronze/Silver (SeaweedFS) + Gold (PostgreSQL) trên K3s home lab.

## Trạng thái hiện tại

- **Phase:** B1 (Building, ~10% tổng thể)
- **Tiến độ tổng:** Repo scaffolded, chưa có code thực thi
- **Hoạt động gần nhất:** Tạo repo structure, CLAUDE.md, configs

## Đã hoàn thành

- [x] Kiến trúc: Bronze/Silver (SeaweedFS) + Gold (PostgreSQL) — quyết định 2026-03-23
- [x] Repo structure: ingestion/, etl/, gold/, scripts/, tests/
- [x] CLAUDE.md, pyproject.toml, Makefile, .env.example
- [x] S3 client wrapper scaffold

## Đang làm

- [ ] Ingestion: sync_vps_to_bronze.py (VPS Parquet → SeaweedFS)
- [ ] ETL: bronze_to_silver.py (stock data)
- [ ] Gold: PostgreSQL schema design + Alembic migrations

## Chưa làm / Kế hoạch

- [ ] Deploy PostgreSQL trên K3s (05-Homelab)
- [ ] ETL: silver_to_gold.py (Parquet → PostgreSQL)
- [ ] Dockerfiles cho ETL/ingestion (05-Homelab)
- [ ] KEDA trigger: thay placeholder bằng real ETL image
- [ ] BĐS data source (W14+)
- [ ] Data API (FastAPI) cho stock bot
- [ ] Monitoring: data freshness, quality alerts

## Ghi chú

- Infra (K3s manifests, Dockerfiles) nằm ở repo 05-Homelab
- SSI Pipeline (source data) ở repo SSI_Connection trên VPS 14.225.0.201
- SeaweedFS đã chạy trên K3s, bucket `lakehouse` đã có
