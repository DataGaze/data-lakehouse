# Developer Onboarding — Data Lakehouse Platform

| Field | Value |
|-------|-------|
| **Owner** | @hoang |
| **Last Updated** | 2026-04-13 |
| **Version** | 1.0 |
| **Audience** | New developer joining DataGaze data platform |

---

## 1. Welcome

Chào mừng đến với **Data Lakehouse Platform** của DataGaze — hệ thống xử lý dữ liệu thị trường tài chính Việt Nam (stock + BĐS sắp tới), chạy trên home lab K3s + LXC Proxmox.

Mục đích của tài liệu này: giúp dev mới **setup local environment và chạy được dbt model đầu tiên trong 15 phút**. Sau đó biết đọc tiếp doc nào theo role của mình.

Nếu setup xong mà không chạy được trong 15 phút → ping `@hoang` trên Telegram, đừng tự vật lộn quá 30 phút.

---

## 2. Prerequisites — Tools cần cài local

Cài trước khi bắt đầu onboarding. Tất cả đều free/open-source.

| Tool | Version | Cài bằng | Ghi chú |
|------|---------|----------|---------|
| Python | 3.11+ | `brew install python@3.11` | Project yêu cầu 3.11 tối thiểu |
| uv | Latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package manager chính (thay pip/poetry) |
| Docker + Compose | 24+ | Docker Desktop / OrbStack | Optional — chỉ cần khi test container |
| dbt-postgres | 1.7+ | `uv pip install dbt-postgres` | Sẽ được cài tự động qua `uv sync` |
| Tailscale | Latest | `brew install --cask tailscale` | Bắt buộc để access home lab network |
| SOPS | Latest | `brew install sops` | Decrypt secrets trong `.env.dev.enc` |
| psql | 15+ | `brew install libpq && brew link libpq --force` | Client để test Postgres connection |
| Git | 2.40+ | `brew install git` | - |
| gh CLI | Latest | `brew install gh` | Tạo PR, tiện nhưng không bắt buộc |

Verify nhanh:
```bash
python3.11 --version   # 3.11.x
uv --version           # 0.x
sops --version         # 3.x
tailscale status       # Logged in
psql --version         # 15+
```

---

## 3. Access Checklist — Xin ai cấp gì

Ping `@hoang` trên Telegram hoặc email với list bên dưới. Thường xử lý trong 1 ngày làm việc.

- [ ] **GitHub DataGaze org membership** — để clone private repos (`data-lakehouse`, `data-pipeline`, `ssi-connection`...)
- [ ] **Tailscale invite** — join tailnet `datagaze`, để reach LXC 202 (lakehouse-gold)
- [ ] **R2 access credentials** — Cloudflare R2 bucket `lakehouse-bronze`, read-only cho dev, read-write cho prod flow
- [ ] **Postgres dev schema permission** — grant `CREATE` trên schema `dbt_{your_username}_dev` trong database `datagaze`
- [ ] **SOPS age key** — để decrypt `.env.dev.enc`. Gửi public key trước, nhận encrypted private key qua Signal
- [ ] **SSH key thêm vào bizfly VPS** — chỉ cần nếu role có liên quan production ingestion (thường dev mới **không** cần)
- [ ] **Telegram bot alert group** — join group `#datagaze-alerts` để thấy on-call notifications

---

## 4. First Setup (15 phút)

Chạy tuần tự. Nếu step nào fail, dừng lại và hỏi.

### 4.1. Clone repos

```bash
mkdir -p ~/All_projects/DataGaze && cd ~/All_projects/DataGaze

# Infra layer (repo này)
git clone git@github.com:DataGaze/data-lakehouse.git

# Runtime logic (sẽ rename từ stock-data-pipeline sang data-pipeline, xem ADR D1)
git clone git@github.com:DataGaze/stock-data-pipeline.git data-pipeline
```

### 4.2. Install dependencies

```bash
cd ~/All_projects/BIZ01-datagaze/data-pipeline
uv sync                        # Install tất cả deps từ pyproject.toml + lock file
source .venv/bin/activate      # Hoặc dùng `uv run <cmd>` trực tiếp
```

### 4.3. Setup secrets

```bash
# Copy template
cp .env.example .env.dev

# Decrypt encrypted env file (cần SOPS age key đã xin ở step 3)
sops -d .env.dev.enc > .env.dev

# Load vào shell
export $(grep -v '^#' .env.dev | xargs)
```

Verify không có placeholder `***` nào còn sót:
```bash
grep '\*\*\*' .env.dev && echo "FAIL: still has placeholders" || echo "OK"
```

### 4.4. Test Postgres connection

```bash
# Phải join Tailscale trước, LXC 202 chỉ accessible qua tailnet
psql "postgresql://stock@192.168.0.113:5432/datagaze" -c "\dt prod.*"
```

Thấy list tables trong schema `prod` → OK. Lỗi `connection refused` → check Tailscale.

### 4.5. Test R2 access

```bash
uv run python -c "
import boto3, os
s3 = boto3.client('s3',
    endpoint_url=os.environ['R2_ENDPOINT'],
    aws_access_key_id=os.environ['R2_ACCESS_KEY'],
    aws_secret_access_key=os.environ['R2_SECRET_KEY'])
resp = s3.list_objects_v2(Bucket='lakehouse-bronze', MaxKeys=5)
for o in resp.get('Contents', []):
    print(o['Key'])
"
```

