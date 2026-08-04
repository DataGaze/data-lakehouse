# Runbook — Data Lakehouse Operations & On-Call Playbook

| Field | Value |
|---|---|
| **Owner** | Data Platform (trongnq / hoangnguyen) |
| **Last Updated** | 2026-08-05 |
| **Version** | 0.1.0 |
| **Status** | Draft |
| **On-call primary** | @trongnq (Telegram) |
| **On-call backup** | @hoangnguyen (Telegram) |
| **Alert channel** | Telegram bot `DataGaze Ops` → chat `TELEGRAM_CHAT_ID` |
| **Escalation** | Telegram @trongnq → call → email (xem §8) |

> Runbook này cover DataGaze data platform: từ ingestion trên Bizfly VPS, qua R2, đến lakehouse Gold trên Proxmox LXC. Đọc cùng `docs/adr/2026-04-13-platform-decisions.md` (kiến trúc) và `ssi-connection/docs/06-OPERATIONS.md` (ingestion chi tiết).

> ## [KHÔNG CÒN HIỆU LỰC] Mọi thủ tục liên quan Prefect — 2026-08-05
>
> Prefect đã gỡ khỏi hệ thống: `prefect-server` (LXC 201) và `prefect-worker` (LXC 202)
> đều stopped + disabled sau 4 tháng chạy với 0 deployment và 0 flow run. Các mục §1.2,
> §2.1, §2.2, §2.4 và mọi lệnh `prefect ...` trong tài liệu này **không chạy được nữa** —
> đừng làm theo. Chúng được giữ lại làm bản ghi, sẽ viết lại khi Dagster chạy thật.
>
> Trong giai đoạn chuyển tiếp: **không có scheduler nào đang chạy**, ETL chỉ chạy khi gọi
> tay bằng CLI của `data-pipeline`. Chi tiết quyết định:
> [ADR 2026-08-05](./adr/2026-08-05-retire-prefect-adopt-dagster.md).

---

## 1. Service Inventory

### 1.1 Bizfly VPS — Producer (upstream source)

| Attribute | Value |
|---|---|
| **Role** | SSI Fast Connect ingestion → WAL → Parquet → R2 upload |
| **Host alias (SSH)** | `bizfly` (xem `~/.ssh/config`) |
| **Public IP** | `14.225.0.201` |
| **SSH port** | `2222` |
| **User** | `trongnq` |
| **Project root** | `/home/trongnq/Projects/SSI_Conection` |
| **OS** | Ubuntu 24.04 LTS |
| **Spec** | 4 vCPU / 8 GB RAM / 60 GB SSD |
| **Timezone** | `Asia/Ho_Chi_Minh` (UTC+7) |
| **Process mgmt** | `systemd --user` (linger enabled) + crontab |

**5 processes trên Bizfly** (ADR ssi-connection):

| # | Process | Schedule | Mechanism | Purpose |
|---|---|---|---|---|
| 1 | `ssi-ingestion.service` | Mon–Fri 08:50–15:10 | systemd + start/stop timers | SSI SignalR → WAL (gzip JSONL) |
| 2 | `telegram_monitor.py` | Mon–Fri market hours, every 2 min | crontab | Đọc state → alert Telegram |
| 3 | `status_reporter.py` | Mon–Fri 08:00–15:30, */30 min | crontab | Periodic status + stale detection |
| 4 | `ssi-processor.service` | Mon–Fri 16:30 | systemd timer (oneshot) | WAL → Parquet local + reconcile |
| 5 | `r2_uploader.py` | Mon–Fri 17:03 | crontab | Parquet local → Cloudflare R2 |

Data sau 17:03 đã on R2 bucket `vn-stock-lake` ở prefix `{YYYY}/{MM}/{DD}/{channel}/{exchange}.parquet`.

### 1.2 Prefect Server — LXC 201 [ĐÃ GỠ 2026-08-05]

| Attribute | Value |
|---|---|
| **Role** | Orchestration control plane cho toàn bộ data-pipeline |
| **Host** | Proxmox LXC 201 |
| **IP** | `192.168.0.112` |
| **Service** | Prefect Server 3.x (API + UI) |
| **UI URL** | `http://192.168.0.112:4200` |
| **API URL** | `http://192.168.0.112:4200/api` |
| **Mgmt** | `systemctl` (privileged LXC) |
| **DB backend** | Postgres local container trên cùng LXC (Prefect metadata) |

