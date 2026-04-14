# Superset Setup — LXC 205

## Overview

Apache Superset 4.1.4 chạy native (không Docker) trên LXC 205, kết nối duy nhất tới PG Gold.
Mọi data source mới phải ETL vào Gold layer trước — Superset không bypass lakehouse pattern.

```
PG Gold (LXC 202, LAN 192.168.0.113:5432)
    │ daily_ohlcv (47K rows)
    │ ticks (82M rows)
    ▼
Superset (LXC 205)
    │ Gunicorn + Celery + Redis
    ├──▶ Browser     http://100.104.77.58:8088 (Tailscale)
    ├──▶ Browser     http://192.168.0.116:8088 (LAN)
    └──▶ MCP Server  Claude tự tạo dashboard qua REST API
```

## Connection Info

| Item | Value |
|------|-------|
| URL (Tailscale) | `http://100.104.77.58:8088` |
| URL (LAN) | `http://192.168.0.116:8088` |
| Hostname | `superset-signalhub` |
| Admin | `admin` / xem Vault `infra/superset` hoặc `/opt/superset/.credentials` |
| Config | `/opt/superset/superset_config.py` |
| Venv | `/opt/superset/venv` (Python 3.11.12) |
| Metadata DB | PostgreSQL 17 local, database `superset_meta`, user `superset` |
| Cache + Broker | Redis `localhost:6379` (db 0-4) |
| Credentials | Vault `infra/superset` (LXC 200) hoặc `/opt/superset/.credentials` |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ LXC 205 — Debian 13 (trixie), 6GB RAM, 2 CPU, 40GB disk │
│                                                           │
│  ┌──────────────────┐   ┌─────────────────────┐          │
│  │ superset-web      │   │ superset-worker      │          │
│  │ Gunicorn gthread  │   │ Celery prefork       │          │
│  │ 2 workers x4 thr  │   │ concurrency=2        │          │
│  │ :8088             │   │                      │          │
│  └────────┬─────────┘   └──────────┬───────────┘          │
│           │                        │                      │
│  ┌────────▼─────────┐   ┌─────────▼───────────┐          │
│  │ PostgreSQL 17     │   │ Redis 7             │          │
│  │ superset_meta     │   │ db0: cache          │          │
│  │ user: superset    │   │ db1: data cache     │          │
│  │                   │   │ db2: celery broker  │          │
│  │                   │   │ db3: celery results │          │
│  │                   │   │ db4: SQL Lab results│          │
│  └───────────────────┘   └─────────────────────┘          │
│                                                           │
│  Tailscale: 100.104.77.58 │ LAN: 192.168.0.116           │
└─────────────────────────────┬────────────────────────────┘
                              │ SQL over LAN
                              ▼
                    PG Gold (LXC 202, 192.168.0.113:5432)
                    db=stock_market, user=stock
```

**Lưu ý network:** LXC 205 kết nối PG Gold qua LAN IP (`192.168.0.113`), không qua Tailscale IP (`100.79.83.42`). Cả hai LXC cùng bridge `vmbr0` trên Proxmox — latency ~0.07ms.

## Quản lý Services

```bash
# SSH vào LXC 205 qua Proxmox
ssh root@100.89.161.125 "pct exec 205 -- bash"

# Hoặc qua Tailscale (nếu đã cài SSH trên 205)
ssh root@100.104.77.58

# --- Status ---
systemctl status superset-web superset-worker redis-server postgresql

# --- Logs ---
journalctl -u superset-web -f          # web requests + errors
journalctl -u superset-worker -f       # async query execution

# --- Restart (sau khi sửa config) ---
systemctl restart superset-web superset-worker

# --- Superset CLI ---
export SUPERSET_CONFIG_PATH=/opt/superset/superset_config.py FLASK_APP=superset
/opt/superset/venv/bin/superset db upgrade          # migrate metadata DB
/opt/superset/venv/bin/superset fab list-users       # list users
```

## Install / Reinstall

Script: `data-lakehouse/scripts/install_superset.sh`

### Chạy trên LXC 205

```bash
# Push script vào LXC
scp scripts/install_superset.sh root@100.89.161.125:/tmp/
ssh root@100.89.161.125 "pct push 205 /tmp/install_superset.sh /tmp/install_superset.sh --perms 0755"

# Chạy (PG_GOLD_PASS bắt buộc)
ssh root@100.89.161.125 "pct exec 205 -- bash -c '
    PG_GOLD_PASS=xxx ADMIN_PASS=mypass bash /tmp/install_superset.sh
'"
```

Script idempotent — chạy lại an toàn, skip bước đã hoàn thành (Python build, DB create...).

### 9 bước install script chạy

| Step | Mô tả | Thời gian |
|------|-------|-----------|
| 1 | System deps (build-essential, libpq, libffi...) | ~30s |
| 2 | Build Python 3.11 from source | ~5 min |
| 3 | PostgreSQL metadata DB (local, `superset_meta`) | ~2s |
| 4 | Redis | ~1s |
| 5 | pip install apache-superset + deps | ~3 min |
| 6 | Write `superset_config.py` | ~1s |
| 7 | `superset db upgrade` + create admin | ~30s |
| 8 | systemd services (superset-web, superset-worker) | ~5s |
| 9 | Add PG Gold data source via API | ~3s |

Tổng: ~10 phút trên 2 CPU.

### Env vars

| Var | Default | Mô tả |
|-----|---------|-------|
| `PG_GOLD_PASS` | _(bắt buộc)_ | Password PG Gold |
| `PG_GOLD_HOST` | `192.168.0.113` | PG Gold host (LAN IP) |
| `ADMIN_PASS` | random | Superset admin password |
| `ADMIN_USER` | `admin` | Superset admin username |
| `META_DB_PASS` | random | Password cho PG metadata user |
| `SECRET_KEY` | random | Flask SECRET_KEY |
| `PYTHON_VERSION` | `3.11.12` | Python version (phải 3.11.x, xem Known Constraints) |

## Seed Dashboards

Script `data-lakehouse/scripts/seed_dashboards.py` tạo 3 dashboards ban đầu.

### Chạy

```bash
# Từ Mac (qua Tailscale)
cd data-lakehouse
SUPERSET_URL=http://100.104.77.58:8088 \
SUPERSET_USER=admin \
SUPERSET_PASSWORD=xxx \
python3 scripts/seed_dashboards.py

