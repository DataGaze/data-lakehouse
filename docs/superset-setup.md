# Superset Setup — LXC 205

## Overview

Apache Superset chạy native (không Docker) trên LXC 205 (`superset-signalhub`), kết nối tới PG Gold duy nhất.

```
PG Gold (LXC 202, 100.79.83.42)
    │ daily_ohlcv, ticks
    │
    ▼
Superset (LXC 205, 192.168.0.116:8088)
    │ Gunicorn + Celery + Redis
    │
    ▼
Browser / MCP Server (Claude tự tạo dashboard)
```

## Thông tin kết nối

| Item | Value |
|------|-------|
| URL | `http://192.168.0.116:8088` |
| Admin | `admin` / (xem `/opt/superset/.credentials`) |
| Config | `/opt/superset/superset_config.py` |
| Venv | `/opt/superset/venv` |
| Python | `/opt/python311/bin/python3.11` |
| Metadata DB | PostgreSQL local `superset_meta` |
| Cache/Celery | Redis `localhost:6379` |

## Architecture

```
┌─────────────────────────────────────────────┐
│ LXC 205 (Debian 13, 6GB RAM, 2 CPU)        │
│                                              │
│  systemd services:                           │
│  ┌──────────────┐  ┌───────────────────┐    │
│  │ superset-web  │  │ superset-worker   │    │
│  │ (Gunicorn)    │  │ (Celery)          │    │
│  │ :8088         │  │                   │    │
│  └───────┬───────┘  └────────┬──────────┘    │
│          │                   │               │
│  ┌───────▼───────┐  ┌───────▼──────────┐    │
│  │ PostgreSQL     │  │ Redis            │    │
│  │ superset_meta  │  │ cache + broker   │    │
│  └───────────────┘  └──────────────────┘    │
└──────────────────────┬──────────────────────┘
                       │ SQL queries
                       ▼
              PG Gold (LXC 202)
              stock_market DB
```

## Services

```bash
# Status
systemctl status superset-web
systemctl status superset-worker

# Logs
journalctl -u superset-web -f
journalctl -u superset-worker -f

# Restart
systemctl restart superset-web superset-worker

# Config reload (after editing superset_config.py)
systemctl restart superset-web
```

## Install / Reinstall

Script nằm tại `scripts/install_superset.sh`. Chạy trên LXC 205:

```bash
# Full install
PG_GOLD_PASS=xxx bash /path/to/install_superset.sh

# Override defaults
PG_GOLD_PASS=xxx ADMIN_PASS=mypass PYTHON_VERSION=3.12.9 bash install_superset.sh
```

Script idempotent — chạy lại an toàn (skip bước đã hoàn thành).

### Env vars

| Var | Default | Mô tả |
|-----|---------|-------|
| `PG_GOLD_PASS` | (required) | Password PG Gold |
| `ADMIN_PASS` | random | Superset admin password |
| `PYTHON_VERSION` | `3.11.12` | Python version to build (must be 3.11.x — Superset 4.x pins numpy 1.23.5 incompatible with 3.12) |
| `SECRET_KEY` | random | Flask secret key |

## Seed Dashboards

Sau khi cài xong, tạo dashboards ban đầu:

```bash
SUPERSET_URL=http://192.168.0.116:8088 \
SUPERSET_USER=admin \
SUPERSET_PASSWORD=xxx \
python scripts/seed_dashboards.py
```

Tạo 3 dashboards:
1. **Market Overview** — tổng giá trị giao dịch, advances/declines, số symbols
2. **Top Movers** — gainers/losers ngày mới nhất
3. **Trading Activity** — phân bổ ticks theo giờ, heatmap symbols

## Troubleshooting

### Superset không start

```bash
# Check logs
journalctl -u superset-web --no-pager -n 50

# Test config manually
export SUPERSET_CONFIG_PATH=/opt/superset/superset_config.py
/opt/superset/venv/bin/superset db upgrade
```

### Query timeout trên bảng ticks (82M rows)

`superset_config.py` đã set `SUPERSET_WEBSERVER_TIMEOUT = 120` và Celery async. Nếu vẫn timeout:
- Tạo virtual dataset với pre-aggregated SQL thay vì query raw ticks
- Thêm index: `CREATE INDEX idx_ticks_time ON ticks (tick_time);`

### Redis connection refused

```bash
systemctl status redis-server
systemctl restart redis-server
```