### 1.3 Lakehouse Gold — LXC 202

| Attribute | Value |
|---|---|
| **Role** | Bronze download + Silver transform + Gold warehouse |
| **Host** | Proxmox LXC 202 (renamed từ `stock-gold`) |
| **IP** | `192.168.0.113` |
| **OS** | Ubuntu 24.04 LTS |
| **Postgres** | Docker container `postgres-gold`, image `postgres:16`, port `5432` |
| **Database** | `datagaze` (schema `prod`, `dbt_{user}_dev`) |
| ~~**Prefect worker**~~ | `prefect-worker.service` stopped + disabled 2026-08-05 (venv `/opt/prefect/` còn trên đĩa, xóa được) |
| **Data dirs** | `/var/lib/docker/volumes/pg_gold_data/_data` (PG), `/opt/lakehouse/bronze`, `/opt/lakehouse/silver` |
| **dbt project** | `/opt/data-pipeline/dbt` |

**Daily flow** (Mon–Fri 17:30 — *mục tiêu*; từ 2026-08-05 chưa có scheduler, chỉ chạy khi gọi tay):
1. `r2_to_bronze` kéo Parquet từ R2 về `/opt/lakehouse/bronze/{date}/`
2. Polars transform Bronze → Silver (`/opt/lakehouse/silver/{date}/`)
3. `dbt run --target prod` load Silver → schema `prod` trong Postgres
4. `dbt test` — fail thì run fail + Telegram alert

---

## 2. Common Operations

### 2.1 Restart Prefect worker (LXC 202) [KHÔNG CÒN HIỆU LỰC — service đã gỡ]

```bash
# SSH vào lakehouse-gold
ssh lakehouse-gold   # alias → trongnq@192.168.0.113

# Xem status
sudo systemctl status prefect-worker.service

# Restart
sudo systemctl restart prefect-worker.service

# Tail logs
sudo journalctl -u prefect-worker.service -f --since "5 min ago"

# Verify worker đã đăng ký với server
curl -s http://192.168.0.112:4200/api/work_pools/lakehouse-gold-pool | jq '.status'
```

Nếu worker không đăng ký được → check connectivity tới Prefect Server:

```bash
curl -sv http://192.168.0.112:4200/api/health
# Expect: HTTP/1.1 200 OK với {"status": "healthy"}
```

### 2.2 Restart Prefect Server (LXC 201) [KHÔNG CÒN HIỆU LỰC — service đã gỡ]

```bash
ssh prefect-server   # alias → root@192.168.0.112

systemctl status prefect-server.service
systemctl restart prefect-server.service
journalctl -u prefect-server.service -f --since "5 min ago"

# Smoke test
curl -s http://127.0.0.1:4200/api/health
```

### 2.3 Check Postgres health + connections (LXC 202)

```bash
ssh lakehouse-gold

# Container alive?
docker ps --filter name=postgres-gold --format '{{.Names}}\t{{.Status}}'

# Postgres responding?
docker exec postgres-gold pg_isready -U postgres -d datagaze
# Expect: /var/run/postgresql:5432 - accepting connections

# Connections in use vs max
docker exec postgres-gold psql -U postgres -d datagaze -c "
SELECT count(*) AS active,
       current_setting('max_connections')::int AS max_conn,
       round(100.0 * count(*) / current_setting('max_connections')::int, 1) AS pct
FROM pg_stat_activity
WHERE state IS NOT NULL;"

# Top 10 longest-running queries
docker exec postgres-gold psql -U postgres -d datagaze -c "
SELECT pid, usename, state, now() - query_start AS duration, left(query, 80) AS query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC NULLS LAST
LIMIT 10;"

# Database size
docker exec postgres-gold psql -U postgres -d datagaze -c "
SELECT pg_size_pretty(pg_database_size('datagaze')) AS size;"
```

### 2.4 Trigger manual R2 → Bronze backfill flow [LỆNH PREFECT KHÔNG CHẠY ĐƯỢC — xem ghi chú đầu file]

Trigger qua Prefect UI hoặc CLI từ LXC 202:

```bash
ssh lakehouse-gold
cd /opt/data-pipeline

# Quick run (hôm nay)
prefect deployment run 'r2-to-bronze/daily' \
  -p run_date=$(date +%Y-%m-%d)

# Backfill 1 ngày cụ thể
prefect deployment run 'r2-to-bronze/daily' \
  -p run_date=2026-04-10

# Backfill range (loop từng ngày, skip cuối tuần)
for d in 2026-04-06 2026-04-07 2026-04-08 2026-04-09 2026-04-10; do
  prefect deployment run 'r2-to-bronze/daily' -p run_date=$d
  sleep 5
done

# Theo dõi flow run
prefect flow-run ls --limit 5
prefect flow-run logs <flow-run-id>
```

Nếu muốn chỉ download Bronze thủ công (không chạy transform):

```bash
cd /opt/data-pipeline
python3 -m ingestion.r2_to_bronze --date 2026-04-10 --dry-run
python3 -m ingestion.r2_to_bronze --date 2026-04-10
```

### 2.5 Rotate secrets

Secrets gồm: R2 creds (Bizfly + LXC 202), Postgres password, Telegram bot token, Prefect API auth (nếu có).

#### 2.5.1 Rotate R2 access key trên Bizfly

```bash
# 1. Tạo key mới trên Cloudflare dashboard (R2 → Manage API tokens)
# 2. SSH vào bizfly
ssh bizfly

# 3. Backup .env hiện tại
cp /home/trongnq/Projects/SSI_Conection/.env \
   /home/trongnq/Projects/SSI_Conection/.env.bak.$(date +%Y%m%d)

# 4. Update R2_ACCESS_KEY + R2_SECRET_KEY
nano /home/trongnq/Projects/SSI_Conection/.env
# Sửa R2_ACCESS_KEY=..., R2_SECRET_KEY=...
chmod 600 /home/trongnq/Projects/SSI_Conection/.env

# 5. Dry-run uploader với key mới
cd /home/trongnq/Projects/SSI_Conection
python3 app/scripts/r2_uploader.py --date $(date -d yesterday +%Y-%m-%d) --dry-run

# 6. Nếu OK → revoke key cũ trên Cloudflare
```

#### 2.5.2 Rotate R2 key trên LXC 202

```bash
ssh lakehouse-gold
sudo nano /opt/data-pipeline/environments/prod.env
# Sửa R2_ACCESS_KEY, R2_SECRET_KEY

# Prefect worker đọc env từ deployment — restart để reload
sudo systemctl restart prefect-worker.service

# Test: trigger flow dev
prefect deployment run 'r2-to-bronze/daily' -p run_date=$(date +%Y-%m-%d) -p dry_run=true
```

#### 2.5.3 Rotate Postgres password

```bash
ssh lakehouse-gold

# 1. Tạo password mới, set trong container
docker exec -it postgres-gold psql -U postgres -c \
  "ALTER USER postgres WITH PASSWORD 'NEW_STRONG_PASSWORD';"

# 2. Update env cho data-pipeline
sudo nano /opt/data-pipeline/environments/prod.env
# PG_PASSWORD=NEW_STRONG_PASSWORD

# 3. Update dbt profiles
sudo nano /opt/data-pipeline/dbt/profiles.yml
# (nên dùng {{ env_var('PG_PASSWORD') }} để tránh sửa profiles.yml)

# 4. Restart worker + test connection
sudo systemctl restart prefect-worker.service
docker exec postgres-gold psql -U postgres -d datagaze -c "SELECT version();"
```

#### 2.5.4 Rotate Telegram bot token (Bizfly)

```bash
# 1. @BotFather → /revoke → /newtoken (hoặc dùng /token trên bot hiện tại)
ssh bizfly
nano /home/trongnq/Projects/SSI_Conection/.env
# TELEGRAM_BOT_TOKEN=<new token>

# 2. Test
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"

# 3. Force trigger 1 lần telegram_monitor để xác nhận nhận được tin nhắn
cd /home/trongnq/Projects/SSI_Conection
python3 app/scripts/telegram_monitor.py
```

---

## 3. Incident Response — Severity & SLA