# Hoặc trên LXC 205 (localhost)
SUPERSET_URL=http://localhost:8088 \
SUPERSET_USER=admin \
SUPERSET_PASSWORD=xxx \
/opt/superset/venv/bin/python3.11 /path/to/seed_dashboards.py
```

### Tạo gì

| Dashboard | Charts | Data source |
|-----------|--------|-------------|
| **Market Overview** | Market Total Value (bar), Advances vs Declines (line), Active Symbols (big number) | `market_summary` (virtual) |
| **Top Movers** | Top Gainers (table), Top Losers (table) | `top_movers` (virtual) |
| **Trading Activity** | Tick Volume by Hour (bar), Symbols Traded by Hour (heatmap) | `hourly_ticks` (virtual) |

4 datasets tạo: `daily_ohlcv` (physical), `top_movers`, `hourly_ticks`, `market_summary` (virtual SQL).

Script idempotent — chạy lại sẽ detect existing, không duplicate.

## Vault Integration

Tất cả credentials lưu tại Vault KV v2, path `infra/superset`.

```bash
# Đọc
export VAULT_ADDR=https://100.64.176.104:8200 VAULT_SKIP_VERIFY=true
vault login   # root token từ /root/.vault-init/init-keys.json trên LXC 200
vault kv get infra/superset

# Cập nhật
vault kv put infra/superset \
    url_lan=http://192.168.0.116:8088 \
    url_tailscale=http://100.104.77.58:8088 \
    admin_user=admin \
    admin_pass=<password> \
    pg_gold_host_lan=192.168.0.113 \
    pg_gold_pass=<password> \
    meta_db_pass=<password> \
    tailscale_ip=100.104.77.58
```

## Troubleshooting

### Superset không start

```bash
journalctl -u superset-web --no-pager -n 50

# Test config thủ công
export SUPERSET_CONFIG_PATH=/opt/superset/superset_config.py FLASK_APP=superset
/opt/superset/venv/bin/superset db upgrade
```

Lỗi phổ biến:
- `SECRET_KEY must be set` → SECRET_KEY rỗng trong config. Tạo mới: `openssl rand -hex 32`
- `No module 'pkg_resources'` → setuptools quá mới. Fix: `/opt/superset/venv/bin/pip install 'setuptools<75'`
- `No module 'flask_cors'` → Thiếu dep. Fix: `/opt/superset/venv/bin/pip install flask-cors`

### SQL Lab: "Results backend is not configured"

Superset cần `RESULTS_BACKEND` cho async SQL queries. Thêm vào `superset_config.py`:

```python
from cachelib.redis import RedisCache
RESULTS_BACKEND = RedisCache(host="localhost", port=6379, db=4)
```

Restart: `systemctl restart superset-web superset-worker`

### Query timeout trên ticks (82M rows)

Config đã set timeout 120s và Celery async. Nếu vẫn chậm:
1. Tạo virtual dataset với pre-aggregated SQL thay vì query raw ticks
2. Thêm index: `CREATE INDEX idx_ticks_time ON ticks (tick_time);`
3. Giảm `ROW_LIMIT` trong chart params

### PG Gold connection failed

Superset connect PG Gold qua LAN (`192.168.0.113`), không qua Tailscale. Verify:
```bash
# Từ trong LXC 205
PGPASSWORD=xxx psql -h 192.168.0.113 -U stock -d stock_market -c "SELECT 1"
```

### Redis connection refused

```bash
systemctl status redis-server
systemctl restart redis-server
redis-cli ping   # should return PONG
```

## Known Constraints

| Constraint | Lý do | Workaround |
|-----------|-------|------------|
| **Python 3.11 only** | Superset 4.x pins `numpy==1.23.5` — cần `distutils` (removed in 3.12) | Không dùng 3.12+. Khi Superset 5.x ra → upgrade |
| **setuptools < 75** | Superset import `pkg_resources` (deprecated, removed setuptools 78+) | Pin trong pip install |
| **flask-cors** | Không auto-install khi `ENABLE_CORS=True` trong config | Cài thủ công |
| **2 CPU / 6GB RAM** | Đủ cho 1-2 users, query ticks nên pre-aggregate | Scale nếu cần nhiều user |
| **LXC-to-LXC via LAN** | Cùng Proxmox bridge, dùng LAN IP cho inter-LXC traffic | Không dùng Tailscale IP cho internal |

## File Layout trên LXC 205

```
/opt/superset/
├── superset_config.py          # Superset configuration
├── .credentials                # Admin + DB passwords (chmod 600)
└── venv/                       # Python 3.11 virtualenv
    └── bin/
        ├── superset            # Superset CLI
        ├── gunicorn            # WSGI server
        ├── celery              # Task worker
        └── python3.11

/opt/python311/                 # Python 3.11.12 built from source
/etc/systemd/system/
├── superset-web.service        # Gunicorn (port 8088)
└── superset-worker.service     # Celery worker
```