Thấy 5 object keys → OK.

### 4.6. dbt debug

```bash
cd dbt/
dbt debug --target dev
```

Tất cả check `[OK]` → setup thành công.

---

## 5. First Task — Do 1 Small Change

Mục tiêu: verify end-to-end flow và làm quen với dev loop.

### 5.1. Tạo 1 dbt model đơn giản

File: `dbt/models/silver/stg_my_onboarding_test.sql`

```sql
{{ config(materialized='view') }}

select
    current_date as run_date,
    '{{ var("user_name", "unknown") }}' as created_by,
    1 as test_id
```

### 5.2. Run model

```bash
dbt run --target dev --select stg_my_onboarding_test --vars '{user_name: your_username}'
```

### 5.3. Verify trong Postgres

```bash
psql "postgresql://stock@192.168.0.113:5432/datagaze" \
  -c "select * from dbt_{your_username}_dev.stg_my_onboarding_test;"
```

Thấy 1 row với `run_date = today, created_by = your_username` → thành công.

### 5.4. Commit + pre-commit hook

```bash
git add dbt/models/silver/stg_my_onboarding_test.sql
git commit -m "test(onboarding): add sanity check model for {your_username} [B1.1]"
```

Pre-commit hook sẽ tự chạy `pytest` + `dbt parse` (xem ADR D7). Nếu pass → commit thành công. Nếu fail → fix theo hướng dẫn hook in ra.

### 5.5. Cleanup

```bash
git reset --hard HEAD~1   # Bỏ commit test
rm dbt/models/silver/stg_my_onboarding_test.sql
dbt run-operation drop_schema --args "{schema: dbt_{your_username}_dev}"  # Optional
```

---

## 6. Key Docs to Read Next (theo thứ tự)

Đọc theo thứ tự này để build mental model từ high-level xuống chi tiết.

1. **[architecture.md](architecture.md)** — Big picture: Bronze/Silver/Gold, components, data flow cross-system
2. **[data-contract.md](data-contract.md)** — Schema contract từng zone, type conventions, versioning rules
3. **[runbook.md](runbook.md)** — Ops playbook: deploy, rollback, on-call procedures
4. **[sla.md](sla.md)** — Service level objectives + error budget — biết khi nào được phép break
5. **[security.md](security.md)** — Threat model, secrets management, RBAC
6. **[cost.md](cost.md)** — Infra cost breakdown + projection — không burn budget vô ý
7. **[sequences/ingestion-flow.md](sequences/ingestion-flow.md)** — Visualize daily ingestion flow
8. **[adr/2026-04-13-platform-decisions.md](adr/2026-04-13-platform-decisions.md)** — 7 decision D1-D7, đọc để hiểu "tại sao chọn stack hiện tại"

---

## 7. Common Commands Cheat Sheet

### Makefile targets (trong `data-pipeline/`)

```bash
make setup            # Install deps + pre-commit hook
make ingest-stock     # Chạy ingestion: R2 → Bronze
make etl-stock        # Chạy ETL: Bronze → Silver → Gold
make test             # pytest full suite
make validate         # Validate Bronze data integrity
make check            # pytest + dbt test + mypy (gate trước deploy)
# make deploy — chưa có tầng điều phối từ 2026-08-05; sẽ trỏ sang Dagster khi dựng
```

### Chạy pipeline (từ 2026-08-05)

Prefect đã gỡ và Dagster chưa dựng, nên chưa có CLI điều phối. Chạy thẳng bằng CLI của
`data-pipeline` ([ADR 2026-08-05](./adr/2026-08-05-retire-prefect-adopt-dagster.md)):

```bash
python -m ingestion.r2_to_bronze --date 2026-08-04    # R2 → Bronze
python -m etl.orchestrator --source stock             # Bronze → Silver → Gold
python -m etl.orchestrator --source stock --step gold # chỉ một chặng
```

### dbt CLI (common)

```bash
dbt debug --target dev                      # Check connections
dbt parse                                   # Parse project, không run
dbt run --target dev --select silver.*      # Run all silver models
dbt run --target dev --select +gold.daily_ohlc   # Run gold.daily_ohlc + upstream
dbt test --target dev                       # Run all data tests
dbt docs generate && dbt docs serve         # Browse lineage graph
```

### Useful psql snippets

```bash
# Xem tables trong dev schema của mình
psql $PG_URL -c "\dt dbt_{your_username}_dev.*"

# Check row count vs prod
psql $PG_URL -c "select 'prod' as src, count(*) from prod.daily_ohlc union all
                 select 'dev', count(*) from dbt_{your_username}_dev.daily_ohlc;"
```

---

## 8. Who to Ask

| Topic | Contact |
|-------|---------|
| Infra, K3s, Proxmox, Tailscale | @hoang |
| dbt models, Silver/Gold logic | @hoang |
| Điều phối, scheduling | @hoang |
| R2 credentials, SOPS keys | @hoang |
| SSI source data questions | @hoang |
| On-call rotation | @hoang |
| General architecture decisions | @hoang |

> Note: đang là solo dev, sẽ update bảng này khi team scale. Nếu block quá 2 giờ ở bất kỳ step nào → ping ngay, đừng chờ.

---

## Feedback

Sau khi onboard xong, mở PR chỉnh sửa chính file này nếu thấy step nào unclear hoặc thiếu. Onboarding doc là **living document** — dev mới nhất là người sửa nó tốt nhất.