| Severity | Định nghĩa | Response SLA | Resolution SLA | Ai trả lời | Ai thông báo |
|---|---|---|---|---|---|
| **SEV1** | Data loss đang diễn ra HOẶC pipeline down > 4h trong giờ giao dịch HOẶC Postgres gold không query được | **15 phút** | **4 giờ** | On-call primary | Telegram 🔴 + gọi điện nếu ko ack trong 15' |
| **SEV2** | Partial failure (1 flow fail, 1 exchange miss), degraded SLO nhưng data intact | **1 giờ** (trong giờ làm việc) | **24 giờ** | On-call primary | Telegram 🟡 |
| **SEV3** | Cosmetic, alert noise, non-urgent refactor, docs drift | Best-effort | 1 tuần | Anyone | Telegram 🟢 hoặc backlog |

**Rules:**
- Trong giờ giao dịch (Mon–Fri 09:00–15:00 VN): bất kỳ ingestion process down nào → mặc định SEV2, escalate SEV1 sau 4h.
- Ngoài giờ giao dịch + trước 17:30 (Prefect flow chạy): xử lý khi có thể, thường SEV3.
- Sau 17:30 fail → SEV2 vì data ngày đó chưa xuống Gold.
- **Ack trong Telegram** bằng reply `ack sev<N>` trong vòng SLA. Không ack = auto-escalate.

---

## 4. Incident Playbooks

### 4.1 Bizfly ingestion down

**Symptom**
- 🔴 `ssi-ingestion is NOT running during market hours!`
- Hoặc status_reporter báo `+0 events` trong active session > 5 phút
- Hoặc Telegram monitor stuck (không còn 2-min heartbeat)

**Check**

```bash
ssh bizfly
systemctl --user status ssi-ingestion.service
journalctl --user -u ssi-ingestion.service --since "30 min ago" | tail -80

# Có PID lock stuck không?
ls -la /home/trongnq/Projects/SSI_Conection/data/state/ingestion.pid
cat /home/trongnq/Projects/SSI_Conection/data/state/ingestion.pid

# Network tới SSI?
curl -sv --max-time 5 https://fc-datahub.ssi.com.vn/v2.0/signalr/negotiate?clientProtocol=1.5
```

**Fix**

```bash
# Case 1: service exited, systemd chưa restart
systemctl --user restart ssi-ingestion.service
journalctl --user -u ssi-ingestion.service -f

# Case 2: PID lock stuck (zombie), service không start lại được
# — CHỈ xoá PID file nếu đã confirm không có process nào chạy
pgrep -af run_production.py   # phải empty
rm /home/trongnq/Projects/SSI_Conection/data/state/ingestion.pid
systemctl --user restart ssi-ingestion.service

# Case 3: SSI key expired (log có "connection is invalid")
# → Renew key trên SSI iBoard, update .env, restart
nano /home/trongnq/Projects/SSI_Conection/.env
systemctl --user restart ssi-ingestion.service

# Case 4: All reconnect attempts failed (sau 5+ lần)
# → Kiểm tra SSI status page / network Bizfly, escalate nếu SSI down
```

**Post-incident:** note vào `docs/TECH-DEBT.md` ssi-connection nếu gap data > 10 phút. Backfill bằng `app/scripts/backfill_historical.py` (chỉ khôi phục OHLC, không khôi phục tick-by-tick).

### 4.2 R2 upload failing

**Symptom**
- 🔴 `r2_uploader.py failed` trong log
- Missing Parquet trong bucket sau 17:30
- LXC 202 flow `r2-to-bronze` báo `NoSuchKey`

**Check**

```bash
ssh bizfly
cd /home/trongnq/Projects/SSI_Conection
tail -100 data/logs/r2_uploader.log
cat data/state/uploads/$(date +%Y-%m-%d).json | python3 -m json.tool

# Credential còn hợp lệ?
source .env
aws --endpoint-url=$R2_ENDPOINT s3 ls s3://$R2_BUCKET/ --summarize | head

# Parquet local có tồn tại?
ls -la data/export/$(date +%Y-%m-%d)/
```

**Fix**

```bash
# Retry upload (idempotent, skip đã upload)
python3 app/scripts/r2_uploader.py

# Nếu state file corrupt → force re-upload ngày cụ thể
rm data/state/uploads/2026-04-10.json
python3 app/scripts/r2_uploader.py --date 2026-04-10

# Credentials lỗi → rotate (§2.5.1)
```

