import faulthandler
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from mybot_ui.app_v2 import MainWindow
from mybot_ui.theme import apply_theme


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
    app = QApplication(sys.argv)
    app.setApplicationName("MyBot 2.0")
    instance_lock = QLockFile(str(Path(tempfile.gettempdir()) / "mybot-2.0-ui.lock"))
    if not instance_lock.tryLock(0):
        _DIAGNOSTIC_STREAM.write("MyBot 2.0 is already running; duplicate launch rejected.\n")
        return 2
    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
