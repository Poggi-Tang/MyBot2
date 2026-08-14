import ast
import unittest
from pathlib import Path


class ArchitectureBoundaryTests(unittest.TestCase):
    def _view_imported_names(self) -> set[str]:
        path = Path(__file__).resolve().parents[1] / "mybot_ui" / "app_v2.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }

    def test_qt_view_does_not_import_concrete_backend_clients(self):
        imported_names = self._view_imported_names()

        self.assertNotIn("Gateway", imported_names)
        self.assertNotIn("ChatModelClient", imported_names)

    def test_qt_view_does_not_import_concrete_application_services(self):
        imported_names = self._view_imported_names()
        forbidden = {
            "CodexRuntimeManager",
            "CodexCliRunner",
            "CodexThreadStore",
            "ConversationAttachmentStore",
            "ConversationMemory",
            "DailyWorkspaceStore",
            "EpisodicMemoryStore",
            "ExtensionAbilityStore",
            "ExtensionRegistry",
            "HiggsVoiceActor",
            "ImageUnderstandingCache",
            "PersonalMemoryLearner",
            "PersonalMemoryStore",
            "RealtimeToolExecutor",
            "ReusableTaskReviewer",
            "ThreadPoolExecutor",
            "WeChatAttachmentResolver",
        }

        self.assertFalse(forbidden & imported_names, forbidden & imported_names)

    def test_backend_layer_has_no_qt_dependency(self):
        source = (
            Path(__file__).resolve().parents[1] / "mybot_ui" / "backend.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }

        self.assertFalse(any(name.startswith("PySide6") for name in imported_modules))

    def test_controllers_have_no_qt_dependency(self):
        source = (
            Path(__file__).resolve().parents[1] / "mybot_ui" / "controllers.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("PySide6", source)

    def test_qt_view_uses_controllers_for_management_workflows(self):
        source = (
            Path(__file__).resolve().parents[1] / "mybot_ui" / "app_v2.py"
        ).read_text(encoding="utf-8")
        forbidden = (
            "self.personal_memory_store.reload(",
            "self.personal_memory_store.update(",
            "self.personal_memory_store.delete(",
            "self.episodic_memory_store.reload(",
            "self.episodic_memory_store.delete_person(",
            "self.daily_workspace_store.entries(",
            "self.daily_workspace_store.files(",
            "self.extension_registry.list_mcps(",
            "self.extension_registry.list_skills(",
            "self.extension_registry.import_",
            "self.extension_registry.remove_",
        )

        for value in forbidden:
            self.assertNotIn(value, source)

    def test_qt_view_delegates_primary_conversation_routing(self):
        source = (
            Path(__file__).resolve().parents[1] / "mybot_ui" / "app_v2.py"
        ).read_text(encoding="utf-8")

        self.assertIn("router.decide(", source)
        self.assertNotIn("detect_realtime_request(", source)
        self.assertNotIn("is_image_edit_request(", source)
        self.assertNotIn("CodexTaskRouter.should_delegate(", source)

    def test_qt_view_delegates_conversation_action_execution(self):
        path = Path(__file__).resolve().parents[1] / "mybot_ui" / "app_v2.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        process = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_process_next_auto_message"
        )
        body = ast.get_source_segment(source, process)

        self.assertIn("executor.execute(", body)
        self.assertNotIn("_send_auto_emoji(", body)
        self.assertNotIn("_send_auto_sticker(", body)
        self.assertNotIn("generate_image(", body)
        self.assertNotIn("generate_with_fallback(", body)

    def test_qt_view_does_not_implement_server_process_control(self):
        source = (
            Path(__file__).resolve().parents[1] / "mybot_ui" / "app_v2.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("taskkill.exe", source)
        self.assertNotIn("Get-CimInstance Win32_Process", source)
        self.assertNotIn("socket.create_connection", source)

    def test_qt_view_does_not_implement_conversation_uia_scanning(self):
        source = (
            Path(__file__).resolve().parents[1] / "mybot_ui" / "app_v2.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("uiautomation", source)
        self.assertNotIn('AutomationId="session_list"', source)


if __name__ == "__main__":
    unittest.main()
