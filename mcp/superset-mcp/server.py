"""MCP server for Apache Superset.

Lets Claude create datasets, charts, dashboards, and run SQL queries
against any Superset instance.

Config via env:
    SUPERSET_URL      — e.g. http://192.168.0.116:8088
    SUPERSET_USER     — admin username
    SUPERSET_PASSWORD  — admin password
"""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from client import SupersetClient

mcp = FastMCP(
    "superset-mcp",
    description="Create and manage Superset dashboards, charts, datasets, and run SQL",
)

_client: SupersetClient | None = None


def get_client() -> SupersetClient:
    global _client
    if _client is None:
        _client = SupersetClient(
            base_url=os.environ["SUPERSET_URL"],
            username=os.environ["SUPERSET_USER"],
            password=os.environ["SUPERSET_PASSWORD"],
        )
    return _client


# ── Database tools ────────────────────────────────────────────────


@mcp.tool()
def list_databases() -> str:
    """List all database connections configured in Superset."""
    dbs = get_client().list_databases()
    rows = [{"id": d["id"], "name": d["database_name"]} for d in dbs]
    return json.dumps(rows, indent=2)


# ── Dataset tools ─────────────────────────────────────────────────


@mcp.tool()
def list_datasets() -> str:
    """List all datasets (tables/views) available in Superset."""
    ds = get_client().list_datasets()
    rows = [
        {"id": d["id"], "table_name": d.get("table_name"), "database": d.get("database", {}).get("database_name")}
        for d in ds
    ]
    return json.dumps(rows, indent=2)


@mcp.tool()
def create_dataset(database_id: int, table_name: str, schema: str = "public") -> str:
    """Register a physical table as a Superset dataset for charting.

    Args:
        database_id: ID of the database connection (from list_databases)
        table_name: Name of the table (e.g. "daily_ohlcv")
        schema: PostgreSQL schema (default "public")
    """
    result = get_client().create_dataset(database_id, table_name, schema)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_virtual_dataset(
    database_id: int, name: str, sql: str, schema: str = "public"
) -> str:
    """Create a virtual dataset from a SQL query (like a view).

    Args:
        database_id: ID of the database connection
        name: Display name for the dataset
        sql: SQL query that defines the dataset
        schema: PostgreSQL schema (default "public")
    """
    result = get_client().create_virtual_dataset(database_id, name, sql, schema)
    return json.dumps(result, indent=2)


# ── Chart tools ───────────────────────────────────────────────────


@mcp.tool()
def list_charts() -> str:
    """List all charts in Superset."""
    charts = get_client().list_charts()
    rows = [
        {"id": c["id"], "name": c.get("slice_name"), "viz_type": c.get("viz_type")}
        for c in charts
    ]
    return json.dumps(rows, indent=2)


@mcp.tool()
def create_chart(
    name: str,
    viz_type: str,
    datasource_id: int,
    metrics: str,
    groupby: str = "",
    time_column: str = "",
    time_grain: str = "",
    filters: str = "",
    order_by: str = "",
    row_limit: int = 10000,
) -> str:
    """Create a chart in Superset.

    Args:
        name: Chart title
        viz_type: Visualization type. Common types:
            - "echarts_timeseries_line" (line chart)
            - "echarts_timeseries_bar" (bar chart)
            - "echarts_area" (area chart)
            - "pie" (pie chart)
            - "table" (data table)
            - "big_number_total" (single big number)
            - "dist_bar" (bar chart distribution)
            - "heatmap" (heatmap)
        datasource_id: Dataset ID (from list_datasets or create_dataset)
        metrics: JSON array of metrics. Examples:
            '[{"label":"count","expressionType":"SIMPLE","aggregate":"COUNT","column":{"column_name":"symbol"}}]'
            '[{"label":"avg_price","expressionType":"SQL","sqlExpression":"AVG(close)"}]'
        groupby: JSON array of column names to group by. E.g. '["symbol","trade_date"]'
        time_column: Time column for time-series charts (e.g. "trade_date")
        time_grain: Time grain — "P1D" (day), "P1W" (week), "P1M" (month)
        filters: JSON array of adhoc filters. E.g. '[{"col":"symbol","op":"==","val":"VNM"}]'
        order_by: JSON array of [column, ascending] pairs. E.g. '[["volume", false]]'
        row_limit: Max rows to fetch (default 10000)
    """
    params: dict = {
        "metrics": json.loads(metrics),
        "row_limit": row_limit,
        "viz_type": viz_type,
    }
    if groupby:
        params["groupby"] = json.loads(groupby)
    if time_column:
        params["granularity_sqla"] = time_column
    if time_grain:
        params["time_grain_sqla"] = time_grain
    if filters:
        adhoc = []
        for f in json.loads(filters):
            adhoc.append({
                "clause": "WHERE",
                "comparator": f["val"],
                "expressionType": "SIMPLE",
                "operator": f["op"],
                "subject": f["col"],
            })
        params["adhoc_filters"] = adhoc
    if order_by:
        params["order_by_cols"] = json.loads(order_by)

    result = get_client().create_chart(name, viz_type, datasource_id, params)
    return json.dumps(result, indent=2)


