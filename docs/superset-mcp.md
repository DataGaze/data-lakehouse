# Superset MCP Server

MCP server cho phép Claude tạo/quản lý datasets, charts, dashboards trên Superset qua REST API.

## Setup

### 1. Install dependencies

```bash
cd mcp/superset-mcp
pip install -e .
# hoặc
pip install mcp httpx
```

### 2. Lấy credentials từ Vault

Credentials lưu ở Vault (LXC 200, `https://100.64.176.104:8200`):

```bash
export VAULT_ADDR=https://100.64.176.104:8200
export VAULT_SKIP_VERIFY=true
vault login  # root token hoặc AppRole

# Đọc superset creds (sau khi đã store)
vault kv get infra/superset
```

### 3. Cấu hình Claude Code

Thêm vào `~/.claude/settings.json` (hoặc project settings):

```json
{
  "mcpServers": {
    "superset": {
      "command": "python3",
      "args": ["/Users/hoangnguyen/All_projects/DataGaze/data-lakehouse/mcp/superset-mcp/server.py"],
      "env": {
        "SUPERSET_URL": "http://100.104.77.58:8088",
        "SUPERSET_USER": "admin",
        "SUPERSET_PASSWORD": "<from-vault>"
      }
    }
  }
}
```

Đã cấu hình sẵn tại `DataGaze/.claude/settings.json`. MCP server sẽ tự start khi Claude Code mở trong DataGaze workspace.

## Available Tools

| Tool | Mô tả |
|------|-------|
| `list_databases` | Liệt kê database connections |
| `list_datasets` | Liệt kê datasets (tables/views) |
| `create_dataset` | Đăng ký physical table làm dataset |
| `create_virtual_dataset` | Tạo dataset từ SQL query |
| `list_charts` | Liệt kê charts |
| `create_chart` | Tạo chart (line, bar, table, heatmap...) |
| `list_dashboards` | Liệt kê dashboards |
| `create_dashboard` | Tạo dashboard mới |
| `add_charts_to_dashboard` | Gắn charts vào dashboard |
| `run_sql` | Chạy SQL query trực tiếp |

## Usage Examples

### Claude tự tạo dashboard

```
User: "Tạo dashboard tracking top 10 cổ phiếu volume cao nhất tuần này"

Claude sẽ:
1. list_databases → tìm PG Gold ID
2. create_virtual_dataset → SQL top 10 by volume
3. create_chart → bar chart volume
4. create_dashboard → "Top Volume Weekly"
5. add_charts_to_dashboard → gắn chart vào
```

### Chạy ad-hoc SQL

```
User: "Kiểm tra volume trung bình của VNM 30 ngày gần nhất"

Claude sẽ:
1. run_sql → SELECT AVG(volume) FROM daily_ohlcv WHERE symbol='VNM' AND trade_date >= CURRENT_DATE - 30
```

## Chart viz_type Reference

| Type | viz_type string |
|------|----------------|
| Line chart | `echarts_timeseries_line` |
| Bar chart | `echarts_timeseries_bar` |
| Area chart | `echarts_area` |
| Pie chart | `pie` |
| Table | `table` |
| Big number | `big_number_total` |
| Heatmap | `heatmap` |
| Scatter | `echarts_timeseries_scatter` |

## Vault Integration

Store Superset admin credentials vào Vault:

```bash
vault kv put infra/superset \
    url=http://192.168.0.116:8088 \
    admin_user=admin \
    admin_pass=<password>
```

Script wrapper để launch MCP với Vault:

```bash
#!/bin/bash
export VAULT_ADDR=https://100.64.176.104:8200
export VAULT_SKIP_VERIFY=true
CREDS=$(vault kv get -format=json infra/superset)
export SUPERSET_URL=$(echo $CREDS | jq -r '.data.data.url')
export SUPERSET_USER=$(echo $CREDS | jq -r '.data.data.admin_user')
export SUPERSET_PASSWORD=$(echo $CREDS | jq -r '.data.data.admin_pass')
python /path/to/server.py
```
