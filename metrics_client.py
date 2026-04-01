"""Prometheus/VictoriaMetrics HTTP client."""

from __future__ import annotations

import httpx
from typing import Any


class MetricsClient:
    """Client for Prometheus-compatible metrics APIs (VictoriaMetrics, Prometheus)."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def instant_query(self, query: str, time: str | None = None) -> dict[str, Any]:
        """Execute an instant PromQL query."""
        params: dict[str, str] = {"query": query}
        if time:
            params["time"] = time
        resp = await self._client.get("/api/v1/query", params=params)
        resp.raise_for_status()
        return resp.json()

    async def range_query(
        self, query: str, start: str, end: str, step: str
    ) -> dict[str, Any]:
        """Execute a range PromQL query."""
        params = {"query": query, "start": start, "end": end, "step": step}
        resp = await self._client.get("/api/v1/query_range", params=params)
        resp.raise_for_status()
        return resp.json()

    async def label_names(self) -> list[str]:
        """Get all label names."""
        resp = await self._client.get("/api/v1/labels")
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def label_values(self, label: str) -> list[str]:
        """Get values for a specific label."""
        resp = await self._client.get(f"/api/v1/label/{label}/values")
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def series(self, match: list[str], start: str, end: str) -> list[dict]:
        """Find series matching label selectors."""
        params: dict[str, Any] = {"match[]": match, "start": start, "end": end}
        resp = await self._client.get("/api/v1/series", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def metadata(self, metric: str | None = None) -> dict[str, Any]:
        """Get metric metadata."""
        params = {}
        if metric:
            params["metric"] = metric
        resp = await self._client.get("/api/v1/metadata", params=params)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()
