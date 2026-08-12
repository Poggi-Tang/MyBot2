from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow


@dataclass(frozen=True)
class DockRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class WeChatWindow:
    handle: int
    rect: DockRect
    work_area: DockRect


def toolbar_rect(
    wechat: DockRect | None,
    work_area: DockRect,
    width: int,
    height: int,
    *,
    gap: int = 0,
) -> DockRect:
    if wechat is None:
        x = work_area.x + (work_area.width - width) // 2
        y = work_area.bottom - height - gap
        return _clamp(DockRect(x, y, width, height), work_area)

    x = wechat.x + (wechat.width - width) // 2
    below = work_area.bottom - wechat.bottom
    above = wechat.y - work_area.y
    if below >= height + gap:
        y = wechat.bottom + gap
    elif above >= height + gap:
        y = wechat.y - height - gap
    else:
        y = wechat.bottom - height - 12
    return _clamp(DockRect(x, y, width, height), work_area)


def tool_rect(
    wechat: DockRect,
    work_area: DockRect,
    preferred_width: int,
    preferred_height: int,
    *,
    minimum_width: int = 520,
    gap: int = 0,
) -> tuple[DockRect, str]:
    right_space = max(0, work_area.right - wechat.right - gap)
    left_space = max(0, wechat.x - work_area.x - gap)
    side = "right" if right_space >= minimum_width else "left"
    if side == "left" and left_space < minimum_width and right_space > left_space:
        side = "right"
    available_width = right_space if side == "right" else left_space
    width = min(preferred_width, max(minimum_width, available_width))
    width = min(width, work_area.width)
    height = min(preferred_height, work_area.height)
    y = min(max(wechat.y, work_area.y), work_area.bottom - height)
    x = wechat.right + gap if side == "right" else wechat.x - gap - width
    return _clamp(DockRect(x, y, width, height), work_area), side


def _clamp(rect: DockRect, bounds: DockRect) -> DockRect:
    width = min(rect.width, bounds.width)
    height = min(rect.height, bounds.height)
    x = min(max(rect.x, bounds.x), bounds.right - width)
    y = min(max(rect.y, bounds.y), bounds.bottom - height)
    return DockRect(x, y, width, height)


def dock_context_is_foreground(
    wechat_handle: int,
    application_process_id: int,
    *,
    foreground_handle: int | None = None,
    foreground_process_id: int | None = None,
) -> bool:
    if foreground_handle is None:
        if os.name != "nt":
            return True
        foreground_handle = int(ctypes.windll.user32.GetForegroundWindow())
    if not foreground_handle:
        return False
    if foreground_handle == wechat_handle:
        return True
    if foreground_process_id is None:
        if os.name != "nt":
            return False
        process_id = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(
            foreground_handle, ctypes.byref(process_id)
        )
        foreground_process_id = int(process_id.value)
    return foreground_process_id in {
        application_process_id,
        _window_process_id(wechat_handle),
    }


def _window_process_id(hwnd: int) -> int:
    if os.name != "nt":
        return 0
    process_id = ctypes.wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value)


class DockToolWindow(QMainWindow):
    def __init__(
        self,
        title: str,
        on_hidden: Callable[[], None],
        parent: QMainWindow,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._on_hidden = on_hidden

    def closeEvent(self, event) -> None:  # noqa: N802
        if bool(self.property("mybot_explicit_exit")):
            event.accept()
            return
        event.ignore()
        self.hide()
        self._on_hidden()


def find_wechat_window() -> WeChatWindow | None:
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    candidates: list[tuple[int, int, DockRect]] = []

    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        title = title_buffer.value.strip()
        executable = _window_executable(hwnd)
        is_wechat = (
            title.casefold() in {"微信", "wechat"}
            or Path(executable).name.casefold()
            in {"wechat.exe", "wechatappex.exe", "weixin.exe"}
        )
        if not is_wechat:
            return True
        rect = _visible_window_rect(hwnd)
        if rect is None:
            return True
        if rect.width >= 400 and rect.height >= 400:
            candidates.append((rect.width * rect.height, int(hwnd), rect))
        return True

    user32.EnumWindows(visit, 0)
    if not candidates:
        return None
    _area, handle, rect = max(candidates)
    return WeChatWindow(handle, rect, _monitor_work_area(handle, rect))


def _visible_window_rect(hwnd: int) -> DockRect | None:
    native = ctypes.wintypes.RECT()
    try:
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            9,  # DWMWA_EXTENDED_FRAME_BOUNDS
            ctypes.byref(native),
            ctypes.sizeof(native),
        )
    except (AttributeError, OSError):
        result = -1
    if result != 0 and not ctypes.windll.user32.GetWindowRect(
        hwnd, ctypes.byref(native)
    ):
        return None
    width = native.right - native.left
    height = native.bottom - native.top
    if width <= 0 or height <= 0:
        return None
    return DockRect(native.left, native.top, width, height)


def _window_executable(hwnd: int) -> str:
    if os.name != "nt":
        return ""
    process_id = ctypes.wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    process = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id.value)
    if not process:
        return ""
    try:
        size = ctypes.wintypes.DWORD(32_768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
            process, 0, buffer, ctypes.byref(size)
        ):
            return buffer.value
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def _monitor_work_area(hwnd: int, fallback: DockRect) -> DockRect:
    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("rcMonitor", ctypes.wintypes.RECT),
            ("rcWork", ctypes.wintypes.RECT),
            ("dwFlags", ctypes.wintypes.DWORD),
        ]

    monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    if monitor and ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        work = info.rcWork
        return DockRect(
            work.left,
            work.top,
            work.right - work.left,
            work.bottom - work.top,
        )
    return fallback
