import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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

    def test_thread_store_rotates_by_task_context_and_legacy_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "threads.json"
            store = CodexThreadStore(path)
            store.set("任务限制", "thread-1", context_chars=2_000, now=100)
            store.set("任务限制", "thread-1", context_chars=2_000, resumed=True, now=101)
            self.assertEqual(
                ("", "task_limit"),
                store.select(
                    "任务限制",
                    incoming_context_chars=100,
                    max_tasks=2,
                    max_context_chars=12_000,
                    max_age_seconds=1_800,
                    now=102,
                ),
            )

            store.set("上下文限制", "thread-2", context_chars=11_500, now=100)
            self.assertEqual(
                ("", "context_limit"),
                store.select(
                    "上下文限制",
                    incoming_context_chars=501,
                    max_tasks=2,
                    max_context_chars=12_000,
                    max_age_seconds=1_800,
                    now=102,
                ),
            )

            path.write_text(json.dumps({"旧会话": "legacy-thread"}), encoding="utf-8")
            self.assertEqual(
                ("", "legacy_thread"),
                store.select(
                    "旧会话",
                    incoming_context_chars=100,
                    max_tasks=2,
                    max_context_chars=12_000,
                    max_age_seconds=1_800,
                    now=102,
                ),
            )

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
            self.assertEqual("1", environment["PYTHONUTF8"])
            self.assertEqual("utf-8", environment["PYTHONIOENCODING"])
            self.assertTrue(any("register_output_file" in value for value in initial))
            self.assertIn("mcp_servers.mybot.tool_timeout_sec=5", initial)
            self.assertIn('model_reasoning_effort="low"', initial)
            enabled_tools = next(value for value in initial if "enabled_tools=" in value)
            self.assertNotIn("get_task_context", enabled_tools)
            self.assertNotIn("get_capabilities", enabled_tools)
            self.assertTrue(any("PYTHONUTF8" in value for value in initial))

    def test_yolo_mode_bypasses_approvals_and_workspace_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "codex.exe"
            proxy = root / "proxy.exe"
            exe.touch()
            proxy.touch()
            runner = CodexCliRunner(
                CodexRuntimeConfig(
                    exe,
                    proxy,
                    root,
                    "https://example.com",
                    "key",
                    "model",
                    yolo_mode=True,
                ),
                ExtensionAbilityStore(root / "extensions"),
                CodexThreadStore(root / "threads.json"),
            )
            output = root / "last.txt"
            initial = runner._command(
                "http://127.0.0.1:1/v1", output, root, previous_thread="", ephemeral=False
            )
            resumed = runner._command(
                "http://127.0.0.1:1/v1", output, root, previous_thread="abc", ephemeral=False
            )

            for command in (initial, resumed):
                self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
                self.assertNotIn('default_permissions="mybot_workspace"', command)
                self.assertNotIn('approval_policy="never"', command)

    def test_restricted_mode_uses_task_workspace_and_skips_abilities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            abilities = Mock()
            thread_store = CodexThreadStore(root / "threads.json")
            thread_store.set("会话", "admin-thread")
            runner = CodexCliRunner(
                CodexRuntimeConfig(
                    root / "codex.exe",
                    root / "proxy.exe",
                    root,
                    "https://example.com",
                    "key",
                    "model",
                    restricted_workspace=True,
                ),
                abilities,
                thread_store,
            )

            self.assertTrue(runner.config.restricted_workspace)
            self.assertFalse(runner.config.yolo_mode)
            completed = subprocess.CompletedProcess(["codex"], 0, "", "")
            with patch.object(
                runner,
                "_execute",
                side_effect=(
                    (completed, "首次完成", "thread-1"),
                    (completed, "继续完成", "thread-1"),
                ),
            ) as execute:
                runner._run_locked("会话", "首次任务", "", "task-1", ())
                runner._run_locked("会话", "后续任务", "", "task-2", ())

            self.assertEqual(
                root / "data" / "codex" / "tasks" / "task-1",
                execute.call_args_list[0].kwargs["workspace"],
            )
            self.assertEqual(
                root / "data" / "codex" / "tasks" / "task-2",
                execute.call_args_list[1].kwargs["workspace"],
            )
            self.assertEqual("", execute.call_args_list[0].kwargs["previous_thread"])
            self.assertEqual("thread-1", execute.call_args_list[1].kwargs["previous_thread"])
            self.assertEqual("admin-thread", thread_store.get("会话"))
            self.assertEqual("thread-1", thread_store.get("restricted::会话"))
            abilities.matching.assert_not_called()

    def test_prompt_allows_explicitly_requested_github_writes(self):
        prompt = CodexCliRunner._initial_prompt(
            object(), "把项目推送到 GitHub", "", "", "成果输出目录：C:/task/outputs"
        )
        resumed = CodexCliRunner._resume_prompt(
            "把项目推送到 GitHub", "", "", "成果输出目录：C:/task/outputs"
        )

        for value in (prompt, resumed):
            self.assertIn("只有用户在当前任务中明确要求时", value)
            self.assertIn("git push", value)
            self.assertIn("gh CLI", value)
            self.assertNotIn("不提交或推送 Git", value)

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

    def test_task_outputs_scan_finds_chinese_file_without_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            task_root = Path(directory) / "task"
            output_dir = task_root / "outputs"
            output_dir.mkdir(parents=True)
            output = output_dir / "已添加打油诗.txt"
            output.write_text("完成", encoding="utf-8")
            self.assertEqual((str(output.resolve()),), CodexCliRunner._task_output_files(task_root))

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

    def test_prompts_forbid_substituting_historical_task_files(self):
        attachment_context = "成果输出目录：C:/task/outputs\n输入文件：[无]"
        initial = CodexCliRunner._initial_prompt(
            object(), "修改刚发的文档", "", "", attachment_context
        )
        resumed = CodexCliRunner._resume_prompt(
            "修改刚发的文档", "", "", attachment_context
        )

        for prompt in (initial, resumed):
            self.assertIn("没有拿到本次原文件", prompt)
            self.assertIn("data/codex/tasks", prompt)
            self.assertIn("其他会话或历史任务", prompt)


if __name__ == "__main__":
    unittest.main()