# ── Dashboard tools ───────────────────────────────────────────────


@mcp.tool()
def list_dashboards() -> str:
    """List all dashboards in Superset."""
    dbs = get_client().list_dashboards()
    rows = [
        {"id": d["id"], "title": d.get("dashboard_title"), "url": d.get("url")}
        for d in dbs
    ]
    return json.dumps(rows, indent=2)


@mcp.tool()
def create_dashboard(title: str, slug: str = "") -> str:
    """Create a new empty dashboard.

    Args:
        title: Dashboard title
        slug: URL-friendly slug (optional, auto-generated if empty)
    """
    result = get_client().create_dashboard(title, slug or None)
    return json.dumps(result, indent=2)


@mcp.tool()
def add_charts_to_dashboard(dashboard_id: int, chart_ids: str) -> str:
    """Add one or more charts to an existing dashboard.

    Args:
        dashboard_id: Dashboard ID
        chart_ids: JSON array of chart IDs to add. E.g. "[1, 2, 3]"
    """
    ids = json.loads(chart_ids)
    client = get_client()

    # Build position JSON — simple grid layout
    position: dict = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
        "GRID_ID": {
            "children": [],
            "id": "GRID_ID",
            "parents": ["ROOT_ID"],
            "type": "GRID",
        },
        "HEADER_ID": {
            "id": "HEADER_ID",
            "type": "HEADER",
            "meta": {"text": ""},
        },
    }

    row_children = []
    for i, cid in enumerate(ids):
        chart_key = f"CHART-{cid}"
        row_key = f"ROW-{i}"
        position[chart_key] = {
            "children": [],
            "id": chart_key,
            "meta": {
                "chartId": cid,
                "height": 50,
                "sliceName": f"Chart {cid}",
                "width": 6,
            },
            "parents": ["ROOT_ID", "GRID_ID", row_key],
            "type": "CHART",
        }
        position[row_key] = {
            "children": [chart_key],
            "id": row_key,
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "parents": ["ROOT_ID", "GRID_ID"],
            "type": "ROW",
        }
        row_children.append(row_key)

    position["GRID_ID"]["children"] = row_children

    result = client.update_dashboard(
        dashboard_id,
        {"position_json": json.dumps(position)},
    )
    return json.dumps({"status": "ok", "dashboard_id": dashboard_id, "charts_added": len(ids)})


# ── SQL Lab ───────────────────────────────────────────────────────


@mcp.tool()
def run_sql(database_id: int, sql: str, limit: int = 1000) -> str:
    """Run a SQL query in Superset SQL Lab and return results.

    Args:
        database_id: Database connection ID (from list_databases)
        sql: SQL query to execute
        limit: Max rows to return (default 1000)
    """
    result = get_client().run_sql(database_id, sql, limit=limit)
    # Simplify output — return columns + first N rows
    columns = result.get("columns", [])
    data = result.get("data", [])
    return json.dumps(
        {
            "columns": [c.get("column_name", c.get("name", "")) for c in columns],
            "data": data[:limit],
            "row_count": len(data),
        },
        indent=2,
        default=str,
    )


# ── Entry point ───────────────────────────────────────────────────


def main():
    mcp.run()


if __name__ == "__main__":
    main()
