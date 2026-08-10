# HANDOFF — Data Lakehouse

> Phiên gần nhất: 2026-08-05 (gỡ Prefect → Dagster) | Agent: Claude Opus 5
> Phiên trước: 2026-08-05 tối (khung nâng cấp 6 tầng) · 2026-04-14 (Superset)

---

## Phiên 2026-08-05 — Gỡ Prefect, chốt hướng Dagster

### Goal

User: *"tôi muốn huỷ prefect đi. thay vào đó là dagster"* — gỡ Prefect khỏi toàn bộ hệ thống
(hạ tầng, code, toolkit, tài liệu) và chốt hướng thay thế.

### Phát hiện xoay bản chất công việc

Đây **không phải migration**. Kiểm tra trực tiếp trước khi làm cho thấy Prefect chưa bao giờ
vào vận hành, dù tài liệu 3 repo mô tả nó như hệ thống đang chạy:

| Chỉ số | Đo được 2026-08-05 |
|---|---|
| Deployment đăng ký trên `prefect-server` | **0** |
| Flow run từ 2026-04-02 tới 2026-08-05 | **0** |
| CPU `prefect-worker` tiêu thụ trong 2,5 tuần | 6 phút 49 giây (chỉ poll pool rỗng) |
| Cron/timer gọi ETL trên LXC 202 | không có |

Nguyên nhân: `serve.py` — thứ đăng ký 2 deployment `daily-stock-etl` + `stock-healthcheck` —
chưa từng được chạy. Backlog `PMO01-myplan/.../backlog_data_pipeline.md` có mục
"Enable Prefect schedule" vẫn `[ ]`.

Hệ quả: không có state lịch sử để migrate; việc thật là teardown + dựng mới, và **tiêu chí
nghiệm thu là một chu kỳ ETL thật chạy xanh qua Dagster**, không phải "Dagster cài xong".

### Đã hoàn thành — 9 commit trên 8 repo

| Repo | Commit | Nội dung |
|---|---|---|
| `BIZ01-datagaze/stock-data-pipeline` | `cd6b96d` | Gỡ decorator `@flow`/`@task`, import, dependency, `PREFECT_API_URL`, fixture test; xóa `serve.py` |
| `DEV01-agent-toolkit/agentsmith` | `1e95cf6`, `5fbc162` | Gỡ `prefect-run.sh` + 4 test + dòng README/SKILL/config.env.example; plugin `infra` 0.1.0→0.2.0 |
| `OPS01-homelab` | `77a5cc6`, `fbb4e93` | infra-overview, 2 doc setup LXC, spec windmill |
| `DATA02-lakehouse` | `bcb4558` | ADR mới + 12 file docs |
| `BIZ01-datagaze` | `3a50543` | 4 doc kiến trúc + ADR 0003/0004 |
| `PMO01-myplan` | `bd700d6` | Backlog + architecture note + `_overview` |
| `BIZ07-kol-studio` | `e17bfb1` | Sửa tiền đề sai trong bảng quyết định |
| `PER01-lifeos/01-Tracking` | `9c7b026` | Backlog log-shipping |

Hạ tầng: `prefect-server` (LXC 201) và `prefect-worker` (LXC 202) stopped + disabled.
`OPS01-homelab` cũng được merge fast-forward `feat/labelstudio-as-code` → `main` trong phiên này.

### Ba lựa chọn biên tập đã áp dụng cho tài liệu

1. **ADR không bị sửa nội dung.** `docs/adr/2026-04-13-platform-decisions.md` giữ nguyên chữ,
   chỉ gắn nhãn superseded ở D4 và ở Status. Quyết định mới nằm ở ADR riêng.
2. **Không thay "Prefect" → "Dagster" trong tài liệu vận hành.** `docs/runbook.md` và
   `docs/security.md` dùng banner đầu file + nhãn từng mục, vì mô tả chi tiết Dagster khi nó
   chưa dựng là thay một tập tài liệu hư cấu bằng tập khác.
3. **Sửa những chỗ có hệ quả thật:** `PREFECT_API_KEY` (S-11) ra khỏi lịch rotate, cổng 4200
   đánh dấu chết, ACL Tailscale `tag:prefect` ghi là thu hồi được, và món nợ "wire refresh
   `mv_*` vào ETL" trong `BIZ01-datagaze/docs/adr/0004-sql-as-query-layer.md` được nêu lại
   vì giờ không còn chỗ nào để wire vào.

