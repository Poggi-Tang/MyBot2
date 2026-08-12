import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
)

from mybot_ui import __version__
from mybot_ui.app_v2 import MainWindow
from mybot_ui.chat_engine import IncomingMessage
from mybot_ui.theme import apply_theme


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def test_label_background_follows_parent_surface(self):
        frame = QFrame()
        frame.setObjectName("connectionBar")
        frame.resize(140, 50)
        label = QLabel("Server", frame)
        label.setGeometry(10, 10, 100, 28)
        frame.show()
        frame.ensurePolished()
        label.ensurePolished()

        image = frame.grab().toImage()
        parent_color = image.pixelColor(6, 25)
        label_color = image.pixelColor(15, 15)

        self.assertEqual(parent_color, label_color)
        self.assertEqual("#ffffff", label_color.name())
        frame.close()

    def test_base_persona_uses_a_multiline_editor(self):
        window = MainWindow()
        window._dock_timer.stop()
        try:
            self.assertIsInstance(window.model_system_prompt, QPlainTextEdit)
            self.assertEqual(112, window.model_system_prompt.height())
            value = "你是圆子。\n说话自然。\n不要机械复述。"
            window.model_system_prompt.setPlainText(value)
            self.assertEqual(value, window._model_config().system_prompt)
            self.assertEqual(value, window._backup_model_config().system_prompt)
        finally:
            for tool in window._tool_windows:
                tool.setProperty("mybot_explicit_exit", True)
                tool.close()
            window.setProperty("mybot_explicit_exit", True)
            window.close()

    def test_system_settings_has_about_version_and_update_controls(self):
        window = MainWindow()
        window._dock_timer.stop()
        try:
            settings_page = window._tool_windows[-1].centralWidget()
            system_tabs = next(
                tabs
                for tabs in settings_page.findChildren(QTabWidget)
                if "系统配置" in [tabs.tabText(index) for index in range(tabs.count())]
            )
            system_page = system_tabs.widget(
                [system_tabs.tabText(index) for index in range(system_tabs.count())].index("系统配置")
            )
            inner_tabs = next(
                tabs
                for tabs in system_page.findChildren(QTabWidget)
                if "关于" in [tabs.tabText(index) for index in range(tabs.count())]
            )

            self.assertEqual(
                ["回复设定", "模型配置", "安全管理", "关于"],
                [inner_tabs.tabText(index) for index in range(inner_tabs.count())],
            )
            about_page = inner_tabs.widget(3)
            self.assertEqual(__version__, window.about_version_label.text())
            self.assertIn(window.check_update_button, about_page.findChildren(type(window.check_update_button)))
            self.assertNotIn(window.check_update_button, inner_tabs.widget(2).findChildren(type(window.check_update_button)))
        finally:
            for tool in window._tool_windows:
                tool.setProperty("mybot_explicit_exit", True)
                tool.close()
            window.setProperty("mybot_explicit_exit", True)
            window.close()

    def test_dock_task_container_adds_and_removes_active_task_cells(self):
        window = MainWindow()
        window._dock_timer.stop()
        window._task_status_timer.stop()
        try:
            for index in range(3):
                incoming = IncomingMessage(
                    "测试群",
                    f"成员{index}",
                    f"任务{index}",
                    f"2026-08-12T12:00:0{index}",
                )
                MainWindow._task_status_enqueue(window, incoming)
                window.task_status_pool.update(
                    MainWindow._auto_task_key(incoming),
                    state="working",
                    stage="生成回复",
                    kind="模型",
                )
            window._refresh_task_status_view()

            self.assertFalse(window.dock_task_strip.isHidden())
            self.assertEqual(3, len(window._dock_task_cells))
            self.assertIsNone(window._nav_buttons[0].property("taskState"))
            for cell in window._dock_task_cells.values():
                self.assertIn("background: #", cell.styleSheet())
                self.assertNotIn("#07c160", cell.styleSheet())
            self.assertEqual(64, window.height())

            for item in window.task_status_pool.snapshots():
                window.task_status_pool.finish(item.task_id, success=True)
            window._refresh_task_status_view()

            self.assertTrue(window.dock_task_strip.isHidden())
            self.assertEqual(0, len(window._dock_task_cells))
            self.assertEqual("当前没有任务", window.dock_task_strip.toolTip())
            self.assertIsNone(window._nav_buttons[0].property("taskState"))
            self.assertEqual(48, window.height())
        finally:
            for tool in window._tool_windows:
                tool.setProperty("mybot_explicit_exit", True)
                tool.close()
            window.setProperty("mybot_explicit_exit", True)
            window.close()

    def test_dock_task_cell_is_green_when_task_is_queued(self):
        window = MainWindow()
        window._dock_timer.stop()
        window._task_status_timer.stop()
        try:
            incoming = IncomingMessage(
                "测试群", "成员", "等待处理", "2026-08-12T12:00:00"
            )
            MainWindow._task_status_enqueue(window, incoming)

            self.assertIsNone(window._nav_buttons[0].property("taskState"))
            self.assertFalse(window.dock_task_strip.isHidden())
            self.assertEqual(1, len(window._dock_task_cells))
            cell = next(iter(window._dock_task_cells.values()))
            self.assertIn("#07c160", cell.styleSheet())
        finally:
            for tool in window._tool_windows:
                tool.setProperty("mybot_explicit_exit", True)
                tool.close()
            window.setProperty("mybot_explicit_exit", True)
            window.close()

    def test_dock_auto_chat_button_tracks_running_state(self):
        window = MainWindow()
        window._dock_timer.stop()
        try:
            window._set_auto_chat_ui_state("running", 2)
            self.assertTrue(window.dock_auto_chat_toggle.property("running"))
            self.assertEqual("关闭自动对话", window.dock_auto_chat_toggle.toolTip())

            window._set_auto_chat_ui_state("stopped")
            self.assertFalse(window.dock_auto_chat_toggle.property("running"))
            self.assertEqual("启动自动对话", window.dock_auto_chat_toggle.toolTip())
        finally:
            for tool in window._tool_windows:
                tool.setProperty("mybot_explicit_exit", True)
                tool.close()
            window.setProperty("mybot_explicit_exit", True)
            window.close()

    def test_dock_toolbar_has_symmetric_outer_button_margins(self):
        window = MainWindow()
        window._dock_timer.stop()
        try:
            window.show()
            self.app.processEvents()

            left_margin = window.dock_auto_chat_toggle.mapTo(window, window.dock_auto_chat_toggle.rect().topLeft()).x()
            settings_button = window._nav_buttons[-1]
            settings_right = settings_button.mapTo(window, settings_button.rect().topRight()).x()
            right_margin = window.width() - 1 - settings_right

            self.assertLessEqual(abs(left_margin - right_margin), 1)
        finally:
            for tool in window._tool_windows:
                tool.setProperty("mybot_explicit_exit", True)
                tool.close()
            window.setProperty("mybot_explicit_exit", True)
            window.close()

    def test_feature_button_contains_catalog_mcp_and_unified_skills(self):
        window = MainWindow()
        window._dock_timer.stop()
        try:
            self.assertEqual(
                ["运行", "知识库", "功能", "设置"],
                [button.accessibleName() for button in window._nav_buttons],
            )
            run_button = window._nav_buttons[0]
            self.assertEqual("运行", run_button.text())
            self.assertEqual("dockButton", run_button.objectName())
            self.assertEqual("任务、连接与测试", run_button.toolTip())
            self.assertIsNone(run_button.property("connected"))
            self.assertIsNone(run_button.property("taskState"))
            feature_page = window._tool_windows[2].centralWidget()
            tabs = next(
                child
                for child in feature_page.findChildren(QTabWidget)
                if [child.tabText(index) for index in range(child.count())]
                == ["功能列表", "MCP", "Skill"]
            )
            self.assertEqual(3, tabs.count())
            self.assertGreaterEqual(window.mcp_table.rowCount(), 2)
            self.assertGreaterEqual(window.skill_table.rowCount(), 1)
            self.assertEqual(9, window.skill_table.columnCount())
            skill_types = {
                window.skill_table.item(row, 2).text()
                for row in range(window.skill_table.rowCount())
                if window.skill_table.item(row, 2) is not None
            }
            self.assertIn("自动匹配", skill_types)
            for table, toggle_column in ((window.mcp_table, 5), (window.skill_table, 8)):
                toggle = table.cellWidget(0, toggle_column)
                self.assertIsInstance(toggle, QPushButton)
                self.assertFalse(toggle.icon().isNull())
                self.assertEqual("extensionToggle", toggle.objectName())
        finally:
            for tool in window._tool_windows:
                tool.setProperty("mybot_explicit_exit", True)
                tool.close()
            window.setProperty("mybot_explicit_exit", True)
            window.close()


if __name__ == "__main__":
    unittest.main()
