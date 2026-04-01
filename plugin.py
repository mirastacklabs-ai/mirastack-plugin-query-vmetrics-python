"""MIRASTACK query_metrics plugin — queries Prometheus/VictoriaMetrics."""

from __future__ import annotations

import asyncio
import json

from mirastack_sdk import (
    Plugin,
    PluginInfo,
    PluginSchema,
    SchemaParam,
    EngineContext,
    Permission,
    DevOpsStage,
    ExecutionRequest,
    ExecutionResponse,
    serve,
)
from metrics_client import MetricsClient


class QueryMetricsPlugin(Plugin):
    """Plugin for querying Prometheus-compatible metrics stores."""

    def __init__(self):
        self._client: MetricsClient | None = None

    def info(self) -> PluginInfo:
        return PluginInfo(
            name="query_metrics",
            version="0.1.0",
            description="Query Prometheus/VictoriaMetrics for metrics data",
            permission=Permission.READ,
            devops_stages=[DevOpsStage.OBSERVE],
        )

    def schema(self) -> PluginSchema:
        return PluginSchema(
            params=[
                SchemaParam(name="action", type="string", required=True,
                           description="One of: instant_query, range_query, label_names, label_values, series, metadata"),
                SchemaParam(name="query", type="string", required=False,
                           description="PromQL query expression"),
                SchemaParam(name="start", type="string", required=False,
                           description="Start time (RFC3339 or relative like -1h)"),
                SchemaParam(name="end", type="string", required=False,
                           description="End time (RFC3339 or relative like now)"),
                SchemaParam(name="step", type="string", required=False,
                           description="Query step (e.g., 15s, 1m)"),
                SchemaParam(name="label", type="string", required=False,
                           description="Label name for label_values action"),
                SchemaParam(name="match", type="string", required=False,
                           description="Series selector for series action"),
                SchemaParam(name="metric", type="string", required=False,
                           description="Metric name for metadata action"),
            ],
        )

    async def execute(self, ctx: EngineContext, req: ExecutionRequest) -> ExecutionResponse:
        if self._client is None:
            config = await ctx.get_config()
            base_url = config.get("metrics_url", "http://localhost:8428")
            self._client = MetricsClient(base_url)

        action = req.params.get("action", "")
        try:
            result = await self._dispatch(action, req.params)
            return ExecutionResponse(
                output={"result": json.dumps(result, default=str)},
            )
        except Exception as e:
            return ExecutionResponse(
                output={"error": str(e)},
                error=str(e),
            )

    async def _dispatch(self, action: str, params: dict) -> dict | list:
        match action:
            case "instant_query":
                return await self._client.instant_query(
                    params["query"], params.get("time")
                )
            case "range_query":
                return await self._client.range_query(
                    params["query"], params["start"], params["end"], params["step"]
                )
            case "label_names":
                return await self._client.label_names()
            case "label_values":
                return await self._client.label_values(params["label"])
            case "series":
                match_selectors = [m.strip() for m in params.get("match", "").split(",")]
                return await self._client.series(
                    match_selectors, params["start"], params["end"]
                )
            case "metadata":
                return await self._client.metadata(params.get("metric"))
            case _:
                raise ValueError(f"Unknown action: {action}")

    async def health_check(self) -> bool:
        if self._client is None:
            return False
        try:
            await self._client.label_names()
            return True
        except Exception:
            return False

    async def config_updated(self, config: dict):
        if "metrics_url" in config:
            if self._client:
                await self._client.close()
            self._client = MetricsClient(config["metrics_url"])


def main():
    plugin = QueryMetricsPlugin()
    asyncio.run(serve(plugin))


if __name__ == "__main__":
    main()
