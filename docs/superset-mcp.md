# Superset MCP Server

MCP server wrap Superset REST API v1 — cho phép client MCP tạo datasets, charts, dashboards và chạy SQL trực tiếp.

## Status hiện tại

- **Đã kiểm tra trực tiếp 2026-09-08:** Python MCP SDK 1.30.0, kết nối stdio, `initialize`, `tools/list` và `tools/call` tới Superset 4.1.4.
- Phiên thử từ Codex chạy client MCP tạm; chưa đăng ký server vào cấu hình MCP thường trực của Codex.
- Truyền địa chỉ đang chạy qua `SUPERSET_URL`; đối chiếu Tailscale và tài liệu vận hành trong `OPS01-homelab/services/superset/`.
- 12 tools available, gồm `update_chart` và `update_dashboard` để sửa biểu đồ, bố cục, CSS và metadata mà giữ các trường không được truyền vào.

## Cấu trúc files

```
data-lakehouse/mcp/superset-mcp/
├── pyproject.toml    # Package metadata, deps: mcp + httpx
├── server.py         # MCP server — FastMCP, 12 tool definitions
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

### Mẫu cấu hình Claude Code từ triển khai trước

Cấu hình trước đây đặt tại `DataGaze/.claude/settings.json`; vị trí đó chưa được kiểm tra lại trong phiên Codex 2026-09-08:

```json
{
  "mcpServers": {
    "superset": {
      "command": "python3",
      "args": ["<path>/data-lakehouse/mcp/superset-mcp/server.py"],
      "env": {
        "SUPERSET_URL": "http://<superset-host>:8088",
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
| `update_chart` | `chart_id`, `params` (JSON object) | `{id, ...}` | Gộp tham số mới vào cấu hình chart hiện có |

### Dashboard

| Tool | Input | Output | Mô tả |
|------|-------|--------|-------|
| `list_dashboards` | _(none)_ | `[{id, title, url}]` | Liệt kê dashboards |
| `create_dashboard` | `title`, `slug` | `{id, ...}` | Tạo dashboard rỗng |
| `update_dashboard` | `dashboard_id`, `properties` (JSON object) | `{id, ...}` | Cập nhật các trường như `position_json`, `css`, `json_metadata` |
| `add_charts_to_dashboard` | `dashboard_id`, `chart_ids` (JSON array) | `{status, charts_added}` | Gắn charts vào dashboard |

### SQL

| Tool | Input | Output | Mô tả |
|------|-------|--------|-------|
| `run_sql` | `database_id`, `sql`, `limit` | `{columns, data, row_count}` | Chạy SQL query, trả kết quả |

## Hành vi cần biết

Biểu đồ `pie` yêu cầu đúng một metric; server ánh xạ phần tử đó sang trường
`metric` của Superset. Danh sách rỗng hoặc nhiều metric bị từ chối. Khi gắn chart vào
dashboard, server cập nhật cả quan hệ chart–dashboard lẫn `position_json`, giữ các
dashboard khác của chart và không thêm quan hệ trùng khi gọi lại. Bố cục mặc định là
mỗi chart một hàng rộng đủ 12 cột.

Sau khi gắn charts, gọi `update_dashboard` với `position_json` để đặt bố cục tùy chỉnh.
Gọi lại `add_charts_to_dashboard` sẽ thay bố cục bằng lưới mặc định. Các trường
`position_json` và `json_metadata` trong `properties` là chuỗi JSON theo Superset API.
Với `big_number_total`, dùng `update_chart` để đặt `metric` đơn sau bước tạo chart.

## Phép thử API và MCP — 2026-09-08

Hai dashboard dùng PostgreSQL `llm_logs` trực tiếp qua connection số 6, tài khoản chỉ
đọc hiện có. Khoảng dữ liệu cố định: `[2026-08-25 00:00:00+07, 2026-09-08 00:00:00+07)`.
Chỉ số là số bản ghi đã nạp, không phải số request AI, chi phí hay năng suất.

| Đường tạo | Dashboard slug | Dataset | Chart IDs |
|---|---|---|---|
| REST API trực tiếp | `ai-activity-api-20260908` | 1 | 1, 2, 3, 7, 8, 9 |
| MCP stdio | `ai-activity-mcp-20260908` | 2 | 4, 5, 6, 10, 11, 12 |

Dataset và chart của bản MCP được tạo, sửa, gắn dashboard qua `tools/call`. Connection
PostgreSQL là phần chuẩn bị dùng chung qua REST API. Dashboard tiếp tục truy vấn nguồn
khi mở; không cần giữ tiến trình MCP hay Codex chạy.

Kiểm chứng: `POST /api/v1/chart/data` cho hai dataset trả dữ liệu khớp ở cả ba phép:
tỷ trọng 2 dòng, xu hướng 23 dòng, dự án 15 dòng. Claude Code 102.185 bản ghi, Codex
23.526; tổng 125.711. Đã kiểm tra giao diện Edge, biểu đồ tròn, đường và bảng tải được.
Test inline đã chạy cho metric pie hợp lệ/rỗng/nhiều phần tử, cập nhật chart giữ tham số
cũ, gắn chart giữ dashboard khác và không nhân đôi quan hệ khi gọi lại.

Thiết kế cập nhật cùng ngày: đầu trang nền xanh đậm ghi rõ khoảng ngày; ba KPI truy vấn
thật; donut tỷ trọng và đường theo ngày cạnh nhau; bảng Top 15 có số nguyên đầy đủ và
ô tìm kiếm. Claude Code dùng xanh `#2563EB`, Codex dùng cam `#D97706`. Nội dung rộng tối
đa 1560 px, có chú giải nguồn và định nghĩa chỉ số cuối trang. Bản API được cập nhật
qua REST; bản MCP qua `tools/call`, gồm cả bố cục và CSS qua `update_dashboard` mới.

Kiểm chứng bổ sung: sáu KPI trả đúng `[125711, 102185, 23526]` cho mỗi bản; tổng bằng
hai thành phần. Ba phép đối chiếu dữ liệu vẫn khớp sau thiết kế. Edge hiển thị đủ sáu
chart mỗi dashboard, không tràn ngang; ghi chú cuối trang không bị cắt. Test inline
`update_dashboard` đã chạy cho payload nguyên vẹn, CSS rỗng, không thêm trường ngoài
yêu cầu và JSON không hợp lệ. MCP SDK liệt kê đủ 12 tool và gọi cập nhật thật thành công.

Giả định thiết kế: giữ hai bản cùng giao diện và khoảng ngày cố định để so sánh đường
tạo báo cáo; không chuyển sang cửa sổ ngày tự động. Nội dung có grounding từ PostgreSQL,
trust level T1, chưa được người dùng audit; lần đối chiếu gần nhất 2026-09-08.

Phát hiện giới hạn môi trường: `SHOW server_encoding` trên `superset_meta` trả
`SQL_ASCII`; tạo chart có tên tiếng Việt và truy vấn có literal tiếng Việt gặp lỗi
`ascii codec`. Demo dùng tiêu đề tiếng Anh và SQL ASCII. Chưa đổi mã hóa database.

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