### Diễn biến sau phiên (đã verify lại 2026-08-10)

- **LXC 201 đã bị xóa hẳn** — không còn trong `pct list` (200 nhảy thẳng sang 202). ADR ban đầu
  ghi "giữ container để tái dùng cho Dagster"; điều đó **không còn đúng** — Dagster phải dựng
  container mới theo khuôn as-code. `OPS01-homelab` commit `c3e7521` đã purge khỏi inventory.
- `prefect-worker` trên LXC 202: `inactive` + `disabled` (xác nhận lại hôm nay). Venv
  `/opt/prefect/` chưa xóa.
- Phiên tối 2026-08-05 (`e86f0c7`) mở rộng phạm vi thành **khung 6 tầng + thứ tự thi công**:
  `docs/2026-08-05-lakehouse-upgrade-framework__ai1.md`. Trong đó Dagster là **bước 4**, đứng sau
  backup (0a/0b), SeaweedFS as-code (1), Loki/Grafana (2), Iceberg catalog (3). Phiên đó cũng
  phát hiện VM 106 và cả 2 node K3s đều không còn tồn tại.

### Lessons

- **[VERIFIED]** Tài liệu kiến trúc mô tả một hệ thống "đang chạy" mà chưa ai kiểm chứng · scope: `both`
  - Lesson: Đo hạ tầng thật TRƯỚC khi sửa tài liệu theo nó. Ở đây 3 repo (~146 chỗ) mô tả
    Prefect như đang chạy lịch 17:30, thực tế 0 flow run trong 4 tháng. Nếu tin tài liệu, việc
    sẽ bị hiểu nhầm thành "migration Prefect → Dagster" và tốn công vô ích cho state không tồn tại.
  - Evidence: `curl -s -X POST http://127.0.0.1:4200/api/deployments/filter -d '{"limit":50}'` → `0`;
    `curl -s -X POST http://127.0.0.1:4200/api/flow_runs/count -d '{}'` → `0`
- **[VERIFIED]** Sửa tài liệu cho một thứ chưa dựng · scope: `both`
  - Lesson: Khi công cụ cũ đã gỡ mà công cụ mới chưa dựng, dùng **banner trạng thái + nhãn từng
    mục**, đừng thay tên công cụ. Thay `prefect deployment run ...` bằng lệnh Dagster tưởng
    tượng là tạo ra tài liệu sai lần thứ hai — đúng cái vừa phải dọn.
  - Evidence: `docs/runbook.md:16-25` (banner), `docs/security.md:13-21`
- **[VERIFIED]** `sed` trên macOS không hiểu `\b` · scope: `both`
  - Lesson: BSD sed im lặng không khớp `\b` (không báo lỗi, chỉ không đổi gì) — dùng `perl -pi -e`
    cho word-boundary. Kiểm lại bằng grep sau mỗi lần thay hàng loạt, đừng tin exit code 0.
  - Evidence: `sed -i '' 's/\blog\./logger./g' ingestion/r2_to_bronze.py` → 12 chỗ `log.` còn nguyên;
    `perl -pi -e 's/\blog\./logger./g'` → 0 chỗ còn lại, 0 chỗ `loggerger`
- **[VERIFIED]** `cd` trong Bash tool bám sang lệnh sau · scope: `claude`
  - Lesson: Working directory persist giữa các lần gọi Bash. Sau một lệnh có `cd`, lệnh kế tiếp
    dùng đường dẫn tương đối sẽ chạy sai chỗ. Dùng đường dẫn tuyệt đối hoặc `git -C <repo>`.
  - Evidence: gọi lần 2 `cd BIZ01-datagaze/stock-data-pipeline` → `no such file or directory`
    vì cwd đã là chính thư mục đó
- **[VERIFIED]** Merge branch về main khi working tree có việc dở của phiên khác · scope: `both`
  - Lesson: `git branch -f main <branch>` rồi `git checkout main` cập nhật ref mà **không đụng
    working tree** — an toàn khi fast-forward được. `git merge` thông thường sẽ vướng file dirty.
    Kiểm FF trước bằng `git merge-base --is-ancestor main <branch>`.
  - Evidence: `OPS01-homelab` — sau merge, 3 thay đổi labelstudio chưa commit vẫn nguyên vẹn
    trong `git status`
