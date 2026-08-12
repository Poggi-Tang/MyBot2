from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon


TRAY_MENU_STYLE = """
QMenu {
    background: #ffffff;
    border: 1px solid #d9dade;
    padding: 4px;
}
QMenu::item {
    min-width: 112px;
    padding: 7px 22px 7px 12px;
    border-radius: 4px;
    color: #242629;
}
QMenu::item:selected {
    background: #e9eaec;
    color: #161719;
}
QMenu::item:pressed { background: #dfe1e4; }
QMenu::item:disabled { color: #b5b7bc; background: transparent; }
QMenu::separator {
    height: 1px;
    background: #e7e8ea;
    margin: 4px 8px;
}
"""


class TrayController(QObject):
    """Keep the main window alive in the Windows notification area."""

    def __init__(
        self,
        app: QApplication,
        window: QMainWindow,
        icon: QIcon,
        *,
        available: bool | None = None,
        show_tray: bool = True,
        quit_callback: Callable[[], None] | None = None,
        restart_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(app)
        self.app = app
        self.window = window
        self._exiting = False
        self._quit_callback = quit_callback or app.quit
        self._restart_callback = restart_callback
        self.available = (
            QSystemTrayIcon.isSystemTrayAvailable()
            if available is None
            else bool(available)
        )
        self.tray_icon: QSystemTrayIcon | None = None
        self.menu: QMenu | None = None
        self.show_action: QAction | None = None
        self.restart_action: QAction | None = None
        self.close_action: QAction | None = None
        self.exit_action: QAction | None = None
        if not self.available:
            return

        app.setQuitOnLastWindowClosed(False)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("MyBot2")
        self.menu = QMenu()
        self.menu.setObjectName("trayMenu")
        self.menu.setStyleSheet(TRAY_MENU_STYLE)
        self.show_action = self.menu.addAction("显示主界面")
        self.show_action.triggered.connect(self.show_window)
        self.menu.addSeparator()
        self.restart_action = self.menu.addAction("重启")
        self.restart_action.setEnabled(self._restart_callback is not None)
        self.restart_action.triggered.connect(self.restart_application)
        self.close_action = self.menu.addAction("关闭")
        self.close_action.triggered.connect(self.quit_application)
        self.exit_action = self.close_action
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.activated.connect(self._activated)
        window.installEventFilter(self)
        if show_tray:
            self.tray_icon.show()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        is_window_close = (
            self.available
            and watched is self.window
            and event.type() == QEvent.Type.Close
        )
        if is_window_close and bool(self.window.property("mybot_explicit_exit")):
            self._exiting = True
            self.window.removeEventFilter(self)
            if self.tray_icon is not None:
                self.tray_icon.hide()
            self._quit_callback()
            return False
        if is_window_close and not self._exiting:
            self.window.hide()
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_window()

    def show_window(self) -> None:
        if self.window.isMinimized():
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def quit_application(self) -> None:
        self._exiting = True
        self.window.setProperty("mybot_explicit_exit", True)
        self.window.removeEventFilter(self)
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.window.close()
        self._quit_callback()

    def restart_application(self) -> None:
        if self._exiting or self._restart_callback is None:
            return
        self._restart_callback()
        self.quit_application()

    def dispose(self) -> None:
        if self.available:
            try:
                self.window.removeEventFilter(self)
            except RuntimeError:
                pass
            self.available = False
        if self.tray_icon is not None:
            self.tray_icon.hide()
