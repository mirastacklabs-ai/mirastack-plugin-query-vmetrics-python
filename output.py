"""Output enrichment helpers for the query_metrics plugin."""

from __future__ import annotations

import json
from typing import Any

MAX_RESULT_LEN = 32000


def enrich_metrics_output(action: str, result: Any) -> dict[str, str]:
    """Wrap raw metrics result with metadata for LLM consumption."""
    raw = result if isinstance(result, str) else json.dumps(result, default=str)

    output: dict[str, str] = {
        "action": action,
        "result": result if isinstance(result, str) else json.dumps(result, default=str),
    }

    if len(raw) > MAX_RESULT_LEN:
        output["result"] = raw[:MAX_RESULT_LEN]
        output["truncated"] = "true"

    # Extract result count from Prometheus API response structure.
    parsed = result if isinstance(result, dict) else _try_parse(raw)
    if parsed and isinstance(parsed, dict):
        if "data" in parsed:
            data = parsed["data"]
            if isinstance(data, dict) and "result" in data:
                rows = data["result"]
                if isinstance(rows, list):
                    output["result_count"] = str(len(rows))
            elif isinstance(data, list):
                output["result_count"] = str(len(data))
        if "status" in parsed:
            output["status"] = str(parsed["status"])

    return output


def _try_parse(raw: str) -> dict | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