- **[VERIFIED]** `timeout` không tồn tại trên máy này · scope: `both`
  - Lesson: Cả `timeout` lẫn `gtimeout` đều chưa cài (`coreutils` chưa có). Với lệnh SSH dùng
    `ssh -o ConnectTimeout=8 -o BatchMode=yes`; với Bash tool dùng tham số `timeout`.
  - Evidence: `timeout 25 ssh ...` → `(eval):1: command not found: timeout`
- **[PROPOSED]** Dagster không nhẹ hơn Prefect về vận hành · scope: `both`
  - Lesson: Nó cần webserver + daemon + Postgres metadata. Nếu động cơ chỉ là "cho gọn" thì
    `systemd timer` gọi `python -m etl.orchestrator` mới là phương án gọn nhất. Chọn Dagster vì
    partition/backfill và lineage, không vì nhẹ. (Chưa đo thực tế vì chưa dựng.)

### Còn treo — việc tiếp theo

1. **Chốt phương án mô hình hóa Dagster.** Đã trình 3 phương án, user chưa trả lời:
   - A — job/op lift-and-shift (bọc `run_stock_pipeline()` thành 1 job)
   - B — asset-centric thuần (viết lại `etl/stock/*` theo asset)
   - **C — asset mỏng bọc code thuần (khuyến nghị):** `@asset` 5–15 dòng gọi thẳng
     `process_date()` / `load_ticks_to_gold()` đang có; logic Python giữ nguyên, testable, chạy
     tay vẫn được; đổi ý lần nữa thì chỉ bỏ ~100 dòng khai báo chứ không mất pipeline.

   Chốt xong → viết spec vào `docs/superpowers/specs/2026-08-XX-dagster-orchestration-design.md`
   để duyệt trước khi đụng hạ tầng.
2. **Dagster là bước 4, không phải bước 1.** Theo `docs/2026-08-05-lakehouse-upgrade-framework__ai1.md`
   §6.1, phải xong 0a/0b (vzdump + pg_dump + backup Vault), 1 (SeaweedFS as-code), 2 (Loki),
   3 (Iceberg catalog trên PG 204) trước. Dựng Dagster trước khi có log là tự làm mù mình.
3. **Chưa push repo nào.** `DATA02-lakehouse` ahead 4, `agentsmith` ahead 22, `OPS01-homelab`
   ahead 16, `PMO01-myplan` ahead 25, `stock-data-pipeline` ahead 1.
4. **Venv `/opt/prefect/` trên LXC 202 chưa xóa** — chiếm chỗ, không còn dùng.
5. **ADR cần sửa một câu.** `docs/adr/2026-08-05-retire-prefect-adopt-dagster.md` mục
   Consequences ghi "Container 201 giữ lại để tái dùng IP/tài nguyên" — container đã bị xóa,
   câu này giờ sai.

### Hai lỗi sẵn có, không thuộc phạm vi phiên này

- `BIZ01-datagaze/stock-data-pipeline/pyproject.toml` thiếu `boto3` và `moto` dù code và test đã dùng.
- `ingestion/r2_to_bronze.py` (untracked từ 2026-04-14) import `config.settings.R2Config` —
  class **chưa từng tồn tại** trong repo. File đó cùng `tests/test_r2_to_bronze.py` chưa bao giờ
  chạy được; đã sửa sạch Prefect nhưng vẫn để untracked, không commit hộ việc dở.

### Resume command

```
Đọc HANDOFF.md + .claude/PROGRESS.md trong DATA02-lakehouse.
Prefect đã gỡ xong (9 commit, 8 repo). Việc tiếp: chốt phương án mô hình hóa Dagster
(A/B/C — khuyến nghị C), nhớ Dagster là bước 4 trong docs/2026-08-05-lakehouse-upgrade-framework__ai1.md
§6.1 nên backup + SeaweedFS as-code + Loki + Iceberg catalog phải xong trước.
Sửa luôn câu "giữ lại container 201" trong ADR 2026-08-05 — container đã bị xóa.
```

---

## Phiên 2026-04-14 — Superset Deployment

