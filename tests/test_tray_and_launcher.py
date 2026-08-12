import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow

from launcher import launcher_command
from mybot_ui.resources import (
    app_icon_path,
    down_arrow_path,
    left_arrow_path,
    up_arrow_path,
)
from mybot_ui.restart import restart_helper_command
from mybot_ui.tray import TrayController
from scripts.generate_windows_version import version_info


class ProbeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.closed_normally = False

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.closed_normally = True
        event.accept()


class TrayAndLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_app_icon_exists_and_loads(self):
        self.assertTrue(app_icon_path().is_file())
        self.assertFalse(QIcon(str(app_icon_path())).isNull())

    def test_vector_arrow_assets_exist_and_load(self):
        for path in (left_arrow_path(), down_arrow_path(), up_arrow_path()):
            self.assertTrue(path.is_file())
            self.assertEqual(".svg", path.suffix)
            self.assertFalse(QIcon(str(path)).isNull())

    def test_close_hides_to_tray_and_explicit_exit_closes(self):
        window = ProbeWindow()
        exited = []
        controller = TrayController(
            self.app,
            window,
            QIcon(str(app_icon_path())),
            available=True,
            show_tray=False,
            quit_callback=lambda: exited.append(True),
        )
        window.show()
        close_event = QCloseEvent()
        self.assertTrue(controller.eventFilter(window, close_event))
        self.assertFalse(window.isVisible())
        self.assertFalse(window.closed_normally)

        controller.quit_application()
        self.assertTrue(window.closed_normally)
        self.assertEqual([True], exited)

    def test_tray_menu_has_show_restart_and_close_actions(self):
        window = ProbeWindow()
        controller = TrayController(
            self.app,
            window,
            QIcon(str(app_icon_path())),
            available=True,
            show_tray=False,
            restart_callback=lambda: None,
        )

        labels = [
            action.text()
            for action in controller.menu.actions()
            if not action.isSeparator()
        ]
        self.assertEqual(["显示主界面", "重启", "关闭"], labels)
        self.assertIn("QMenu::item:selected", controller.menu.styleSheet())
        self.assertIn("background: #e9eaec", controller.menu.styleSheet())
        controller.dispose()

    def test_restart_is_scheduled_before_clean_exit(self):
        window = ProbeWindow()
        events = []
        controller = TrayController(
            self.app,
            window,
            QIcon(str(app_icon_path())),
            available=True,
            show_tray=False,
            restart_callback=lambda: events.append("restart"),
            quit_callback=lambda: events.append("close"),
        )

        controller.restart_application()

        self.assertEqual(["restart", "close"], events)
        self.assertTrue(window.closed_normally)

    def test_update_close_bypasses_tray_and_quits(self):
        window = ProbeWindow()
        exited = []
        controller = TrayController(
            self.app,
            window,
            QIcon(str(app_icon_path())),
            available=True,
            show_tray=False,
            quit_callback=lambda: exited.append(True),
        )
        window.setProperty("mybot_explicit_exit", True)
        close_event = QCloseEvent()
        self.assertFalse(controller.eventFilter(window, close_event))
        self.assertEqual([True], exited)

    def test_launcher_uses_sibling_run_script_and_preserves_arguments(self):
        root = Path("C:/Program Files/MyBot2")
        command = launcher_command(root, ["-SkipServer"])
        self.assertEqual("powershell.exe", command[0])
        self.assertEqual(str(root / "run.ps1"), command[-2])
        self.assertEqual("-SkipServer", command[-1])

    def test_restart_helper_waits_and_prefers_exe_with_run_cmd_fallback(self):
        command = restart_helper_command(4321, Path(r"C:\Projects\MyBot2"))[-1]
        self.assertIn("Get-Process -Id 4321", command)
        self.assertIn("MyBot2.exe", command)
        self.assertIn("run.cmd", command)
        self.assertLess(
            command.index("Test-Path -LiteralPath $exe"),
            command.index("Test-Path -LiteralPath $cmd"),
        )

    def test_windows_version_resource_matches_release(self):
        value = version_info("2.4.1")
        self.assertIn("filevers=(2, 4, 1, 0)", value)
        self.assertIn("StringStruct('ProductVersion', '2.4.1')", value)


if __name__ == "__main__":
    unittest.main()
