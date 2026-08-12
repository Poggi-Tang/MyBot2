import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from mybot_ui.app_v2 import MainWindow
from mybot_ui.docking import DockRect
from mybot_ui.theme import apply_theme


class DockPageSwitchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def test_page_switch_does_not_refresh_data_or_enumerate_windows(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("page switch performed synchronous work")

        tools = [QWidget() for _ in range(4)]
        window = SimpleNamespace(
            _tool_windows=tools,
            _nav_buttons=[QPushButton() for _ in range(4)],
            _active_tool_index=-1,
            _last_tool_rect=DockRect(900, 100, 760, 700),
            _refresh_personal_memory_page=forbidden,
            _refresh_mcp_list=forbidden,
            _refresh_skill_list=forbidden,
            _sync_docked_windows=forbidden,
        )

        try:
            for index in range(4):
                MainWindow._select_page(window, index)
            self.assertEqual(3, window._active_tool_index)
            self.assertTrue(window._tool_windows[3].isVisible())
        finally:
            for tool in tools:
                tool.close()


if __name__ == "__main__":
    unittest.main()
