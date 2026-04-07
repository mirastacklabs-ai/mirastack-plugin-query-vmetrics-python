"""MIRASTACK query_metrics plugin — queries Prometheus/VictoriaMetrics."""

from __future__ import annotations

import json
import os

from mirastack_sdk import (
    Action,
    ConfigParam,
    IntentPattern,
    Plugin,
    PluginInfo,
    PluginSchema,
    ParamSchema,
    Permission,
    PromptTemplate,
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
from output import enrich_metrics_output


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
            version="0.2.0",
            description=(
                "Query VictoriaMetrics for metrics data using MetricsQL (Prometheus-compatible). "
                "Use this plugin when you need current or historical metric values, label discovery, "
                "series matching, or metric metadata. Start with instant_query for spot checks, "
                "range_query for trend analysis, and label_values/series for exploration."
            ),
            permissions=[Permission.READ],
            devops_stages=[DevOpsStage.OBSERVE],
            intents=[
                IntentPattern(pattern="query metrics", description="Query Prometheus/VictoriaMetrics metrics", priority=10),
                IntentPattern(pattern="check metric", description="Check specific metric values", priority=8),
                IntentPattern(pattern="promql", description="Execute a PromQL expression", priority=7),
                IntentPattern(pattern="metricsql", description="Execute a MetricsQL expression", priority=7),
                IntentPattern(pattern="cpu usage", description="Check CPU utilisation metrics", priority=6),
                IntentPattern(pattern="memory usage", description="Check memory utilisation metrics", priority=6),
                IntentPattern(pattern="error rate", description="Check request error rates", priority=6),
                IntentPattern(pattern="request latency", description="Check request latency percentiles", priority=6),
            ],
            actions=[
                Action(
                    id="instant_query",
                    description=(
                        "Execute an instant PromQL/MetricsQL query at a single point in time. "
                        "Use this to check the current value of a metric or evaluate a PromQL expression "
                        "at a specific timestamp. Returns vector or scalar results."
                    ),
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    intents=[
                        IntentPattern(pattern="run promql", description="Execute a PromQL instant query", priority=10),
                        IntentPattern(pattern="instant metric value", description="Get the current value of a metric", priority=9),
                        IntentPattern(pattern="current value of", description="Check what a metric reads right now", priority=8),
                        IntentPattern(pattern="evaluate expression", description="Evaluate a MetricsQL expression", priority=7),
                    ],
                    input_params=[
                        ParamSchema(name="query", type="string", required=True, description="PromQL/MetricsQL query expression (e.g. 'up{job=\"node\"}' or 'rate(http_requests_total[5m])')"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Query result in Prometheus API response format")],
                ),
                Action(
                    id="range_query",
                    description=(
                        "Execute a range PromQL/MetricsQL query over a time window. "
                        "Use this for trend analysis, anomaly detection, or viewing metric behaviour "
                        "over a period. The engine provides start/end times from user context."
                    ),
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    intents=[
                        IntentPattern(pattern="metrics over time", description="View metric trend over a time range", priority=10),
                        IntentPattern(pattern="range query", description="Execute a range PromQL query", priority=9),
                        IntentPattern(pattern="metric trend", description="Analyze metric behaviour over time", priority=8),
                        IntentPattern(pattern="time series for", description="Get time series data for a metric", priority=7),
                    ],
                    input_params=[
                        ParamSchema(name="query", type="string", required=True, description="PromQL/MetricsQL query expression"),
                        ParamSchema(name="start", type="string", required=False, description="Start time"),
                        ParamSchema(name="end", type="string", required=False, description="End time"),
                        ParamSchema(name="step", type="string", required=False, description="Query resolution step (e.g., 15s, 1m, 5m). Defaults to 1m."),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Query result in Prometheus API response format")],
                ),
                Action(
                    id="label_names",
                    description=(
                        "List all label names available in VictoriaMetrics. "
                        "Use this to discover what dimensions are available for filtering. "
                        "Optionally scope with match[] selectors to narrow results."
                    ),
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    intents=[
                        IntentPattern(pattern="list label names", description="Get all available metric label names", priority=9),
                        IntentPattern(pattern="what labels exist", description="Discover available metric dimensions", priority=8),
                        IntentPattern(pattern="available dimensions", description="List filterable label dimensions", priority=7),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Array of label names")],
                ),
                Action(
                    id="label_values",
                    description=(
                        "List all values for a specific label across the metric store. "
                        "Use this to find which services, namespaces, or other dimension values exist. "
                        "Essential before building filtered queries."
                    ),
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    intents=[
                        IntentPattern(pattern="label values", description="List values for a metric label", priority=9),
                        IntentPattern(pattern="which services", description="Find service names from metrics", priority=8),
                        IntentPattern(pattern="values of label", description="Enumerate values for a dimension", priority=7),
                    ],
                    input_params=[
                        ParamSchema(name="label", type="string", required=True, description="Label name to get values for (e.g. 'job', 'namespace', 'instance')"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Array of label values")],
                ),
                Action(
                    id="series",
                    description=(
                        "Find time series matching label selectors. "
                        "Returns the full label set for each matching series. Use this to explore "
                        "what is being collected for a job, service, or metric name."
                    ),
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    intents=[
                        IntentPattern(pattern="find series", description="Find time series matching selectors", priority=9),
                        IntentPattern(pattern="matching series", description="List series that match a selector", priority=8),
                        IntentPattern(pattern="what series exist for", description="Discover series for a metric or job", priority=7),
                    ],
                    input_params=[
                        ParamSchema(name="match", type="string", required=True, description="Series selector(s) (comma-separated, e.g. '{job=\"node\"}')"),
                        ParamSchema(name="start", type="string", required=False, description="Start time"),
                        ParamSchema(name="end", type="string", required=False, description="End time"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Array of matching series with label sets")],
                ),
                Action(
                    id="metadata",
                    description=(
                        "Get metric metadata including type, help text, and unit. "
                        "Use this to understand what a metric measures before querying it. "
                        "Returns HELP, TYPE, and UNIT annotations from metric exposition."
                    ),
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    intents=[
                        IntentPattern(pattern="metric metadata", description="Get metric type and help text", priority=9),
                        IntentPattern(pattern="what does metric measure", description="Understand a metric's purpose", priority=8),
                        IntentPattern(pattern="describe metric", description="Describe a metric name", priority=7),
                    ],
                    input_params=[
                        ParamSchema(name="metric", type="string", required=False, description="Metric name for metadata lookup (e.g. 'node_cpu_seconds_total')"),
                    ],
                    output_params=[ParamSchema(name="result", type="json", required=True, description="Metric metadata (type, help, unit)")],
                ),
            ],
            prompt_templates=[
                PromptTemplate(
                    name="query_metrics_guide",
                    description="Best practices for using VictoriaMetrics metrics query tools",
                    content=(
                        "You have access to VictoriaMetrics metrics tools. Follow these guidelines:\n\n"
                        "1. DISCOVERY FIRST: Before querying, use label_values(\"job\") or label_names() to find available targets.\n"
                        "2. INSTANT vs RANGE: Use instant_query for current state checks. Use range_query for trend analysis.\n"
                        "3. SCOPING: Always scope queries with label matchers like {job=\"X\", namespace=\"Y\"} to reduce cardinality.\n"
                        "4. RATES: For counters, always wrap with rate() or increase(). Raw counter values are rarely useful.\n"
                        "5. STEP SIZE: For range_query, choose step relative to the time window (e.g., 1m for <1h, 5m for <6h, 15m for <24h).\n"
                        "6. METADATA: Use metadata action to understand metric types (counter, gauge, histogram, summary) before querying.\n"
                        "7. SERIES EXPLORATION: Use series action to check what label combinations exist before building complex queries.\n"
                        "8. COMMON PATTERNS:\n"
                        "   - CPU: rate(node_cpu_seconds_total{mode!=\"idle\"}[5m])\n"
                        "   - Memory: node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes\n"
                        "   - Error rate: rate(http_requests_total{code=~\"5..\"}[5m]) / rate(http_requests_total[5m])\n"
                        "   - Latency: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))"
                    ),
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
            enriched = enrich_metrics_output(action, result)
            resp = respond_map(enriched)
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
