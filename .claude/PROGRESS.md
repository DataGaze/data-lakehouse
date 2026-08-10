# PROGRESS — Data Lakehouse

> Auto-generated: 2026-08-05 | Phase: B1.4

## Tổng quan

**Nền tảng lake dùng chung** (tách khỏi `BIZ01-datagaze` ngày 2026-08-05 vì là hạ tầng nhiều
venture thuê chung, không phải tài sản của một venture): SeaweedFS Bronze/Silver, Postgres Gold,
lược đồ, chất lượng dữ liệu. Nhiều nguồn: `stock` (đang có), `bds` (kế hoạch).

Kiến trúc: Bizfly → R2 (SoT) → Bronze SeaweedFS → Silver → Gold Postgres trên LXC 202.

## Trạng thái hiện tại

- **Phase:** B1.4 (Building, ~25% tổng thể)
- **Tiến độ tổng:** ADR + docs + Superset đang chạy + Prefect đã gỡ; tầng điều phối, truy vấn,
  catalog, giám sát đều **chưa có**
- **Hoạt động gần nhất:** 2026-08-05 — gỡ Prefect toàn hệ thống (9 commit / 8 repo) + khung
  nâng cấp 6 tầng dựa trên số đo hạ tầng thật

## Đã hoàn thành

### Gỡ Prefect + chốt hướng Dagster (2026-08-05)
- [x] **Đo trước khi làm:** Prefect chạy 2026-04-02 → 2026-08-05 với **0 deployment, 0 flow run**
      — chưa bao giờ vào vận hành, nên đây là teardown chứ không phải migration
- [x] `prefect-server` (LXC 201) + `prefect-worker` (LXC 202): stopped + disabled
- [x] **ADR** `docs/adr/2026-08-05-retire-prefect-adopt-dagster.md` — lý do gỡ, ba phương án đã
      cân (giữ Prefect / systemd timer / Dagster), và tiêu chí nghiệm thu là *một chu kỳ ETL thật
      chạy xanh*, không phải "cài xong"
- [x] ADR 2026-04-13 giữ nguyên chữ, gắn nhãn superseded ở D4 + Status
- [x] 12 file docs cập nhật: architecture, runbook, security, sla, onboarding, sequences (3),
      cost, data-contract, README
- [x] Code `stock-data-pipeline` gỡ sạch Prefect (101/101 test pass); toolkit `agentsmith` gỡ
      `prefect-run.sh` (350/350 test pass); tài liệu 6 repo khác theo sau

### Khung nâng cấp nền tảng (2026-08-05, phiên tối)
- [x] `docs/2026-08-05-lakehouse-upgrade-framework__ai1.md` — khung 6 tầng + thứ tự thi công
- [x] `docs/2026-08-05-catalog-metadata-probe__ai1.md` — khảo sát catalog/metadata
- [x] Chốt: Iceberg làm định dạng bảng; OpenMetadata phương án B (dùng chung OpenSearch 213 +
      PostgreSQL 204, bỏ Airflow); giữ SeaweedFS không chuyển MinIO; loại DuckLake
- [x] **Đo được:** VM 106, cả 2 node K3s, và LXC 201 đều không còn tồn tại trên promax

### Superset Deployment (2026-04-14)
- [x] Superset 4.1.4 native trên LXC 205 (Python 3.11.12, Gunicorn, Celery, Redis, PG metadata)
- [x] PG Gold connected (LAN 192.168.0.113:5432/stock_market)
- [x] Tailscale trên LXC 205 (100.104.77.58) — TUN device configured
- [x] systemd services: superset-web + superset-worker (auto-start)
- [x] Install script `scripts/install_superset.sh` (9 bước, idempotent)
- [x] MCP server `mcp/superset-mcp/` (server.py + client.py, 10 tool)
- [x] Seed dashboards: 4 dataset, 7 chart, 3 dashboard
- [x] Vault `infra/superset` v3 — toàn bộ credential + IP
- [x] Docs: `docs/superset-setup.md` + `docs/superset-mcp.md`

### Docs & Architecture (2026-04-13)
- [x] Kiến trúc: Bronze/Silver (SeaweedFS) + Gold (Postgres) — quyết định 2026-03-23
- [x] Repo structure: ingestion/, etl/, gold/, scripts/, tests/
- [x] CLAUDE.md, pyproject.toml, Makefile, .env.example
- [x] **ADR D1-D7**: repo split, LXC rename, R2 ingestion, orchestration+Polars+dbt, env config,
      schema separation, no CI/CD
