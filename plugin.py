"""MIRASTACK query_metrics plugin — queries Prometheus/VictoriaMetrics."""

from __future__ import annotations

import json
import os

from mirastack_sdk import (
    Action,
    ConfigParam,
    Plugin,
    PluginInfo,
    PluginSchema,
    ParamSchema,
    Permission,
    DevOpsStage,
    ExecuteRequest,
    ExecuteResponse,
    respond_map,
    respond_error,
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
            actions=[
                Action(
                    id="instant_query",
                    description="Execute an instant PromQL query at a single point in time",
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    input_params=[
                        ParamSchema(name="query", type="string", required=True, description="PromQL query expression"),
                        ParamSchema(name="time", type="string", required=False, description="Evaluation time (default: now)"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Instant query result")],
                ),
                Action(
                    id="range_query",
                    description="Execute a PromQL range query over a time window",
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    input_params=[
                        ParamSchema(name="query", type="string", required=True, description="PromQL query expression"),
                        ParamSchema(name="start", type="string", required=False, description="Start time"),
                        ParamSchema(name="end", type="string", required=False, description="End time"),
                        ParamSchema(name="step", type="string", required=True, description="Query step (e.g., 15s, 1m)"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Range query result")],
                ),
                Action(
                    id="label_names",
                    description="List all label names in the metrics store",
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Label names")],
                ),
                Action(
                    id="label_values",
                    description="List values for a specific label",
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    input_params=[
                        ParamSchema(name="label", type="string", required=True, description="Label name"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Label values")],
                ),
                Action(
                    id="series",
                    description="Find time series matching selectors",
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    input_params=[
                        ParamSchema(name="match", type="string", required=True, description="Series selector (comma-separated)"),
                        ParamSchema(name="start", type="string", required=False, description="Start time"),
                        ParamSchema(name="end", type="string", required=False, description="End time"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Matching series")],
                ),
                Action(
                    id="metadata",
                    description="Get metric metadata (type, help, unit)",
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    input_params=[
                        ParamSchema(name="metric", type="string", required=False, description="Metric name (omit for all)"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Metric metadata")],
                ),
            ],
            config_params=[
                ConfigParam(key="metrics_url", type="string", required=True, description="VictoriaMetrics base URL (e.g. http://victoriametrics:8428)"),
            ],
        )

    def schema(self) -> PluginSchema:
        info = self.info()
        return PluginSchema(actions=info.actions)

    async def execute(self, req: ExecuteRequest) -> ExecuteResponse:
        if self._client is None:
            resp = respond_error("metrics_url not configured — set MIRASTACK_METRICS_URL or push config via engine")
            resp.logs = ["ERROR: no metrics client configured"]
            return resp

        action = req.action_id or req.params.get("action", "")
        try:
            result = await self._dispatch(action, req.params, req.time_range)
            resp = respond_map({"result": result})
            return resp
        except Exception as e:
            resp = respond_error(str(e))
            resp.logs = [f"ERROR: {e}"]
            return resp

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
