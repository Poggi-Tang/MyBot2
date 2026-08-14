import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QVBoxLayout, QWidget

from mybot_ui.app_v2 import MainWindow, NewApiImportDialog, ReplyPolicyDialog
from mybot_ui.automation_ids import (
    AutomationIdManager,
    automation_id,
    mybot_automation_id,
    semantic_token,
)
from mybot_ui.reply_policy import ReplyPolicy
from mybot_ui.resources import app_icon_path
from mybot_ui.tray import TrayController


class AutomationIdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_operable_controls_have_unique_mybot_ids(self):
        window = MainWindow()
        try:
            report = window.automation_ids.audit()

            self.assertEqual([], report["missing"])
            self.assertEqual([], report["invalid"])
            self.assertEqual([], report["duplicates"])
            self.assertGreater(len(report["ids"]), 200)
        finally:
            window.close()

    def test_critical_workflow_ids_are_stable(self):
        window = MainWindow()
        try:
            expected = {
                "dock_auto_chat_toggle": "MyBot.MainWindow.dock_auto_chat_toggle",
                "connect_button": "MyBot.MainWindow.connect_button",
                "restart_server_button": "MyBot.MainWindow.restart_server_button",
                "restart_app_button": "MyBot.MainWindow.restart_app_button",
                "auto_chat_start": "MyBot.MainWindow.auto_chat_start",
                "auto_chat_stop": "MyBot.MainWindow.auto_chat_stop",
                "memory_save_button": "MyBot.MainWindow.memory_save_button",
                "mcp_table": "MyBot.MainWindow.mcp_table",
                "skill_table": "MyBot.MainWindow.skill_table",
            }
            for member_name, expected_id in expected.items():
                self.assertEqual(expected_id, automation_id(getattr(window, member_name)))

            self.assertEqual(
                [
                    "MyBot.MainWindow.nav_run_button",
                    "MyBot.MainWindow.nav_knowledge_button",
                    "MyBot.MainWindow.nav_features_button",
                    "MyBot.MainWindow.nav_settings_button",
                ],
                [automation_id(button) for button in window._nav_buttons],
            )
        finally:
            window.close()

    def test_dialogs_have_complete_automation_ids(self):
        import_dialog = NewApiImportDialog()
        reply_dialog = ReplyPolicyDialog(ReplyPolicy(), ["测试会话"])
        for dialog in (import_dialog, reply_dialog):
            report = dialog.automation_ids.audit()
            self.assertEqual([], report["missing"])
            self.assertEqual([], report["invalid"])
            self.assertEqual([], report["duplicates"])
            dialog.close()

    def test_dynamic_operable_child_is_marked_after_event_delivery(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        manager = AutomationIdManager(parent=root)
        manager.register_root(root, "DynamicWindow")

        control = QPushButton("动态操作", root)
        layout.addWidget(control)
        self.app.processEvents()

        self.assertTrue(automation_id(control).startswith("MyBot.DynamicWindow."))
        self.assertEqual([], manager.audit()["missing"])

    def test_dynamic_extension_ids_are_independent_of_row_order(self):
        first = mybot_automation_id(
            "MainWindow", f"mcp_{semantic_token('autowx', 'extension')}_toggle"
        )
        second = mybot_automation_id(
            "MainWindow", f"mcp_{semantic_token('filesystem', 'extension')}_toggle"
        )

        self.assertEqual("MyBot.MainWindow.mcp_autowx_toggle", first)
        self.assertEqual("MyBot.MainWindow.mcp_filesystem_toggle", second)

    def test_inventory_never_serializes_password_values_or_placeholders(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        secret = QLineEdit(root)
        secret.setEchoMode(QLineEdit.EchoMode.Password)
        secret.setPlaceholderText("sk-example-placeholder")
        secret.setText("real-secret-value")
        layout.addWidget(secret)
        manager = AutomationIdManager(parent=root)
        manager.register_root(root, "SecurityProbe")

        record = next(
            item for item in manager.inventory() if item["class"] == "QLineEdit"
        )
        self.assertEqual("protected_input", record["name"])
        self.assertNotIn("secret", str(record))
        self.assertNotIn("sk-", str(record))

    def test_tray_menu_actions_keep_mybot_markers(self):
        window = QWidget()
        controller = TrayController(
            self.app,
            window,
            QIcon(str(app_icon_path())),
            available=True,
            show_tray=False,
        )
        try:
            self.assertEqual("MyBot.Tray.menu", automation_id(controller.menu))
            self.assertEqual(
                {
                    "MyBot.Tray.show_action",
                    "MyBot.Tray.restart_action",
                    "MyBot.Tray.close_action",
                },
                {
                    str(action.property("mybot_automation_id"))
                    for action in (
                        controller.show_action,
                        controller.restart_action,
                        controller.close_action,
                    )
                },
            )
        finally:
            controller.dispose()
            window.close()


if __name__ == "__main__":
    unittest.main()
