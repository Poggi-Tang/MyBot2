from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def app_icon_path() -> Path:
    return PROJECT_ROOT / "assets" / "logo.svg"


def settings_icon_path() -> Path:
    return PROJECT_ROOT / "assets" / "settings.png"


def auto_chat_off_icon_path() -> Path:
    return PROJECT_ROOT / "assets" / "auto-chat-off.svg"


def auto_chat_on_icon_path() -> Path:
    return PROJECT_ROOT / "assets" / "auto-chat-on.svg"


def switch_off_icon_path() -> Path:
    return PROJECT_ROOT / "assets" / "auto-chat-off.svg"


def switch_on_icon_path() -> Path:
    return PROJECT_ROOT / "assets" / "auto-chat-on.svg"


def left_arrow_path() -> Path:
    return PROJECT_ROOT / "assets" / "left.svg"


def down_arrow_path() -> Path:
    return PROJECT_ROOT / "assets" / "down.svg"


def up_arrow_path() -> Path:
    return PROJECT_ROOT / "assets" / "up.svg"
