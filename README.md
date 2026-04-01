# MIRASTACK Plugin: Query Metrics

Python plugin for querying **Prometheus/VictoriaMetrics** from MIRASTACK workflows. Part of the core observability plugin suite.

## Capabilities

| Action | Description |
|--------|-------------|
| `instant_query` | Execute PromQL instant query |
| `range_query` | Execute PromQL range query with start/end/step |
| `label_names` | List all label names |
| `label_values` | List values for a specific label |
| `series` | Find series matching selectors |
| `metadata` | Get metric metadata |

## Configuration

Configure the VictoriaMetrics URL via MIRASTACK settings:

```bash
miractl config set victoriametrics.url http://victoriametrics:8428
```

## Example Workflow Step

```yaml
- id: check-error-rate
  type: plugin
  plugin: query_metrics
  params:
    action: range_query
    query: "rate(http_requests_total{status=~'5..'}[5m])"
    start: "-1h"
    end: "now"
    step: "1m"
```

## Development

```bash
pip install -e .
python -m mirastack_plugin_query_metrics
```

## Requirements

- Python 3.12+
- httpx
- mirastack-sdk

## License

AGPL v3 — see [LICENSE](LICENSE).
