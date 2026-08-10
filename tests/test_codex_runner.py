import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from mybot_ui.codex_runner import CodexCliRunner, CodexRuntimeConfig, CodexThreadStore
from mybot_ui.extension_abilities import ExtensionAbilityStore


class CodexRunnerTests(unittest.TestCase):
    def test_thread_store_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CodexThreadStore(Path(directory) / "threads.json")
            store.set("测试会话", "thread-1")
            self.assertEqual("thread-1", store.get("测试会话"))
            store.clear("测试会话")
            self.assertEqual("", store.get("测试会话"))

    def test_commands_use_persistent_initial_and_resume_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "codex.exe"
            proxy = root / "proxy.exe"
            exe.touch()
            proxy.touch()
            runner = CodexCliRunner(
                CodexRuntimeConfig(exe, proxy, root, "https://example.com", "key", "model"),
                ExtensionAbilityStore(root / "extensions"),
                CodexThreadStore(root / "threads.json"),
            )
            output = root / "last.txt"
            initial = runner._command("http://127.0.0.1:1/v1", output, root, previous_thread="", ephemeral=False)
            resumed = runner._command("http://127.0.0.1:1/v1", output, root, previous_thread="abc", ephemeral=False)

            self.assertIn('default_permissions="mybot_workspace"', initial)
            self.assertIn('windows.sandbox="elevated"', initial)
            self.assertIn("-C", initial)
            self.assertEqual("resume", resumed[resumed.index("exec") + 1])
            self.assertIn("abc", resumed)
            environment = runner._environment(context_path=root / "task.json", task_token="token")
            self.assertEqual(str(root / "task.json"), environment["MYBOT_TASK_CONTEXT"])
            self.assertEqual("token", environment["MYBOT_TASK_TOKEN"])
            self.assertIn(str(root), environment["PYTHONPATH"])
            self.assertTrue(any("register_output_file" in value for value in initial))

    def test_task_outputs_are_limited_to_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task_root = root / "task"
            output_dir = task_root / "outputs"
            output_dir.mkdir(parents=True)
            valid = output_dir / "result.txt"
            valid.write_text("done", encoding="utf-8")
            outside = task_root / "outside.txt"
            outside.write_text("no", encoding="utf-8")
            (task_root / "outputs.json").write_text(json.dumps([
                {"path": str(valid)},
                {"path": str(outside)},
            ]), encoding="utf-8")
            self.assertEqual((str(valid.resolve()),), CodexCliRunner._task_output_files(task_root))

    def test_thread_id_is_read_from_json_events(self):
        stdout = '\n'.join((json.dumps({"type": "turn.started"}), json.dumps({"type": "thread.started", "thread_id": "t-1"})))
        self.assertEqual("t-1", CodexCliRunner._thread_id(stdout))

    def test_timeout_stage_reports_pending_mcp_tool(self):
        stdout = '\n'.join((
            json.dumps({"type": "item.started", "item": {"id": "1", "type": "mcp_tool_call", "server": "mybot", "tool": "get_capabilities"}}),
            json.dumps({"type": "item.started", "item": {"id": "2", "type": "mcp_tool_call", "server": "mybot", "tool": "get_task_context"}}),
            json.dumps({"type": "item.completed", "item": {"id": "2", "type": "mcp_tool_call"}}),
        ))
        error = subprocess.TimeoutExpired(["codex"], 30, output=stdout)
        self.assertEqual("MCP mybot.get_capabilities", CodexCliRunner._timeout_stage(error))


if __name__ == "__main__":
    unittest.main()
