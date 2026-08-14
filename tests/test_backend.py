import subprocess
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from mybot_ui.api import GatewayResult
from mybot_ui.backend import (
    ApplicationBackend,
    ApplicationServices,
    ExtensionManagement,
    ExtensionOperationError,
    GatewayWeChatAutomation,
    ModelOperations,
    WeChatCommand,
    WindowsServerLifecycle,
)


class BackendDispatchTests(unittest.TestCase):
    def test_application_backend_dispatches_typed_wechat_command(self):
        calls = []
        completed = Future()
        completed.set_result(GatewayResult(True, True))
        wechat = SimpleNamespace(
            dispatch=lambda command: calls.append(command) or completed,
            close=lambda: None,
        )
        backend = ApplicationBackend(wechat=wechat, server=MagicMock(), models=MagicMock())

        result = backend.dispatch_wechat(
            "圆子",
            "SendMessage",
            {"who": "芝士圆子", "message": "hello"},
            timeout_seconds=12,
        ).result()

        self.assertTrue(result.ok)
        self.assertEqual(1, len(calls))
        self.assertEqual(
            WeChatCommand(
                "圆子",
                "SendMessage",
                {"who": "芝士圆子", "message": "hello"},
                12,
            ),
            calls[0],
        )

    def test_gateway_adapter_translates_command_to_gateway_call(self):
        completed = Future()
        gateway = SimpleNamespace(
            connected=True,
            clients=["圆子"],
            uri="ws://127.0.0.1:5177/ws",
            call=lambda *args, **kwargs: completed,
        )
        adapter = GatewayWeChatAutomation.__new__(GatewayWeChatAutomation)
        adapter._gateway = gateway

        returned = adapter.dispatch(WeChatCommand("圆子", "GetAllConversations", "", 7))

        self.assertIs(completed, returned)

    def test_model_service_delegates_provider_operations(self):
        client = MagicMock()
        client.generate_with_fallback.return_value = "ok"
        service = ModelOperations(client)
        primary = MagicMock()
        backup = MagicMock()
        messages = [{"role": "user", "content": "hello"}]

        self.assertEqual(
            "ok",
            service.generate_with_fallback(
                primary,
                backup,
                messages,
                timeout=25,
            ),
        )
        client.generate_with_fallback.assert_called_once_with(
            primary,
            backup,
            messages,
            timeout=25,
        )

    def test_application_services_resolve_project_paths_and_share_dependencies(self):
        with patch("mybot_ui.backend.ConversationMemory") as conversation_memory, patch(
            "mybot_ui.backend.PersonalMemoryStore"
        ) as personal_store, patch(
            "mybot_ui.backend.PersonalMemoryLearner"
        ) as learner, patch(
            "mybot_ui.backend.EpisodicMemoryStore"
        ) as episodic_store, patch(
            "mybot_ui.backend.DailyWorkspaceStore"
        ) as daily_store, patch(
            "mybot_ui.backend.ExtensionAbilityStore"
        ) as abilities, patch(
            "mybot_ui.backend.ExtensionRegistry"
        ) as extension_registry, patch(
            "mybot_ui.backend.CodexRuntimeManager"
        ) as codex_manager, patch(
            "mybot_ui.backend.CodexThreadStore"
        ) as codex_threads, patch(
            "mybot_ui.backend.ConversationAttachmentStore"
        ) as attachment_store, patch(
            "mybot_ui.backend.ImageUnderstandingCache"
        ) as image_cache, patch(
            "mybot_ui.backend.ReusableTaskReviewer"
        ) as reviewer, patch(
            "mybot_ui.backend.RealtimeToolExecutor"
        ) as realtime_tools, patch(
            "mybot_ui.backend.HiggsVoiceActor"
        ) as voice_actor, patch(
            "mybot_ui.backend.TaskExecutors.create"
        ) as executors:
            root = Path(r"F:\MyBot")
            models = MagicMock()
            services = ApplicationServices.create(
                project_root=root,
                settings={
                    "personal_memory": {
                        "path": "state/people.json",
                        "name_aliases": {" 小圆 ": "圆子"},
                        "ignored_names": ["系统"],
                    },
                    "attachments": {"wechat_file_roots": [r"D:\WeChat Files"]},
                },
                models=models,
                chat_concurrency=5,
            )

        personal_store.assert_called_once_with(
            root / "state" / "people.json",
            aliases={"小圆": "圆子"},
            ignored_names={"系统"},
        )
        learner.assert_called_once_with(models, personal_store.return_value)
        reviewer.assert_called_once_with(models)
        voice_actor.assert_called_once_with(models)
        executors.assert_called_once_with(chat_concurrency=5)
        self.assertIs(services.conversation_memory, conversation_memory.return_value)
        self.assertIs(services.abilities, abilities.return_value)
        self.assertEqual({"小圆": "圆子"}, services.personal_memory_aliases)

    def test_extension_management_translates_storage_error(self):
        registry = MagicMock()
        from mybot_ui.extension_registry import ExtensionRegistryError

        registry.import_skill.side_effect = ExtensionRegistryError("bad skill")

        with self.assertRaisesRegex(ExtensionOperationError, "bad skill"):
            ExtensionManagement(registry).import_skill("skill")


class ServerLifecycleTests(unittest.TestCase):
    def test_process_lookup_rejects_wechat_executable(self):
        service = WindowsServerLifecycle()
        with patch("mybot_ui.backend.os.name", "nt"), patch(
            "mybot_ui.backend.subprocess.run"
        ) as run:
            self.assertEqual(
                [],
                service.process_ids(Path(r"C:\Program Files\Tencent\Weixin.exe")),
            )
        run.assert_not_called()

    @patch.object(WindowsServerLifecycle, "process_ids")
    @patch.object(WindowsServerLifecycle, "sync_development_server_dll", return_value=True)
    @patch("mybot_ui.backend.socket.create_connection")
    @patch("mybot_ui.backend.subprocess.Popen")
    @patch("mybot_ui.backend.subprocess.run")
    def test_restart_stops_only_server_then_waits_for_port(
        self,
        run,
        popen,
        create_connection,
        _sync_dll,
        process_ids,
    ):
        process_ids.side_effect = [[42], [], []]
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        process = MagicMock(pid=1234)
        process.poll.return_value = None
        popen.return_value = process
        create_connection.return_value = MagicMock(
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )

        result = WindowsServerLifecycle().restart(
            Path(r"F:\server\Server.exe"),
            "ws://127.0.0.1:5177/ws",
        )

        self.assertTrue(result.ok)
        self.assertEqual(1234, result.value["pid"])
        run.assert_called_once_with(
            ["taskkill.exe", "/PID", "42", "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        create_connection.assert_called_once_with(("127.0.0.1", 5177), timeout=0.4)

    @patch("mybot_ui.backend.subprocess.Popen")
    @patch("mybot_ui.backend.subprocess.run")
    def test_restart_rejects_wechat_target(self, run, popen):
        result = WindowsServerLifecycle().restart(
            Path(r"C:\Program Files\Tencent\Weixin.exe"),
            "ws://127.0.0.1:5177/ws",
        )

        self.assertFalse(result.ok)
        run.assert_not_called()
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
