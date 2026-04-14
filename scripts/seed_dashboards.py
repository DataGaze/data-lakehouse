#!/usr/bin/env python3
"""Seed initial stock market dashboards into Superset.

Creates datasets, charts, and 3 dashboards:
  1. Market Overview — OHLCV price + volume over time
  2. Top Movers — biggest gainers/losers today
  3. Trading Activity — tick distribution by hour/exchange

Usage:
    SUPERSET_URL=http://192.168.0.116:8088 \
    SUPERSET_USER=admin \
    SUPERSET_PASSWORD=xxx \
    python seed_dashboards.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp", "superset-mcp"))

from client import SupersetClient


def get_client() -> SupersetClient:
    return SupersetClient(
        base_url=os.environ["SUPERSET_URL"],
        username=os.environ["SUPERSET_USER"],
        password=os.environ["SUPERSET_PASSWORD"],
    )


def find_pg_gold_db(client: SupersetClient) -> int | None:
    """Find PG Gold database ID."""
    for db in client.list_databases():
        if "gold" in db.get("database_name", "").lower():
            return db["id"]
    return None


def create_datasets(client: SupersetClient, db_id: int) -> dict[str, int]:
    """Create physical + virtual datasets, return name->id map."""
    datasets: dict[str, int] = {}

    # Check existing datasets
    existing = {d.get("table_name"): d["id"] for d in client.list_datasets()}

    # 1. Physical: daily_ohlcv
    if "daily_ohlcv" not in existing:
        resp = client.create_dataset(db_id, "daily_ohlcv")
        datasets["daily_ohlcv"] = resp["id"]
        print(f"  Created dataset: daily_ohlcv (id={resp['id']})")
    else:
        datasets["daily_ohlcv"] = existing["daily_ohlcv"]
        print(f"  Dataset exists: daily_ohlcv (id={existing['daily_ohlcv']})")

    # 2. Virtual: top_movers (latest trading day gainers/losers)
    top_movers_sql = """
    WITH latest AS (
        SELECT MAX(trade_date) AS dt FROM daily_ohlcv
    ),
    prev AS (
        SELECT MAX(trade_date) AS dt FROM daily_ohlcv
        WHERE trade_date < (SELECT dt FROM latest)
    ),
    changes AS (
        SELECT
            t.symbol,
            t.close AS price,
            t.volume,
            t.value,
            ROUND(((t.close - p.close) / NULLIF(p.close, 0) * 100)::numeric, 2) AS pct_change
        FROM daily_ohlcv t
        JOIN daily_ohlcv p ON t.symbol = p.symbol
        CROSS JOIN latest l
        CROSS JOIN prev pr
        WHERE t.trade_date = l.dt AND p.trade_date = pr.dt
          AND t.close > 0 AND p.close > 0
    )
    SELECT * FROM changes
    WHERE pct_change IS NOT NULL
    ORDER BY ABS(pct_change) DESC
    """
    if "top_movers" not in existing:
        resp = client.create_virtual_dataset(db_id, "top_movers", top_movers_sql)
        datasets["top_movers"] = resp["id"]
        print(f"  Created dataset: top_movers (id={resp['id']})")
    else:
        datasets["top_movers"] = existing["top_movers"]
        print(f"  Dataset exists: top_movers (id={existing['top_movers']})")

    # 3. Virtual: hourly_ticks (tick activity by hour)
    hourly_sql = """
    SELECT
        tick_time::date AS trade_date,
        EXTRACT(HOUR FROM tick_time) AS hour,
        COUNT(*) AS tick_count,
        COUNT(DISTINCT symbol) AS symbols,
        SUM(volume) AS total_volume
    FROM ticks
    WHERE tick_time >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY 1, 2
    ORDER BY 1, 2
    """
    if "hourly_ticks" not in existing:
        resp = client.create_virtual_dataset(db_id, "hourly_ticks", hourly_sql)
        datasets["hourly_ticks"] = resp["id"]
        print(f"  Created dataset: hourly_ticks (id={resp['id']})")
    else:
        datasets["hourly_ticks"] = existing["hourly_ticks"]
        print(f"  Dataset exists: hourly_ticks (id={existing['hourly_ticks']})")

    # 4. Virtual: market_summary (daily aggregates)
    summary_sql = """
    SELECT
        trade_date,
        COUNT(DISTINCT symbol) AS symbols,
        SUM(volume) AS total_volume,
        SUM(value) AS total_value,
        COUNT(CASE WHEN close > open THEN 1 END) AS advances,
        COUNT(CASE WHEN close < open THEN 1 END) AS declines,
        COUNT(CASE WHEN close = open THEN 1 END) AS unchanged
    FROM daily_ohlcv
    GROUP BY trade_date
    ORDER BY trade_date
    """
    if "market_summary" not in existing:
        resp = client.create_virtual_dataset(db_id, "market_summary", summary_sql)
        datasets["market_summary"] = resp["id"]
        print(f"  Created dataset: market_summary (id={resp['id']})")
    else:
        datasets["market_summary"] = existing["market_summary"]
        print(f"  Dataset exists: market_summary (id={existing['market_summary']})")

    return datasets


def create_charts(
    client: SupersetClient, datasets: dict[str, int]
) -> dict[str, int]:
    """Create charts, return name->id map."""
    charts: dict[str, int] = {}

    # Check existing
    existing = {c.get("slice_name"): c["id"] for c in client.list_charts()}

    chart_defs = [
        # ── Market Overview charts ──
        {
            "name": "Market Total Value",
            "viz_type": "echarts_timeseries_bar",
            "datasource_id": datasets["market_summary"],
            "params": {
                "metrics": [{"label": "total_value", "expressionType": "SQL", "sqlExpression": "SUM(total_value)"}],
                "granularity_sqla": "trade_date",
                "time_grain_sqla": "P1D",
                "viz_type": "echarts_timeseries_bar",
                "row_limit": 1000,
                "color_scheme": "supersetColors",
            },
        },
        {
            "name": "Advances vs Declines",
            "viz_type": "echarts_timeseries_line",
            "datasource_id": datasets["market_summary"],
            "params": {
                "metrics": [
                    {"label": "advances", "expressionType": "SQL", "sqlExpression": "SUM(advances)"},
                    {"label": "declines", "expressionType": "SQL", "sqlExpression": "SUM(declines)"},
                ],
                "granularity_sqla": "trade_date",
                "time_grain_sqla": "P1D",
                "viz_type": "echarts_timeseries_line",
                "row_limit": 1000,
            },
        },
        {
            "name": "Active Symbols",
            "viz_type": "big_number_total",
            "datasource_id": datasets["market_summary"],
            "params": {
                "metrics": [{"label": "symbols", "expressionType": "SQL", "sqlExpression": "MAX(symbols)"}],
                "viz_type": "big_number_total",
                "granularity_sqla": "trade_date",
            },
        },
        # ── Top Movers charts ──
        {
            "name": "Top Gainers",
            "viz_type": "table",
            "datasource_id": datasets["top_movers"],
            "params": {
                "metrics": [],
                "all_columns": ["symbol", "price", "pct_change", "volume", "value"],
                "viz_type": "table",
                "row_limit": 20,
                "order_by_cols": ['["pct_change", false]'],
                "adhoc_filters": [{
                    "clause": "WHERE",
                    "comparator": "0",
                    "expressionType": "SIMPLE",
                    "operator": ">",
                    "subject": "pct_change",
                }],
            },
        },
        {
            "name": "Top Losers",
            "viz_type": "table",
            "datasource_id": datasets["top_movers"],
            "params": {
                "metrics": [],
                "all_columns": ["symbol", "price", "pct_change", "volume", "value"],
                "viz_type": "table",
                "row_limit": 20,
                "order_by_cols": ['["pct_change", true]'],
                "adhoc_filters": [{
                    "clause": "WHERE",
                    "comparator": "0",
                    "expressionType": "SIMPLE",
                    "operator": "<",
                    "subject": "pct_change",
                }],
            },
        },
        # ── Trading Activity charts ──
        {
            "name": "Tick Volume by Hour",
            "viz_type": "echarts_timeseries_bar",
            "datasource_id": datasets["hourly_ticks"],
            "params": {
                "metrics": [{"label": "ticks", "expressionType": "SQL", "sqlExpression": "SUM(tick_count)"}],
                "granularity_sqla": "trade_date",
                "time_grain_sqla": "P1D",
                "groupby": ["hour"],
                "viz_type": "echarts_timeseries_bar",
                "row_limit": 5000,
            },
        },
        {
            "name": "Symbols Traded by Hour",
            "viz_type": "heatmap",
            "datasource_id": datasets["hourly_ticks"],
            "params": {
                "all_columns_x": "trade_date",
                "all_columns_y": "hour",
                "metric": {"label": "symbols", "expressionType": "SQL", "sqlExpression": "SUM(symbols)"},
                "viz_type": "heatmap",
                "row_limit": 5000,
            },
        },
    ]

    for cdef in chart_defs:
        name = cdef["name"]
        if name in existing:
            charts[name] = existing[name]
            print(f"  Chart exists: {name} (id={existing[name]})")
            continue

        resp = client.create_chart(
            slice_name=name,
            viz_type=cdef["viz_type"],
            datasource_id=cdef["datasource_id"],
            params=cdef["params"],
        )
        charts[name] = resp["id"]
        print(f"  Created chart: {name} (id={resp['id']})")

    return charts


def create_dashboards(client: SupersetClient, charts: dict[str, int]) -> None:
    """Create 3 dashboards and assign charts."""
    existing = {d.get("dashboard_title"): d["id"] for d in client.list_dashboards()}

    dashboard_defs = [
        {
            "title": "Market Overview",
            "slug": "market-overview",
            "charts": ["Market Total Value", "Advances vs Declines", "Active Symbols"],
        },
        {
            "title": "Top Movers",
            "slug": "top-movers",
            "charts": ["Top Gainers", "Top Losers"],
        },
        {
            "title": "Trading Activity",
            "slug": "trading-activity",
            "charts": ["Tick Volume by Hour", "Symbols Traded by Hour"],
        },
    ]

    for ddef in dashboard_defs:
        title = ddef["title"]
        if title in existing:
            dash_id = existing[title]
            print(f"  Dashboard exists: {title} (id={dash_id})")
        else:
            resp = client.create_dashboard(title, ddef["slug"])
            dash_id = resp["id"]
            print(f"  Created dashboard: {title} (id={dash_id})")

        # Build layout with charts
        chart_ids = [charts[c] for c in ddef["charts"] if c in charts]
        if not chart_ids:
            continue

        position = _build_position(chart_ids)
        client.update_dashboard(dash_id, {"position_json": json.dumps(position)})
        print(f"    Added {len(chart_ids)} charts to {title}")


def _build_position(chart_ids: list[int]) -> dict:
    """Build a simple grid layout for dashboard."""
    position: dict = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
        "GRID_ID": {
            "children": [],
            "id": "GRID_ID",
            "parents": ["ROOT_ID"],
            "type": "GRID",
        },
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": ""}},
    }

    row_children = []
    # 2 charts per row
    for i in range(0, len(chart_ids), 2):
        row_key = f"ROW-{i}"
        row_charts = []
        for j, cid in enumerate(chart_ids[i : i + 2]):
            chart_key = f"CHART-{cid}"
            width = 12 if len(chart_ids[i : i + 2]) == 1 else 6
            position[chart_key] = {
                "children": [],
                "id": chart_key,
                "meta": {"chartId": cid, "height": 50, "sliceName": "", "width": width},
                "parents": ["ROOT_ID", "GRID_ID", row_key],
                "type": "CHART",
            }
            row_charts.append(chart_key)

        position[row_key] = {
            "children": row_charts,
            "id": row_key,
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "parents": ["ROOT_ID", "GRID_ID"],
            "type": "ROW",
        }
        row_children.append(row_key)

    position["GRID_ID"]["children"] = row_children
    return position


def main() -> None:
    print("=== Seeding Superset Dashboards ===\n")

    client = get_client()

    # Find PG Gold
    db_id = find_pg_gold_db(client)
    if db_id is None:
        print("ERROR: PG Gold database not found in Superset. Run install first.")
        sys.exit(1)
    print(f"PG Gold database ID: {db_id}\n")

    print("Creating datasets...")
    datasets = create_datasets(client, db_id)

    print("\nCreating charts...")
    charts = create_charts(client, datasets)

    print("\nCreating dashboards...")
    create_dashboards(client, charts)

    print("\n=== Done! ===")
    url = os.environ["SUPERSET_URL"]
    print(f"  Market Overview:   {url}/superset/dashboard/market-overview/")
    print(f"  Top Movers:        {url}/superset/dashboard/top-movers/")
    print(f"  Trading Activity:  {url}/superset/dashboard/trading-activity/")


if __name__ == "__main__":
    main()
