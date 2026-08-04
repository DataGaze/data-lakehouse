# ADR — Data Platform Decisions (2026-04-13)

## Status

Accepted (2026-04-13). Phần orchestration được thay thế bởi
[ADR 2026-08-05 — Gỡ Prefect, chuyển sang Dagster](./2026-08-05-retire-prefect-adopt-dagster.md).

Mọi nhắc tới Prefect trong tài liệu này là bản ghi của quyết định tại thời điểm 2026-04-13,
giữ nguyên có chủ đích. Đừng đọc chúng như mô tả hệ thống hiện tại.

## Context
DataGaze bắt đầu mở rộng từ chỉ stock sang multi-domain (stock + BĐS + future). Cần chốt kiến trúc data platform để tránh drift + tech debt từ sớm.

## Decisions

### D1. Tách 2 repo rõ vai trò
- **`data-lakehouse`** = Infra layer: Terraform/Ansible, K8s/K3s manifests, Postgres DDL/migrations, SeaweedFS setup, network/storage declaration. Ít code logic.
- **`data-pipeline`** (rename từ `stock-data-pipeline`) = Runtime logic: Prefect flows, Polars transforms, dbt models, ingestion, quality checks. Code chạy hàng ngày.

### D2. LXC naming
- `stock-gold` → **`lakehouse-gold`** (LXC 202, Proxmox). Giữ medallion pattern, bỏ "stock" để mở rộng scope đa domain.

### D3. Ingestion path
- Data kéo **qua R2**, không rsync trực tiếp từ bizfly.
- Lý do: R2 đã là SoT (ADR-011 của ssi-connection), decoupling bizfly, egress Cloudflare free, scalable cho nhiều consumer.
- Flow: `bizfly cron 17:03 upload → R2` → `lakehouse-gold Prefect 17:30 pull từ R2 → Bronze → Silver → Gold`.

### D4. Orchestration + transform stack

> **Phần orchestration đã bị thay thế** bởi [ADR 2026-08-05](./2026-08-05-retire-prefect-adopt-dagster.md):
> Prefect gỡ bỏ sau khi chạy 4 tháng với 0 deployment và 0 flow run; chuyển sang Dagster.
> Phần Polars và dbt dưới đây vẫn có hiệu lực.

- ~~**Prefect 3**: orchestration (đã deploy LXC 201 prefect-server, worker LXC 202)~~
- **Polars**: Bronze → Silver (Parquet transform)
- **dbt**: Silver → Gold (SQL transformations trên Postgres)
- Pattern: `Polars Bronze→Silver → dbt run Silver→Gold`, do tầng điều phối gọi

### D5. Env separation (2 envs: dev + prod)
- **Không** tách folder prod/dev. Dùng config-per-env (industry standard Y).
- Structure `data-pipeline/`:
  ```
  data-pipeline/
  ├── ingestion/                   # R2 → Bronze (Python + boto3)
  ├── transform/                   # Bronze → Silver (Polars)
  ├── dbt/
  │   ├── models/silver/
  │   ├── models/gold/
  │   ├── profiles.yml             # targets: dev, prod
  │   └── dbt_project.yml
  ├── flows/                       # Prefect deployments per env
  ├── environments/
  │   ├── dev.env
  │   └── prod.env
  └── Makefile                     # make run ENV=prod
  ```

### D6. Schema separation (cùng Postgres, khác schema)
- Database `datagaze` (không còn `stock_market`)
- Schema `prod` — Prefect production flow ghi vào
- Schema `dbt_{user}_dev` — developer chạy local dbt ghi vào (dbt native convention)
- **Không dùng 2 database hoặc 2 LXC** cho dev/prod — tốn ops, dbt đã support target-based schema native

### D7. Testing strategy — không CI/CD
- Scale nhỏ (solo dev), bỏ qua GitHub Actions
- Thay bằng 3 cơ chế local-first:
  1. **Pre-commit hook** (`pre-commit install`) — auto pytest + dbt parse trước commit, chặn quên
  2. **Data test trong Prefect flow** — `dbt test` là step sau `dbt run`, fail thì flow fail + Telegram alert
  3. **Makefile `make deploy` gate** — chạy `make check` (pytest + dbt test + mypy) trước khi `prefect deployment apply`
- Pre-commit là **must-have**, 2 cái còn lại là bonus nhưng nên làm

## Consequences

**Positive:**
- 2 repo role rõ, infra và runtime không lẫn
- dbt + Polars + Prefect là stack chuẩn modern data stack, transferable skill
- Env config (D5) dễ maintain, không drift giữa prod/dev folder
- R2 làm SoT giúp bizfly chỉ producer, không serving layer — đơn giản hóa

**Negative / Trade-off:**
- Mất khả năng schedule deploy auto qua CI (chủ động `make deploy`)
- Phát hiện env drift muộn hơn (không có matrix test CI trên nhiều env)
- Phụ thuộc discipline của dev (phải chạy pre-commit, không bypass)

**Neutral:**
- Khi scale lớn hơn (multi-team, >3 consumer) nên xem xét thêm CI/CD, data catalog (DataHub), schema registry — chưa cần giờ.

## References
- ADR-011 (ssi-connection): R2 làm SoT
- `data-lakehouse/README.md`: medallion architecture
- `stock-data-pipeline/CLAUDE.md`: Prefect + Polars + psycopg stack (sẽ rename thành `data-pipeline`)
