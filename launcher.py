from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


def application_root() -> Path:
    executable = Path(sys.executable).resolve()
    return executable.parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def launcher_command(root: Path, arguments: list[str]) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(root / "run.ps1"),
        *arguments,
    ]


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, "MyBot2 启动失败", 0x10)


def main() -> int:
    root = application_root()
    script = root / "run.ps1"
    if not script.is_file():
        show_error(f"缺少启动脚本：\n{script}")
        return 2
    try:
        return subprocess.call(
            launcher_command(root, sys.argv[1:]),
            cwd=root,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        show_error(f"无法启动 MyBot2：\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
