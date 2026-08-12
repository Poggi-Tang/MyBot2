import faulthandler
import ctypes
import os
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, qInstallMessageHandler
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from mybot_ui.app_v2 import MainWindow
from mybot_ui.resources import app_icon_path
from mybot_ui.restart import launch_restart_helper
from mybot_ui.theme import apply_theme
from mybot_ui.tray import TrayController


_DIAGNOSTIC_STREAM = None


def install_diagnostics() -> None:
    global _DIAGNOSTIC_STREAM
    path = Path(__file__).resolve().parent / "crash.log"
    _DIAGNOSTIC_STREAM = path.open("a", encoding="utf-8", buffering=1)
    _DIAGNOSTIC_STREAM.write(
        f"\n[{datetime.now().isoformat(timespec='seconds')}] process started\n"
    )
    faulthandler.enable(_DIAGNOSTIC_STREAM, all_threads=True)

    def write_exception(kind: str, exc_type, exc_value, exc_traceback) -> None:
        _DIAGNOSTIC_STREAM.write(
            f"\n[{datetime.now().isoformat(timespec='seconds')}] {kind}\n"
        )
        traceback.print_exception(
            exc_type,
            exc_value,
            exc_traceback,
            file=_DIAGNOSTIC_STREAM,
        )
        _DIAGNOSTIC_STREAM.flush()

    sys.excepthook = lambda exc_type, exc_value, exc_traceback: write_exception(
        "unhandled exception", exc_type, exc_value, exc_traceback
    )
    threading.excepthook = lambda args: write_exception(
        f"thread exception: {args.thread.name}",
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
    )

    def qt_message_handler(message_type, context, message) -> None:
        message_code = getattr(message_type, "value", message_type)
        _DIAGNOSTIC_STREAM.write(
            f"[{datetime.now().isoformat(timespec='seconds')}] Qt {message_code}: {message}\n"
        )

    qInstallMessageHandler(qt_message_handler)


def main() -> int:
    install_diagnostics()
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PoggiTang.MyBot2")
    app = QApplication(sys.argv)
    app.setApplicationName("MyBot 2.0")
    icon = QIcon(str(app_icon_path()))
    app.setWindowIcon(icon)
    instance_lock = QLockFile(str(Path(tempfile.gettempdir()) / "mybot-2.0-ui.lock"))
    if not instance_lock.tryLock(0):
        _DIAGNOSTIC_STREAM.write("MyBot 2.0 is already running; duplicate launch rejected.\n")
        return 2
    apply_theme(app)
    window = MainWindow()
    window.setWindowIcon(icon)
    tray = TrayController(
        app,
        window,
        icon,
        restart_callback=lambda: launch_restart_helper(
            os.getpid(), Path(__file__).resolve().parent
        ),
    )
    window.show()
    result = app.exec()
    tray.dispose()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
