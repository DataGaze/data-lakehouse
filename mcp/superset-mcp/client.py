"""Superset REST API client."""

from __future__ import annotations

import httpx


class SupersetClient:
    """Thin wrapper around Superset REST API v1."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token: str | None = None
        self._csrf: str | None = None
        self._client = httpx.Client(timeout=60, follow_redirects=True)

    # ── Auth ──────────────────────────────────────────────────────

    def _login(self) -> None:
        resp = self._client.post(
            f"{self.base_url}/api/v1/security/login",
            json={
                "username": self._username,
                "password": self._password,
                "provider": "db",
            },
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

    def _get_csrf(self) -> str:
        resp = self._client.get(
            f"{self.base_url}/api/v1/security/csrf_token/",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        self._csrf = resp.json()["result"]
        return self._csrf

    def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            self._login()
        return {"Authorization": f"Bearer {self._token}"}

    def _write_headers(self) -> dict[str, str]:
        h = self._auth_headers()
        h["Content-Type"] = "application/json"
        h["X-CSRFToken"] = self._get_csrf()
        h["Referer"] = self.base_url
        return h

    # ── Generic request ───────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._client.get(
            f"{self.base_url}{path}",
            headers=self._auth_headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        resp = self._client.post(
            f"{self.base_url}{path}",
            headers=self._write_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, payload: dict) -> dict:
        resp = self._client.put(
            f"{self.base_url}{path}",
            headers=self._write_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> dict:
        resp = self._client.delete(
            f"{self.base_url}{path}",
            headers=self._write_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Databases ─────────────────────────────────────────────────

    def list_databases(self) -> list[dict]:
        return self._get("/api/v1/database/")["result"]

    def get_database(self, db_id: int) -> dict:
        return self._get(f"/api/v1/database/{db_id}")["result"]

    # ── Datasets ──────────────────────────────────────────────────

    def list_datasets(self, page_size: int = 100) -> list[dict]:
        return self._get("/api/v1/dataset/", {"q": f"(page_size:{page_size})"})["result"]

    def create_dataset(
        self, database_id: int, table_name: str, schema: str = "public"
    ) -> dict:
        return self._post(
            "/api/v1/dataset/",
            {
                "database": database_id,
                "table_name": table_name,
                "schema": schema,
            },
        )

    def create_virtual_dataset(
        self, database_id: int, name: str, sql: str, schema: str = "public"
    ) -> dict:
        return self._post(
            "/api/v1/dataset/",
            {
                "database": database_id,
                "table_name": name,
                "schema": schema,
                "sql": sql,
            },
        )

    # ── Charts ────────────────────────────────────────────────────

    def list_charts(self, page_size: int = 100) -> list[dict]:
        return self._get("/api/v1/chart/", {"q": f"(page_size:{page_size})"})["result"]

    def create_chart(
        self,
        slice_name: str,
        viz_type: str,
        datasource_id: int,
        params: dict,
        datasource_type: str = "table",
    ) -> dict:
        import json

        return self._post(
            "/api/v1/chart/",
            {
                "slice_name": slice_name,
                "viz_type": viz_type,
                "datasource_id": datasource_id,
                "datasource_type": datasource_type,
                "params": json.dumps(params),
            },
        )

    def get_chart(self, chart_id: int) -> dict:
        return self._get(f"/api/v1/chart/{chart_id}")["result"]

    # ── Dashboards ────────────────────────────────────────────────

    def list_dashboards(self, page_size: int = 100) -> list[dict]:
        return self._get(
            "/api/v1/dashboard/", {"q": f"(page_size:{page_size})"}
        )["result"]

    def create_dashboard(
        self,
        dashboard_title: str,
        slug: str | None = None,
        published: bool = True,
    ) -> dict:
        payload: dict = {
            "dashboard_title": dashboard_title,
            "published": published,
        }
        if slug:
            payload["slug"] = slug
        return self._post("/api/v1/dashboard/", payload)

    def update_dashboard(self, dashboard_id: int, payload: dict) -> dict:
        return self._put(f"/api/v1/dashboard/{dashboard_id}", payload)

    def get_dashboard(self, dashboard_id: int) -> dict:
        return self._get(f"/api/v1/dashboard/{dashboard_id}")["result"]

    # ── SQL Lab ───────────────────────────────────────────────────

    def run_sql(
        self, database_id: int, sql: str, schema: str = "public", limit: int = 1000
    ) -> dict:
        return self._post(
            "/api/v1/sqllab/execute/",
            {
                "database_id": database_id,
                "sql": sql,
                "schema": schema,
                "runAsync": False,
                "queryLimit": limit,
            },
        )
