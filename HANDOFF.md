# HANDOFF — Data Lakehouse / Superset Deployment

> Session: 2026-04-14 | Agent: Claude Opus 4.6

## Goal

Cài Apache Superset native (không Docker) trên LXC 205, kết nối PG Gold, tạo MCP server để Claude tự tạo dashboards, seed 3 dashboards ban đầu.

## Current Progress

**Superset fully deployed and operational:**

- Superset 4.1.4 running on LXC 205 (`superset-signalhub`)
  - Tailscale: `100.104.77.58:8088`
  - LAN: `192.168.0.116:8088`
  - Admin: `admin` / `datagaze2026`
- PG Gold connected via LAN `192.168.0.113:5432/stock_market`
- MCP server written + configured in `DataGaze/.claude/settings.json`
- 3 dashboards seeded: Market Overview, Top Movers, Trading Activity
- Docs fully rewritten: `docs/superset-setup.md`, `docs/superset-mcp.md`
- Vault updated: `infra/superset` v3 (all creds + IPs)
- 3 commits on `main`: `b420403`, `32447a2`, `695d743`

## What Worked

- **Python 3.11.12** from source — correct version for Superset 4.x
- **`su - postgres`** thay vì `sudo -u postgres` — LXC không có sudo
- **`setuptools<75`** — Superset dùng `pkg_resources` (removed in 78+)
- **`flask-cors`** phải cài riêng — không auto-install dù config ENABLE_CORS
- **LAN IP** (`192.168.0.113`) cho PG Gold — LXC 205 cùng bridge Proxmox
- **Python `requests.Session()`** cho Superset API — CSRF token cần match session cookies
- **`uv` pip install** nhanh hơn pip nhưng cùng numpy issue — cuối cùng dùng pip thuần trên 3.11
- **Tailscale trên LXC** cần TUN device: thêm `lxc.cgroup2.devices.allow: c 10:200 rwm` + mount entry

## What Didn't Work

- **Python 3.12** — Superset 4.x pins `numpy==1.23.5` cần `distutils` (removed in 3.12). Mất ~30 min debug pip build isolation failures trước khi switch sang 3.11
- **pip build isolation** trên Python 3.12 — numpy build env kéo old setuptools thiếu `pkgutil.ImpImporter`. `--prefer-binary`, `PIP_CONSTRAINT`, `--no-build-isolation` đều fail
- **curl shell cho Superset API POST** — CSRF session token require cookies match. Curl `-b cookies.txt` không đủ. Phải dùng Python `requests.Session()` để login + csrf + POST trong 1 session
- **`sudo`** trong LXC — không tồn tại by default
- **Tailscale** trên unprivileged LXC — fail `no socket` cho tới khi add TUN device config trên Proxmox host

## Remaining Work (cần fix)

### 1. Install script Step 9 (`add_pg_gold`) — BROKEN
- **File:** `scripts/install_superset.sh:335-393`
- **Problem:** Dùng curl shell cho CSRF — đã chứng minh không work
- **Fix:** Rewrite dùng Python requests session (pattern đã test thành công ở deployment)
- **Ưu tiên:** Medium (script vẫn dùng được, chỉ Step 9 fail → add PG Gold thủ công)

### 2. Install script `write_config()` thiếu RESULTS_BACKEND
- **File:** `scripts/install_superset.sh:147-222`
- **Problem:** Config template không có `RESULTS_BACKEND` → SQL Lab async fail
- **Fix:** Thêm `from cachelib.redis import RedisCache; RESULTS_BACKEND = RedisCache(host="localhost", port=6379, db=4)` vào template
- **Note:** Đã fix thủ công trên LXC 205, chỉ script chưa update

### 3. MCP server chưa test live trong Claude Code
- MCP configured tại `DataGaze/.claude/settings.json`
- Cần restart Claude Code session để load MCP server
- Test: invoke `list_dashboards` tool trong conversation mới

### 4. PROGRESS.md chưa update
- File: `data-lakehouse/.claude/PROGRESS.md`
- Cần thêm Superset deployment vào "Đã hoàn thành"

### 5. Thêm dashboards qua MCP
- User đã yêu cầu tạo dashboards — chưa làm qua MCP (chỉ qua seed script)
- Test MCP tools create chart/dashboard end-to-end

## Key Files

| File | Mô tả |
|------|-------|
| `scripts/install_superset.sh` | Install script (cần fix Step 9 + RESULTS_BACKEND) |
| `scripts/seed_dashboards.py` | Seed 3 dashboards (đã test, idempotent) |
| `mcp/superset-mcp/server.py` | MCP server (10 tools) |
| `mcp/superset-mcp/client.py` | Superset API client (requests-based) |
| `docs/superset-setup.md` | Setup guide (rewritten 2026-04-14) |
| `docs/superset-mcp.md` | MCP reference (rewritten 2026-04-14) |
| `DataGaze/.claude/settings.json` | MCP config cho Claude Code |

## Credentials

- Superset admin: `admin` / `datagaze2026`
- PG Gold: `stock` / `***` @ `192.168.0.113:5432/stock_market`
- Vault: `infra/superset` v3 trên LXC 200 (`100.64.176.104:8200`)
- Vault root token: xem `/root/.vault-init/init-keys.json` trên LXC 200

## Resume Command

```
Đọc HANDOFF.md và .claude/PROGRESS.md trong data-lakehouse.
Fix install script (Step 9 rewrite Python + RESULTS_BACKEND), 
update PROGRESS.md, rồi test MCP tools trong session này.
```