- [x] **docs/** — architecture, runbook, data-contract, SLA, security, cost, onboarding
- [x] **docs/sequences/** — ingestion-flow, backfill-flow, incident-r2-down

### PG Gold Data (2026-04-14)
- [x] Backfill VPS → PG Gold: daily_ohlcv 47.024 dòng, ticks 82.399.218 dòng (25 ngày)

## Đang làm

- [ ] **Chốt phương án mô hình hóa Dagster** — A (job/op lift-and-shift) / B (asset-centric thuần)
      / **C (asset mỏng bọc code thuần — khuyến nghị)**. Đã trình cho user, chưa có quyết định.
      Chốt xong mới viết spec, chưa đụng hạ tầng
- [ ] Sửa ADR 2026-08-05 mục Consequences: câu "giữ lại container 201" đã sai (container bị xóa)

## Chưa làm / Kế hoạch

### Thứ tự thi công (theo `docs/2026-08-05-lakehouse-upgrade-framework__ai1.md` §6.1)

| Thứ tự | Việc | Trạng thái |
|---|---|---|
| 0a | Khai lịch `vzdump` toàn bộ LXC, đích **ngoài** `/dev/sda` | chưa — **hiện không có job sao lưu nào** |
| 0b | `pg_dump` định kỳ cho 204 + 202; sao lưu Vault trên 200 | chưa |
| 1 | SeaweedFS vào as-code + xác minh khôi phục thật | chưa — đang chạy **không có role ansible** |
| 2 | Loki + Grafana + agent thu log | chưa |
| 3 | Dựng lại Iceberg catalog trên PostgreSQL 204 | chưa — có sẵn `data-infra/iceberg/catalog-schema.sql` |
| 4 | **Dagster** | chưa — ADR đã chốt hướng, chờ chốt phương án mô hình hóa |
| 5 | Prometheus + exporter + cảnh báo | chưa |
| 6 | Trino | chưa — phải chọn nơi chạy vì K3s không còn |
| 7 | OpenMetadata (phương án B) | chưa |
| 8 | Superset (đang chạy, cần nối lại sau khi có Trino) | một phần |

### Còn mở, cần quyết
- Trino chạy ở đâu khi không còn K3s (chặn bước 6, 8)
- Prometheus chạy ở đâu, thu đích nào; cảnh báo gửi đi đâu (chặn bước 5)
- Retention log 7 hay 30 ngày
- Tên bucket cho nguồn `messaging` (chặn phần ghi bronze của 01-Tracking)

### Việc tồn từ trước
- [ ] Fix `scripts/install_superset.sh` Step 9 (`add_pg_gold`) — rewrite curl → Python requests
- [ ] Fix `write_config()` — thêm `RESULTS_BACKEND` vào template
- [ ] Test MCP server live trong Claude Code
- [ ] LXC 202 rename `stock-gold` → `lakehouse-gold`; PG rename `stock_market` → `datagaze`
- [ ] Repo rename `stock-data-pipeline` → `data-pipeline`; gom 2 code base ingestion chồng nhau
- [ ] Alembic migrations, SOPS + `.sops.yaml`
- [ ] PG Gold index: `CREATE INDEX idx_ticks_time ON ticks (tick_time)`

## Ghi chú

- **Không có scheduler nào đang chạy.** ETL chỉ chạy khi gọi tay:
  `python -m ingestion.r2_to_bronze --date YYYY-MM-DD` rồi `python -m etl.orchestrator --source stock`
- **Dagster không nhẹ hơn Prefect** — cần webserver + daemon + Postgres metadata. Chọn nó vì
  partition/backfill và lineage, không vì gọn. Nếu chỉ cần gọn thì `systemd timer` mới đúng
- **Tài liệu vận hành mô tả Prefect được giữ lại có chủ đích**, đánh dấu hết hiệu lực bằng banner
  + nhãn từng mục. Viết lại khi Dagster chạy thật, để không thay tài liệu hư cấu bằng tài liệu khác
- **Lệch phase cần chốt:** `repo_categories.json` ghi `B1`, PROGRESS trước đó ghi `B2.3`. File này
  đang dùng `B1.4` theo registry. Nếu tiến độ thực là B2 thì cập nhật cả hai
- **Địa chỉ S3 trong `CLAUDE.md` của repo này sai:** ghi `192.168.0.102:30333` (nút K3s đã chết).
  Đường đúng: `192.168.0.200:8333`
- Python 3.11 only cho Superset 4.x; `setuptools<75`; LXC-to-LXC dùng LAN không dùng Tailscale IP
- SSI Pipeline (producer) ở `ssi-connection` trên Bizfly VPS — đừng động