### 4.3 Prefect flow failed 3x [KHÔNG CÒN HIỆU LỰC — viết lại khi Dagster chạy]

**Symptom**
- Telegram 🔴 `Flow r2-to-bronze failed 3 consecutive runs`
- Prefect UI (http://192.168.0.112:4200) — nhiều flow-run state = `Failed`

**Check**

```bash
ssh lakehouse-gold
prefect flow-run ls --state Failed --limit 10
prefect flow-run logs <latest-failed-id> | tail -200

# Worker alive?
sudo systemctl status prefect-worker.service

# Connectivity R2?
cd /opt/data-pipeline
source environments/prod.env
aws --endpoint-url=$R2_ENDPOINT s3 ls s3://$R2_BUCKET/ | head

# Postgres alive? (xem §2.3)

# Disk đủ không?
df -h /opt/lakehouse
```

**Fix — theo root cause:**

- **R2 credential expired** → rotate theo §2.5.2
- **Postgres down** → xem §4.4
- **Disk full** → xem §4.5
- **Bug code** → rollback Prefect deployment về version trước:

```bash
cd /opt/data-pipeline
git log --oneline -5
git checkout <good-commit>
make deploy ENV=prod   # re-apply deployment
```

- **Flow-specific** (e.g., dbt test fail) → check dbt output:

```bash
cd /opt/data-pipeline/dbt
dbt test --target prod --select <model>
dbt run --target prod --select <model> --full-refresh   # last resort
```

### 4.4 Postgres connection exhausted

**Symptom**
- 🔴 `FATAL: sorry, too many clients already` trong worker log
- dbt run fail với `connection refused`
- `pg_stat_activity` count gần `max_connections`

**Check**

```bash
ssh lakehouse-gold

# Count + top consumers
docker exec postgres-gold psql -U postgres -d datagaze -c "
SELECT application_name, state, count(*)
FROM pg_stat_activity
GROUP BY application_name, state
ORDER BY count DESC;"

# Idle-in-transaction (thường là culprit)
docker exec postgres-gold psql -U postgres -d datagaze -c "
SELECT pid, application_name, state, now() - state_change AS idle_duration, left(query, 100) AS query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY idle_duration DESC;"
```

**Fix**

```bash
# Immediate: terminate idle-in-transaction > 10 phút
docker exec postgres-gold psql -U postgres -d datagaze -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND now() - state_change > interval '10 minutes';"

# Medium: tăng max_connections nếu dbt + Prefect worker cần > default
docker exec postgres-gold psql -U postgres -c "ALTER SYSTEM SET max_connections = 200;"
docker restart postgres-gold
# Verify
docker exec postgres-gold psql -U postgres -c "SHOW max_connections;"

# Long-term: dùng pgbouncer (chưa deploy — tracked TECH-DEBT)
```

### 4.5 Disk full trên lakehouse-gold

**Symptom**
- 🔴 `No space left on device` trong worker / Postgres log
- `df -h` mount point `/` hoặc `/opt` > 90%
- Flow fail tại step `polars.write_parquet` hoặc `COPY`

**Check**

```bash
ssh lakehouse-gold
df -h
du -sh /opt/lakehouse/bronze/* | sort -h | tail -20
du -sh /opt/lakehouse/silver/* | sort -h | tail -20
du -sh /var/lib/docker/volumes/pg_gold_data/_data
docker system df
```

**Fix — in priority order:**

```bash
# 1. Xoá Bronze cũ > 30 ngày (Bronze có thể re-download từ R2)
find /opt/lakehouse/bronze -maxdepth 1 -type d -name "20*" -mtime +30 \
  -exec echo "Would delete: {}" \;
# Khi confirm đúng:
# find /opt/lakehouse/bronze -maxdepth 1 -type d -name "20*" -mtime +30 -exec rm -rf {} \;
#
# LƯU Ý: KHÔNG tự chạy rm -rf. In command ra cho owner confirm rồi chạy tay
# (theo global rule về destructive commands).

# 2. Xoá Docker dangling images/volumes
docker system prune -a --volumes   # chỉ khi confirm không còn image cần
# hoặc cụ thể:
docker image prune -f
docker builder prune -f

# 3. Vacuum Postgres
docker exec postgres-gold psql -U postgres -d datagaze -c "VACUUM FULL ANALYZE;"

# 4. Logs
sudo journalctl --vacuum-time=7d
```

Threshold:
- 80% → 🟡 cleanup Bronze > 60 ngày
- 90% → 🔴 cleanup ngay, SEV2

---

## 5. Recovery Procedures

### 5.1 Postgres backup strategy

**Schedule:** daily 23:00 VN (sau khi Gold đã load xong), chạy trên LXC 202 qua systemd timer `pg-backup.timer`.

**Retention:**
- 7 daily dumps (rolling)
- 4 weekly dumps (Sunday, rolling 4 tuần)
- 12 monthly dumps (ngày 1, rolling 12 tháng)

**Script location:** `/opt/scripts/pg_backup.sh`

**Manual dump** (toàn bộ database `datagaze`):

```bash
ssh lakehouse-gold
TS=$(date +%Y%m%d_%H%M%S)
docker exec postgres-gold pg_dump -U postgres -Fc -d datagaze \
  > /opt/backups/postgres/datagaze_${TS}.dump

# Verify
ls -lh /opt/backups/postgres/datagaze_${TS}.dump
docker exec -i postgres-gold pg_restore -l < /opt/backups/postgres/datagaze_${TS}.dump | head
```

**Schema-only / data-only:**

```bash
# Schema only
docker exec postgres-gold pg_dump -U postgres -s -d datagaze > schema.sql

# Single schema (prod)
docker exec postgres-gold pg_dump -U postgres -Fc -n prod -d datagaze > prod_schema.dump
```

**Offsite:** daily dump sync lên R2 `s3://vn-stock-lake/backups/postgres/` giữ 30 ngày:

```bash
aws --endpoint-url=$R2_ENDPOINT s3 cp \
  /opt/backups/postgres/datagaze_${TS}.dump \
  s3://vn-stock-lake/backups/postgres/datagaze_${TS}.dump \
  --storage-class STANDARD
```

**Restore** (full):

```bash
# 1. Stop worker (tránh write trong lúc restore)
sudo systemctl stop prefect-worker.service

# 2. Drop + recreate database
docker exec postgres-gold psql -U postgres -c "DROP DATABASE datagaze;"
docker exec postgres-gold psql -U postgres -c "CREATE DATABASE datagaze;"

# 3. Restore
docker exec -i postgres-gold pg_restore -U postgres -d datagaze -j 4 \
  < /opt/backups/postgres/datagaze_20260412_230000.dump

# 4. Verify
docker exec postgres-gold psql -U postgres -d datagaze -c "\dn"
docker exec postgres-gold psql -U postgres -d datagaze -c \
  "SELECT schemaname, count(*) FROM pg_tables GROUP BY schemaname;"

# 5. Start worker
sudo systemctl start prefect-worker.service
```

### 5.2 Parquet recovery từ R2 (rebuild Bronze)

Bronze local là cache — nếu mất có thể rebuild từ R2 (SoT theo ADR D3):

```bash
ssh lakehouse-gold
cd /opt/data-pipeline
source environments/prod.env

# Single date
python3 -m ingestion.r2_to_bronze --date 2026-04-10

# Range
for d in $(seq 0 30); do
  DATE=$(date -d "$d days ago" +%Y-%m-%d)
  python3 -m ingestion.r2_to_bronze --date $DATE --skip-existing
done

# Verify counts match R2
aws --endpoint-url=$R2_ENDPOINT s3 ls --recursive \
  s3://$R2_BUCKET/2026/04/10/ | wc -l
find /opt/lakehouse/bronze/2026-04-10/ -name '*.parquet' | wc -l
```

Sau khi Bronze rebuild → trigger Silver + Gold:

```bash
prefect deployment run 'bronze-to-silver/daily' -p run_date=2026-04-10
prefect deployment run 'silver-to-gold/daily'  -p run_date=2026-04-10
```

### 5.3 Point-in-time recovery (PITR) plan

**Current state (Draft):** PITR chưa enabled. Chỉ có daily `pg_dump` = RPO 24h, RTO ~30 phút cho dataset hiện tại (< 50 GB).

**Gap analysis:**
- Mất dữ liệu trong ngày giữa 2 dump → có thể rebuild từ Bronze + dbt (deterministic, idempotent). Acceptable vì Gold là derived layer.
- Nếu Postgres corrupt ngay trước 23:00 → mất tối đa 1 ngày Gold transform, rebuild ~15 phút.

**Roadmap (tracked TECH-DEBT):**
- Enable WAL archiving tới R2 `s3://vn-stock-lake/backups/postgres-wal/` → RPO < 5 phút
- `archive_command`: `aws s3 cp %p s3://.../postgres-wal/%f`
- Test restore hàng tháng

**Restore to timestamp (khi đã có WAL archiving):**

```bash
# 1. Stop postgres
docker stop postgres-gold

# 2. Restore base backup + replay WAL tới thời điểm T
# (procedure cụ thể viết sau khi enable WAL archive)
```

---

## 6. Monitoring & Alerts

**Alert transport:** Telegram bot → chat `TELEGRAM_CHAT_ID`. Không có Slack/Email ở thời điểm này.

### 6.1 Alert matrix

| Source | Check | Threshold | Severity | Runbook |
|---|---|---|---|---|
| Bizfly `healthcheck.sh` (every 5') | Disk usage | > 90% | 🔴 SEV1 | §4.5 (lakehouse) / SSI ops §7 |
| Bizfly `healthcheck.sh` | Disk usage | > 80% | 🟡 SEV2 | §4.5 |
| Bizfly `healthcheck.sh` | RAM free | < 500 MB | 🔴 SEV1 | SSI ops §7 |
| Bizfly `healthcheck.sh` | ssi-ingestion down in market hours | immediate | 🔴 SEV1 | §4.1 |
| Bizfly `healthcheck.sh` | WAL file size | < 1 MB cho 1h tick | 🟡 SEV2 | SSI ops §4 |
| Bizfly `healthcheck.sh` | Post-processor chạy chưa | 17:00 chưa chạy | 🟡 SEV2 | SSI ops §7.1 |
| Bizfly `status_reporter.py` (every 30') | Events stuck | +0 events in active session | 🟡 SEV2 | §4.1 |
| LXC 202 Prefect flow | `r2-to-bronze` fail | 1 lần | 🟡 SEV2 | §4.2 / §4.3 |
| LXC 202 Prefect flow | Any flow fail | 3x consecutive | 🔴 SEV1 | §4.3 |
| LXC 202 `dbt test` | Data quality fail | bất kỳ test fail | 🟡 SEV2 | §4.3 |
| LXC 202 custom check (every 15') | Postgres connections | > 80% max_connections | 🟡 SEV2 | §4.4 |
| LXC 202 custom check | Postgres down | `pg_isready` fail | 🔴 SEV1 | §4.4 / §5.1 |
| LXC 202 custom check | Disk `/opt/lakehouse` | > 90% | 🔴 SEV1 | §4.5 |
| LXC 202 custom check | Disk `/opt/lakehouse` | > 80% | 🟡 SEV2 | §4.5 |

### 6.2 Alert emoji convention (khớp SSI ops §4)

- 🔴 **CRITICAL** — ack trong 15', data loss risk
- 🟡 **WARNING** — ack trong 1h
- 🟢 **INFO** — không cần action
- 📊 **REPORT** — daily summary 16:40 (Bizfly) + 18:00 (Gold flow result)

### 6.3 Silence / maintenance window

Chưa có cơ chế formal. Trong lúc maintenance:
1. Post message vào Telegram: `🔕 Maintenance window start <TS> end <TS>, ignore alerts`
2. Stop healthcheck timer nếu cần:

```bash
# Bizfly
systemctl --user stop ssi-healthcheck.timer

# Sau maintenance
systemctl --user start ssi-healthcheck.timer
```

---

## 7. Escalation Path

```
Alert fires
  │
  ▼
On-call primary (@trongnq) — Telegram
  │  ack trong SLA? ─── NO ──► Wait 15 min ─► Call phone primary
  │                                               │
  │                                               ▼
  │                                    Ack? ── NO ──► On-call backup (@hoangnguyen)
  │                                                       │
  │                                                       ▼
  ▼                                            Ack? ── NO ──► Email + post Telegram escalation
Works on fix
  │
  ▼
Root cause identified? ── NO (> 2h for SEV1) ──► Escalate: post trong Telegram + tag cả 2
  │
  ▼
Fix applied → verify → post resolution in Telegram → file post-mortem nếu SEV1
```

### 7.1 Khi nào escalate

| Condition | Action |
|---|---|
| SEV1 chưa ack trong 15' | Auto-escalate backup |
| SEV1 chưa có hướng fix sau 2h | Post `@channel` Telegram, involve backup |
| SEV2 không ack sau 2h trong giờ làm việc | Escalate backup |
| Gặp unknown root cause + đã thử 2 fix không work | Dừng, post details, hỏi backup trước khi thử thứ 3 |
| Destructive action cần (rm -rf, DROP, force-restore) | Luôn double-confirm với owner trước khi chạy |

### 7.2 Liên hệ

| Role | Person | Telegram | Phone | Email |
|---|---|---|---|---|
| On-call primary | trongnq | `@trongnq` | (điền khi deploy prod) | trongnq@datagaze.local |
| On-call backup | hoangnguyen | `@hoangnguyen` | (điền khi deploy prod) | hoangnguyen@datagaze.local |
| Infra (Proxmox) | hoangnguyen | `@hoangnguyen` | — | — |
| SSI vendor support | SSI Fast Connect team | — | — | fc-support@ssi.com.vn |
| Cloudflare (R2) | Dashboard support | — | — | via CF dashboard |
| Bizfly support | Bizfly Cloud | — | (hotline hosting) | support@bizflycloud.vn |

### 7.3 Post-mortem

Bắt buộc cho mọi SEV1, trong vòng 3 ngày. Template:

```
docs/postmortems/YYYY-MM-DD-{slug}.md
  - Summary (2-3 câu)
  - Timeline (UTC+7)
  - Root cause
  - Resolution
  - Impact (data loss, duration, flows affected)
  - Action items (owner + deadline, track trong TECH-DEBT.md)
  - What went well / What didn't
```

---

## Appendix A — Quick reference

### Daily schedule (Mon–Fri, VN time)

```
08:50  Bizfly: ssi-ingestion.service start (systemd timer)
09:00  Market open — ingestion active
11:30  Lunch break (heartbeat disabled)
13:00  Resume afternoon session
15:00  Market close
15:10  Bizfly: ssi-ingestion.service stop
16:30  Bizfly: ssi-processor.service run (WAL → Parquet)
17:03  Bizfly: r2_uploader.py (Parquet → R2)
17:30  LXC 202: Prefect r2-to-bronze → bronze-to-silver → silver-to-gold
18:00  Gold ready, daily report sent via Telegram
23:00  LXC 202: pg_backup.sh (daily Postgres dump + sync R2)
00:00  Bizfly: cleanup-wal.sh (xoá WAL > 3 ngày đã verify R2 upload)
```

### SSH aliases (expected in `~/.ssh/config`)

```
Host bizfly
    HostName 14.225.0.201
    Port 2222
    User trongnq

Host prefect-server
    HostName 192.168.0.112
    User root

Host lakehouse-gold
    HostName 192.168.0.113
    User trongnq
```

### Key paths cheat-sheet

| Host | Path | Content |
|---|---|---|
| Bizfly | `/home/trongnq/Projects/SSI_Conection` | ssi-connection code |
| Bizfly | `~/data/wal/{date}/` | WAL raw |
| Bizfly | `~/data/export/{date}/` | Parquet pre-R2 |
| Bizfly | `~/data/state/uploads/{date}.json` | R2 upload state |
| LXC 201 | `/var/lib/prefect/` | Prefect server DB + config |
| LXC 202 | `/opt/data-pipeline/` | Python runtime code |
| LXC 202 | `/opt/lakehouse/bronze/{date}/` | Bronze parquet local |
| LXC 202 | `/opt/lakehouse/silver/{date}/` | Silver parquet local |
| LXC 202 | `/opt/backups/postgres/` | Daily pg_dump files |
| LXC 202 | `/var/lib/docker/volumes/pg_gold_data/_data` | Postgres data dir |

---

**Changelog**
- 2026-04-13 v0.1.0 — Initial draft, cover ingestion (Bizfly) + orchestration (LXC 201) + warehouse (LXC 202). PITR WAL archiving chưa enabled, tracked roadmap.
