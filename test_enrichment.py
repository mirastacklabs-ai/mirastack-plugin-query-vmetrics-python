"""Tests for query_vmetrics_python output enrichment."""

import json
import unittest

from output import MAX_RESULT_LEN, enrich_metrics_output


class TestEnrichMetricsOutput(unittest.TestCase):
    """Verify output enrichment function."""

    def test_basic_fields(self):
        out = enrich_metrics_output("instant_query", '{"status":"success"}')
        self.assertEqual(out["action"], "instant_query")
        self.assertEqual(out["status"], "success")

    def test_result_count_from_vector(self):
        raw = json.dumps({
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1, "1"]}]},
        })
        out = enrich_metrics_output("instant_query", raw)
        self.assertEqual(out["result_count"], "1")

    def test_result_count_from_array(self):
        raw = json.dumps({"status": "success", "data": ["__name__", "job"]})
        out = enrich_metrics_output("label_names", raw)
        self.assertEqual(out["result_count"], "2")

    def test_truncation(self):
        long = "x" * (MAX_RESULT_LEN + 5000)
        out = enrich_metrics_output("range_query", long)
        self.assertEqual(out["truncated"], "true")
        self.assertEqual(len(out["result"]), MAX_RESULT_LEN)

    def test_invalid_json_passes_through(self):
        out = enrich_metrics_output("metadata", "not-json")
        self.assertEqual(out["action"], "metadata")
        self.assertEqual(out["result"], "not-json")
        self.assertNotIn("result_count", out)

    def test_dict_input(self):
        data = {"status": "success", "data": {"result": [1, 2, 3]}}
        out = enrich_metrics_output("instant_query", data)
        self.assertEqual(out["result_count"], "3")


if __name__ == "__main__":
    unittest.main()
