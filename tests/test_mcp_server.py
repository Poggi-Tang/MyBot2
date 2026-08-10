import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mybot_mcp.server import handle_request
from mybot_ui.operation_log import OperationLog


class McpServerTests(unittest.TestCase):
    def test_initialize_and_tool_list(self):
        initialized = handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        })
        self.assertEqual("mybot-wechat", initialized["result"]["serverInfo"]["name"])
        listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(
            {"get_capabilities", "get_task_context", "report_progress", "register_output_file"},
            {item["name"] for item in listed["result"]["tools"]},
        )
        capabilities = handle_request({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_capabilities", "arguments": {}},
        })
        self.assertNotIn("error", capabilities)
        text = capabilities["result"]["content"][0]["text"]
        parsed = json.loads(text)
        self.assertGreater(parsed["sdk_function_count"], 0)
        self.assertEqual("mybot_ui/catalog.py", parsed["sdk_details_source"])
        self.assertLess(len(text.encode("utf-8")), 4_000)

    def test_task_context_requires_process_binding(self):
        response = handle_request({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_task_context", "arguments": {}},
        })
        self.assertIn("error", response)

    def test_task_context_never_exposes_internal_token(self):
        from mybot_mcp import server

        control_root = server.PROJECT_ROOT / "data" / "codex" / "tmp"
        control_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".json", dir=control_root, encoding="utf-8", delete=False) as stream:
            path = Path(stream.name)
            json.dump({"task_id": "task-1", "conversation": "chat", "task_token": "internal-secret"}, stream)
        try:
            with patch.dict(os.environ, {
                "MYBOT_TASK_CONTEXT": str(path),
                "MYBOT_TASK_TOKEN": "internal-secret",
            }, clear=False):
                response = handle_request({
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "get_task_context", "arguments": {}},
                })
            text = response["result"]["content"][0]["text"]
            self.assertEqual("task-1", json.loads(text)["task_id"])
            self.assertNotIn("internal-secret", text)
            self.assertNotIn("task_token", text)
        finally:
            path.unlink(missing_ok=True)

    def test_tool_call_writes_timing_log(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("mybot_mcp.server.operations", OperationLog(directory)):
                response = handle_request({
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "get_capabilities", "arguments": {}},
                })
            self.assertNotIn("error", response)
            entries = [
                json.loads(line)
                for path in Path(directory).glob("*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(["started", "finished"], [entry["event"] for entry in entries])
            self.assertTrue(entries[-1]["success"])
            self.assertIn("duration_ms", entries[-1])

    def test_register_output_file_rejects_outside_path_and_writes_manifest(self):
        from mybot_mcp import server

        task_id = "test-output-registration"
        task_root = server.PROJECT_ROOT / "data" / "codex" / "tasks" / task_id
        output_dir = task_root / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "result.txt"
        output.write_text("done", encoding="utf-8")
        control_root = server.PROJECT_ROOT / "data" / "codex" / "tmp"
        control_root.mkdir(parents=True, exist_ok=True)
        context_path = control_root / f"task-{task_id}.json"
        token = "test-token"
        context_path.write_text(json.dumps({
            "task_id": task_id,
            "conversation": "测试会话",
            "output_dir": str(output_dir.resolve()),
            "task_token": token,
        }), encoding="utf-8")
        try:
            with patch.dict(os.environ, {
                "MYBOT_TASK_CONTEXT": str(context_path),
                "MYBOT_TASK_TOKEN": token,
            }, clear=False):
                accepted = handle_request({
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {"name": "register_output_file", "arguments": {"path": str(output)}},
                })
                rejected = handle_request({
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {"name": "register_output_file", "arguments": {"path": str(context_path)}},
                })
            self.assertNotIn("error", accepted)
            self.assertIn("error", rejected)
            manifest = json.loads((task_root / "outputs.json").read_text(encoding="utf-8"))
            self.assertEqual("result.txt", manifest[0]["name"])
        finally:
            context_path.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            (task_root / "outputs.json").unlink(missing_ok=True)
            output_dir.rmdir()
            task_root.rmdir()


if __name__ == "__main__":
    unittest.main()
