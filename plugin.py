"""MIRASTACK query_metrics plugin — queries Prometheus/VictoriaMetrics."""

from __future__ import annotations

import json
import os

from mirastack_sdk import (
    ConfigParam,
    Plugin,
    PluginInfo,
    PluginSchema,
    ParamSchema,
    Permission,
    DevOpsStage,
    ExecuteRequest,
    ExecuteResponse,
    serve,
)
from mirastack_sdk.datetimeutils import format_epoch_seconds
from mirastack_sdk.plugin import TimeRange
from metrics_client import MetricsClient


class QueryMetricsPlugin(Plugin):
    """Plugin for querying Prometheus-compatible metrics stores."""

    def __init__(self):
        self._client: MetricsClient | None = None
        # Bootstrap from env var; engine pushes runtime config via config_updated()
        url = os.environ.get("MIRASTACK_METRICS_URL", "")
        if url:
            self._client = MetricsClient(url)

    def info(self) -> PluginInfo:
        return PluginInfo(
            name="query_metrics",
            version="0.1.0",
            description="Query Prometheus/VictoriaMetrics for metrics data",
            permissions=[Permission.READ],
            devops_stages=[DevOpsStage.OBSERVE],
            config_params=[
                ConfigParam(key="metrics_url", type="string", required=True, description="VictoriaMetrics base URL (e.g. http://victoriametrics:8428)"),
            ],
        )

    def schema(self) -> PluginSchema:
        return PluginSchema(
            input_params=[
                ParamSchema(name="action", type="string", required=True,
                            description="One of: instant_query, range_query, label_names, label_values, series, metadata"),
                ParamSchema(name="query", type="string", required=False,
                            description="PromQL query expression"),
                ParamSchema(name="start", type="string", required=False,
                            description="Start time (RFC3339 or relative like -1h)"),
                ParamSchema(name="end", type="string", required=False,
                            description="End time (RFC3339 or relative like now)"),
                ParamSchema(name="step", type="string", required=False,
                            description="Query step (e.g., 15s, 1m)"),
                ParamSchema(name="label", type="string", required=False,
                            description="Label name for label_values action"),
                ParamSchema(name="match", type="string", required=False,
                            description="Series selector for series action"),
                ParamSchema(name="metric", type="string", required=False,
                            description="Metric name for metadata action"),
            ],
            output_params=[
                ParamSchema(name="result", type="json", required=True,
                            description="Query result as JSON"),
            ],
        )

    async def execute(self, req: ExecuteRequest) -> ExecuteResponse:
        if self._client is None:
            return ExecuteResponse(
                output={"error": "metrics_url not configured — set MIRASTACK_METRICS_URL or push config via engine"},
                logs=["ERROR: no metrics client configured"],
            )

        action = req.params.get("action", "")
        try:
            result = await self._dispatch(action, req.params, req.time_range)
            return ExecuteResponse(
                output={"result": json.dumps(result, default=str)},
            )
        except Exception as e:
            return ExecuteResponse(
                output={"error": str(e)},
                logs=[f"ERROR: {e}"],
            )

    async def _dispatch(self, action: str, params: dict, tr: TimeRange | None = None) -> dict | list:
        match action:
            case "instant_query":
                eval_time = params.get("time")
                if tr and tr.end_epoch_ms > 0:
                    eval_time = format_epoch_seconds(tr.end_epoch_ms)
                return await self._client.instant_query(
                    params["query"], eval_time
                )
            case "range_query":
                if tr and tr.start_epoch_ms > 0:
                    start = format_epoch_seconds(tr.start_epoch_ms)
                    end = format_epoch_seconds(tr.end_epoch_ms)
                else:
                    start = params["start"]
                    end = params["end"]
                return await self._client.range_query(
                    params["query"], start, end, params["step"]
                )
            case "label_names":
                return await self._client.label_names()
            case "label_values":
                return await self._client.label_values(params["label"])
            case "series":
                match_selectors = [m.strip() for m in params.get("match", "").split(",")]
                if tr and tr.start_epoch_ms > 0:
                    start = format_epoch_seconds(tr.start_epoch_ms)
                    end = format_epoch_seconds(tr.end_epoch_ms)
                else:
                    start = params["start"]
                    end = params["end"]
                return await self._client.series(
                    match_selectors, start, end
                )
            case "metadata":
                return await self._client.metadata(params.get("metric"))
            case _:
                raise ValueError(f"Unknown action: {action}")

    async def health_check(self) -> None:
        # Pull config from engine (cached 15s in SDK)
        ec = getattr(self, "_engine_context", None)
        if ec is not None:
            try:
                config = await ec.get_config()
                await self._apply_config(config)
            except Exception:
                pass
        if self._client is None:
            raise RuntimeError("metrics_url not configured")
        await self._client.label_names()

    async def config_updated(self, config: dict[str, str]) -> None:
        await self._apply_config(config)

    async def _apply_config(self, config: dict[str, str]) -> None:
        if "metrics_url" in config:
            if self._client:
                await self._client.close()
            self._client = MetricsClient(config["metrics_url"])


def main():
    plugin = QueryMetricsPlugin()
    serve(plugin)


if __name__ == "__main__":
    main()
