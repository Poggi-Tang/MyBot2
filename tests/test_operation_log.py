import json
import tempfile
import unittest
from pathlib import Path

from mybot_ui.operation_log import OperationLog, summarize


class OperationLogTests(unittest.TestCase):
    def test_start_and_finish_share_id_and_include_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = OperationLog(directory)
            span = logger.start("gateway", "SendMessage", operation_id="request-1", details={"who": "芝士圆子"})
            logger.finish(span, success=True, result=True)

            path = next(Path(directory).glob("client-operations-*.jsonl"))
            entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(["started", "finished"], [entry["event"] for entry in entries])
        self.assertTrue(all(entry["operation_id"] == "request-1" for entry in entries))
        self.assertGreaterEqual(entries[1]["duration_ms"], 0)

    def test_large_encoded_payload_is_redacted(self):
        value = summarize({"upload": "A" * 5000})

        self.assertTrue(value["upload"]["redacted"])
        self.assertEqual(5000, value["upload"]["length"])
        self.assertNotIn("A" * 100, json.dumps(value))

    def test_data_url_is_redacted_even_under_generic_key(self):
        value = summarize({"url": "data:image/png;base64," + "A" * 200})

        self.assertTrue(value["url"]["redacted"])


if __name__ == "__main__":
    unittest.main()
