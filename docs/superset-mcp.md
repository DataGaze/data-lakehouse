# Superset MCP Server

MCP server wrap Superset REST API v1 — cho phép Claude tạo datasets, charts, dashboards và chạy SQL trực tiếp.

## Status hiện tại

- **Đã cấu hình** tại `DataGaze/.claude/settings.json`
- MCP server tự start khi Claude Code mở trong DataGaze workspace
- Kết nối qua Tailscale: `http://100.104.77.58:8088`
- 10 tools available (xem bảng bên dưới)

## Cấu trúc files

```
data-lakehouse/mcp/superset-mcp/
├── pyproject.toml    # Package metadata, deps: mcp + httpx
├── server.py         # MCP server — FastMCP, 10 tool definitions
└── client.py         # SupersetClient — thin wrapper REST API v1
```

## Setup

### Dependencies

```bash
cd data-lakehouse/mcp/superset-mcp
pip install mcp httpx
# hoặc
pip install -e .
```

### Claude Code config

Đã cấu hình tại `DataGaze/.claude/settings.json`:

```json
{
  "mcpServers": {
    "superset": {
      "command": "python3",
      "args": ["<path>/data-lakehouse/mcp/superset-mcp/server.py"],
      "env": {
        "SUPERSET_URL": "http://100.104.77.58:8088",
        "SUPERSET_USER": "admin",
        "SUPERSET_PASSWORD": "<from vault infra/superset>"
      }
    }
  }
}
```

### Lấy password từ Vault

```bash
export VAULT_ADDR=https://100.64.176.104:8200 VAULT_SKIP_VERIFY=true
vault login
vault kv get -field=admin_pass infra/superset
```

## Tools Reference

### Database

| Tool | Input | Output | Mô tả |
|------|-------|--------|-------|
| `list_databases` | _(none)_ | `[{id, name}]` | Liệt kê database connections |

### Dataset

| Tool | Input | Output | Mô tả |
|------|-------|--------|-------|
| `list_datasets` | _(none)_ | `[{id, table_name, database}]` | Liệt kê tất cả datasets |
| `create_dataset` | `database_id`, `table_name`, `schema` | `{id, ...}` | Đăng ký physical table |
| `create_virtual_dataset` | `database_id`, `name`, `sql`, `schema` | `{id, ...}` | Tạo dataset từ SQL query |

### Chart

| Tool | Input | Output | Mô tả |
|------|-------|--------|-------|
| `list_charts` | _(none)_ | `[{id, name, viz_type}]` | Liệt kê charts |
| `create_chart` | `name`, `viz_type`, `datasource_id`, `metrics`, ... | `{id, ...}` | Tạo chart mới |

### Dashboard

| Tool | Input | Output | Mô tả |
|------|-------|--------|-------|
| `list_dashboards` | _(none)_ | `[{id, title, url}]` | Liệt kê dashboards |
| `create_dashboard` | `title`, `slug` | `{id, ...}` | Tạo dashboard rỗng |
| `add_charts_to_dashboard` | `dashboard_id`, `chart_ids` (JSON array) | `{status, charts_added}` | Gắn charts vào dashboard |

### SQL

| Tool | Input | Output | Mô tả |
|------|-------|--------|-------|
| `run_sql` | `database_id`, `sql`, `limit` | `{columns, data, row_count}` | Chạy SQL query, trả kết quả |

## create_chart chi tiết

### viz_type reference

| Loại | `viz_type` string |
|------|-------------------|
| Line chart | `echarts_timeseries_line` |
| Bar chart | `echarts_timeseries_bar` |
| Area chart | `echarts_area` |
| Pie chart | `pie` |
| Table | `table` |
| Big number | `big_number_total` |
| Heatmap | `heatmap` |
| Scatter | `echarts_timeseries_scatter` |

### metrics format

JSON array. Hai kiểu:

```json
// SIMPLE — aggregate trên column có sẵn
[{"label": "count", "expressionType": "SIMPLE", "aggregate": "COUNT", "column": {"column_name": "symbol"}}]

// SQL — expression tùy ý
[{"label": "avg_price", "expressionType": "SQL", "sqlExpression": "AVG(close)"}]
```

### Ví dụ tạo chart đầy đủ

```
create_chart(
    name="VNM Price 30D",
    viz_type="echarts_timeseries_line",
    datasource_id=3,
    metrics='[{"label":"close","expressionType":"SQL","sqlExpression":"AVG(close)"}]',
    groupby='["symbol"]',
    time_column="trade_date",
    time_grain="P1D",
    filters='[{"col":"symbol","op":"==","val":"VNM"}]',
    row_limit=100
)
```

## Usage Patterns

### Pattern 1: Tạo dashboard từ mô tả tự nhiên

```
User: "Tạo dashboard tracking top 10 volume tuần này"

Claude:
1. list_databases           → PG Gold id=1
2. create_virtual_dataset   → SQL top 10 by volume last 7 days
3. create_chart             → bar chart volume
4. create_chart             → table chi tiết
5. create_dashboard         → "Top Volume Weekly"
6. add_charts_to_dashboard  → gắn 2 charts
```

### Pattern 2: Ad-hoc data query

```
User: "Volume trung bình VNM 30 ngày?"

Claude:
1. run_sql → SELECT AVG(volume) FROM daily_ohlcv
              WHERE symbol='VNM'
              AND trade_date >= CURRENT_DATE - 30
```

### Pattern 3: Mở rộng dashboard có sẵn

```
User: "Thêm chart PE ratio vào Market Overview"

Claude:
1. list_dashboards          → Market Overview id=1
2. create_virtual_dataset   → SQL tính PE
3. create_chart             → line chart PE
4. add_charts_to_dashboard  → gắn vào dashboard 1
```

## Superset API Authentication Flow

MCP client xử lý tự động, nhưng để debug:

```
POST /api/v1/security/login     → JWT access_token
GET  /api/v1/security/csrf_token/ → CSRF token (cần cho mọi POST/PUT/DELETE)

Headers cho write operations:
  Authorization: Bearer <jwt>
  X-CSRFToken: <csrf>
  Referer: <base_url>     ← bắt buộc, nếu thiếu sẽ 400
  Content-Type: application/json
```

**Lưu ý:** CSRF token phải lấy trong cùng session (cookies) với JWT. Dùng `requests.Session()` (Python) hoặc `-b cookies.txt` (curl). Curl thuần không đủ — đã verify khi deploy.

## Troubleshooting

### MCP server không start

```bash
# Test thủ công
cd data-lakehouse/mcp/superset-mcp
SUPERSET_URL=http://100.104.77.58:8088 \
SUPERSET_USER=admin \
SUPERSET_PASSWORD=xxx \
python3 server.py
```

Lỗi phổ biến:
- `ModuleNotFoundError: mcp` → chưa install: `pip install mcp httpx`
- `Connection refused` → Superset chưa chạy hoặc Tailscale disconnected
- `401 Unauthorized` → sai password, check Vault `infra/superset`

### run_sql trả 500 "Results backend not configured"

Superset config trên LXC 205 thiếu `RESULTS_BACKEND`. Xem fix tại `docs/superset-setup.md` > Troubleshooting.

### create_chart fail 422

Dataset chưa được refresh metadata. Thử:
1. Mở Superset UI → Datasets → chọn dataset → "Sync columns from source"
2. Hoặc tạo virtual dataset mới với SQL rõ ràng
