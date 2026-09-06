# PROGRESS — Data Lakehouse

> Auto-generated: 2026-09-06 | Phase: B2.3

## Tổng quan

**Nền tảng lake dùng chung** (tách khỏi `BIZ01-datagaze` ngày 2026-08-05 vì là hạ tầng nhiều
venture thuê chung, không phải tài sản của một venture): SeaweedFS Bronze/Silver, Postgres Gold,
lược đồ, chất lượng dữ liệu. Nhiều nguồn: `stock` (đang có), `bds` (kế hoạch).

Kiến trúc: Bizfly → R2 (SoT) → Bronze SeaweedFS → Silver → Gold Postgres trên LXC 202.

## Trạng thái hiện tại

- **Phase:** B2.3 (Building, ~40% tổng thể)
- **Tiến độ tổng:** **Tầng truy vấn (T3) đã chạy đủ hai giai đoạn** — Trino 483 trên LXC 220,
  ba catalog PostgreSQL chỉ đọc + catalog Iceberg ghi được trên SeaweedFS, Superset nối cả bốn.
  Tầng điều phối (Dagster), catalog nghiệp vụ (OpenMetadata) và giám sát vẫn **chưa có**
- **Hoạt động gần nhất:** 2026-09-06 — Trino giai đoạn 2: catalog Iceberg trên SeaweedFS

## Đã hoàn thành

### Trino giai đoạn 2 — Iceberg trên SeaweedFS (2026-09-06)
- [x] **Đo trước khi dựng**: bucket `lakehouse` chỉ 24.768 B — Bronze/Silver **rỗng**, dữ liệu
      thật nằm ở PostgreSQL Gold. Giai đoạn 2 vì thế là dựng **đường ghi**, không phải mở đường
      đọc hồ sẵn có; tiêu chí nghiệm thu đổi theo
- [x] **Catalog JDBC trên PostgreSQL 204**, không dựng Hive metastore: CSDL `iceberg_catalog`,
      vai `iceberg_cat`, lược đồ từ `OPS01-homelab/data-infra/iceberg/catalog-schema.sql`
- [x] **Kho tệp `s3://lakehouse/warehouse/`** qua `fs.native-s3.enabled`, danh tính SeaweedFS
      `trino` chỉ có quyền trong đúng bucket `lakehouse` — Trino giờ là bên GHI mà vẫn chưa có
      xác thực, nên phạm vi hỏng bị chặn ở tầng lưu trữ (TD-43 nâng hạng, TD-44, TD-45)
- [x] **Vào role ansible**: template `catalog-iceberg.properties.j2`, gate ba bí mật riêng,
      `trino_expected_catalogs` để healthcheck đòi luôn `iceberg`
- [x] **Nghiệm thu 6 phép + 2 phép phụ**: CTAS 47.024 dòng từ gold sang Iceberg, đọc lại khớp;
      Parquet 494.706 B kèm đủ manifest/snapshot/stats trên S3; một câu nối Iceberg (S3) với
      telemetry (PG 204); Superset chạy được qua nguồn `Trino - iceberg`

### Trino giai đoạn 1 — tầng truy vấn liên nguồn (2026-09-06)
- [x] **LXC 220 `trino`** trên promax: Debian 13, IP tĩnh 192.168.0.125, 6 nhân / 16 GB / 40 GB,
      TUN cho tailnet. Địa chỉ chọn sau khi đo trống bằng cả hai bằng chứng (ping im lặng và
      `ip neigh` trả FAILED)
- [x] **Trino 483 native**, không container: tarball GitHub Releases ghim sha256, kèm Temurin
      JDK 25.0.4.1+1 ghim vào kho `adoptium/temurin25-binaries` — kho **chỉ chứa dòng 25**, nên
      `apt` không trượt được sang Java 26 mà Trino 483 từ chối chạy
- [x] **Ba catalog PostgreSQL** qua vai chỉ đọc `trino_ro`: `gold` (`stock_market`, LXC 202),
      `telemetry` (`llm_logs`, LXC 204), `nocodb` (`nocodb_content` gồm schema `toeic`, LXC 204)
- [x] **Role ansible đủ năm tệp tasks** trong `OPS01-homelab`, có mục trong `inventory.yml`,
      `versions.yml` và hai bảng guard của `provision.yml`
- [x] **Lọc mạng `nftables`**: cổng 8080 chỉ mở cho Superset (205), máy điều khiển ansible và
      dải tailnet. Trino chưa có xác thực — nợ ghi ở `OPS01-homelab/docs/tech-debt.md` TD-43
      kèm điều kiện nâng cấp viết sẵn
- [x] **Superset nối lại**: `trino[sqlalchemy]==0.339.0` vào venv (SQLAlchemy giữ nguyên 1.4.54),
      ba nguồn `Trino - gold` / `- telemetry` / `- nocodb`
- [x] **Nghiệm thu bằng máy, 7 phép**: `SHOW CATALOGS` đủ bốn; `daily_ohlcv` đếm 47.024 khớp
      `psql`; một câu `FULL OUTER JOIN` đọc cả hai cụm (gold 47.024, telemetry 240.786);
      `CREATE TABLE` bị từ chối; LXC 217 ngoài danh sách nhận `http=000` còn Superset nhận `200`;
      khởi động lại xanh sau 5 giây; Superset lấy được dữ liệu thật qua Trino
- [x] Thiết kế: `docs/superpowers/specs/2026-09-06-trino-deployment-design.md`.
      Kế hoạch: `OPS01-homelab/docs/superpowers/plans/2026-09-06-trino-deployment.md`.
      Cài đặt: `OPS01-homelab/services/trino/INSTALL.md`


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
| 3 | Dựng lại Iceberg catalog trên PostgreSQL 204 | **xong 2026-09-06** — CSDL `iceberg_catalog`, lược đồ áp tay từ `catalog-schema.sql` |
| 4 | **Dagster** | chưa — ADR đã chốt hướng, chờ chốt phương án mô hình hóa |
| 5 | Prometheus + exporter + cảnh báo | chưa |
| 6 | Trino | **xong 2026-09-06** — LXC 220, native, ba catalog PostgreSQL + catalog Iceberg |
| 7 | OpenMetadata (phương án B) | chưa |
| 8 | Superset (đang chạy, cần nối lại sau khi có Trino) | **đã nối lại 2026-09-06** |

### Còn mở, cần quyết
- ~~Trino chạy ở đâu khi không còn K3s~~ — đã đáp 2026-09-06: LXC 220 riêng, cài native
- ~~Đích sao lưu đặt ở đâu~~ — đã đáp 2026-09-06: `/mnt/hdd` trên promax. Chấp nhận **có
  biết** rằng đó là `/dev/sda`, cùng đĩa vật lý với dữ liệu SeaweedFS, nên chỉ chống được lỗi
  vận hành chứ không chống được hỏng đĩa. Ghi ở `OPS01-homelab/docs/tech-debt.md` TD-45
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