> Agent: Claude Opus 4.6

### Goal

Cài Apache Superset native (không Docker) trên LXC 205, kết nối PG Gold, tạo MCP server để Claude tự tạo dashboards, seed 3 dashboards ban đầu.

### Current Progress

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

### What Worked

- **Python 3.11.12** from source — correct version for Superset 4.x
- **`su - postgres`** thay vì `sudo -u postgres` — LXC không có sudo
- **`setuptools<75`** — Superset dùng `pkg_resources` (removed in 78+)
- **`flask-cors`** phải cài riêng — không auto-install dù config ENABLE_CORS
- **LAN IP** (`192.168.0.113`) cho PG Gold — LXC 205 cùng bridge Proxmox
- **Python `requests.Session()`** cho Superset API — CSRF token cần match session cookies
- **`uv` pip install** nhanh hơn pip nhưng cùng numpy issue — cuối cùng dùng pip thuần trên 3.11
- **Tailscale trên LXC** cần TUN device: thêm `lxc.cgroup2.devices.allow: c 10:200 rwm` + mount entry

### What Didn't Work

- **Python 3.12** — Superset 4.x pins `numpy==1.23.5` cần `distutils` (removed in 3.12). Mất ~30 min debug pip build isolation failures trước khi switch sang 3.11
- **pip build isolation** trên Python 3.12 — numpy build env kéo old setuptools thiếu `pkgutil.ImpImporter`. `--prefer-binary`, `PIP_CONSTRAINT`, `--no-build-isolation` đều fail
- **curl shell cho Superset API POST** — CSRF session token require cookies match. Curl `-b cookies.txt` không đủ. Phải dùng Python `requests.Session()` để login + csrf + POST trong 1 session
- **`sudo`** trong LXC — không tồn tại by default
- **Tailscale** trên unprivileged LXC — fail `no socket` cho tới khi add TUN device config trên Proxmox host

### Remaining Work (cần fix)

#### 1. Install script Step 9 (`add_pg_gold`) — BROKEN
- **File:** `scripts/install_superset.sh:335-393`
- **Problem:** Dùng curl shell cho CSRF — đã chứng minh không work
- **Fix:** Rewrite dùng Python requests session (pattern đã test thành công ở deployment)
- **Ưu tiên:** Medium (script vẫn dùng được, chỉ Step 9 fail → add PG Gold thủ công)

#### 2. Install script `write_config()` thiếu RESULTS_BACKEND
- **File:** `scripts/install_superset.sh:147-222`
- **Problem:** Config template không có `RESULTS_BACKEND` → SQL Lab async fail
- **Fix:** Thêm `from cachelib.redis import RedisCache; RESULTS_BACKEND = RedisCache(host="localhost", port=6379, db=4)` vào template
- **Note:** Đã fix thủ công trên LXC 205, chỉ script chưa update

#### 3. MCP server chưa test live trong Claude Code
- MCP configured tại `DataGaze/.claude/settings.json`
- Cần restart Claude Code session để load MCP server
- Test: invoke `list_dashboards` tool trong conversation mới

#### 4. Thêm dashboards qua MCP
- User đã yêu cầu tạo dashboards — chưa làm qua MCP (chỉ qua seed script)
- Test MCP tools create chart/dashboard end-to-end

### Key Files

| File | Mô tả |
|------|-------|
| `scripts/install_superset.sh` | Install script (cần fix Step 9 + RESULTS_BACKEND) |
| `scripts/seed_dashboards.py` | Seed 3 dashboards (đã test, idempotent) |
| `mcp/superset-mcp/server.py` | MCP server (10 tools) |
| `mcp/superset-mcp/client.py` | Superset API client (requests-based) |
| `docs/superset-setup.md` | Setup guide (rewritten 2026-04-14) |
| `docs/superset-mcp.md` | MCP reference (rewritten 2026-04-14) |
| `DataGaze/.claude/settings.json` | MCP config cho Claude Code |

### Credentials

- Superset admin: `admin` / `datagaze2026`
- PG Gold: `stock` / `***` @ `192.168.0.113:5432/stock_market`
- Vault: `infra/superset` v3 trên LXC 200 (`100.64.176.104:8200`)
- Vault root token: xem `/root/.vault-init/init-keys.json` trên LXC 200
