from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any


_GROUP_TITLE = re.compile(r"\(\d+\)$")
_IGNORED_TITLES = {"服务号", "公众号", "折叠的聊天"}
_TITLE_AUTOMATION_ID = (
    "content_view.top_content_view.title_h_view.left_v_view."
    "left_content_v_view.left_ui_.big_title_line_h_view"
)
_CONTROL_SEARCH_TIMEOUT = 0.15
_TITLE_REFRESH_TIMEOUT = 1.2
_TITLE_POLL_INTERVAL = 0.05


@dataclass(frozen=True)
class ConversationScan:
    names: tuple[str, ...]
    groups: tuple[str, ...]
    privates: tuple[str, ...]
    elapsed_ms: float


@dataclass(frozen=True)
class ConversationScanResult:
    ok: bool
    scan: ConversationScan | None = None
    error: str = ""


class ConversationScanner:
    """Direct Python UIA scanner adapted from DebugTool/sdk.py."""

    def __init__(self, automation: Any | None = None, *, sleep=time.sleep) -> None:
        self._automation = automation
        self._sleep = sleep

    def try_scan(self) -> ConversationScanResult:
        try:
            automation = self._automation or self._load_automation()
            initializer = getattr(automation, "UIAutomationInitializerInThread", None)
            if initializer is None:
                return ConversationScanResult(True, self.scan(automation))
            with initializer():
                return ConversationScanResult(True, self.scan(automation))
        except Exception as exc:
            return ConversationScanResult(
                False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def scan(self, automation: Any | None = None) -> ConversationScan:
        automation = automation or self._automation or self._load_automation()
        old_timeout = getattr(automation, "TIME_OUT_SECOND", 10)
        started = time.perf_counter()
        session_list = None
        automation.SetGlobalSearchTimeout(_CONTROL_SEARCH_TIMEOUT)
        try:
            session_list = automation.ListControl(
                AutomationId="session_list",
                Name="会话",
                ClassName="mmui::XTableView",
            )
            session_list.WheelUp(wheelTimes=1000, interval=0, waitTime=0)

            privates: list[str] = []
            groups: list[str] = []
            names: list[str] = []
            seen: set[str] = set()
            no_new_rounds = 0

            while no_new_rounds < 2:
                new_count = 0
                for session in session_list.GetChildren():
                    session_key = str(session.Name or "")
                    if session_key in seen:
                        continue
                    seen.add(session_key)
                    new_count += 1

                    lines = session_key.splitlines()
                    title = lines[0].strip() if lines else ""
                    if not title or title in _IGNORED_TITLES:
                        continue

                    session.Click(simulateMove=False, waitTime=0)
                    header = self._wait_for_title(automation, title)
                    if not header:
                        raise RuntimeError(f"会话标题刷新超时：{title}")
                    names.append(title)
                    if _GROUP_TITLE.search(header):
                        groups.append(title)
                    else:
                        privates.append(title)

                no_new_rounds = no_new_rounds + 1 if new_count == 0 else 0
                session_list.WheelDown(wheelTimes=6, interval=0.01, waitTime=0.05)
                self._sleep(0.2)

            return ConversationScan(
                tuple(names),
                tuple(groups),
                tuple(privates),
                (time.perf_counter() - started) * 1000,
            )
        finally:
            try:
                if session_list is not None:
                    session_list.WheelUp(wheelTimes=1000, interval=0, waitTime=0)
            finally:
                automation.SetGlobalSearchTimeout(old_timeout)

    def _wait_for_title(self, automation: Any, expected_title: str) -> str:
        deadline = time.monotonic() + _TITLE_REFRESH_TIMEOUT
        while True:
            title_line = automation.Control(
                AutomationId=_TITLE_AUTOMATION_ID,
                ClassName="mmui::XHBoxView",
            )
            header = str(getattr(title_line, "Name", "") or "").strip()
            base_title = _GROUP_TITLE.sub("", header).rstrip()
            if header and base_title == expected_title:
                return header
            if time.monotonic() >= deadline:
                return ""
            self._sleep(_TITLE_POLL_INTERVAL)

    @staticmethod
    def _load_automation() -> Any:
        try:
            from uiautomation import uiautomation
        except ImportError as exc:
            raise RuntimeError(
                "缺少 uiautomation 运行依赖，请重新执行 setup.cmd"
            ) from exc
        return uiautomation
