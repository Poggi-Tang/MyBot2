from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PIL import ImageGrab

from .wechat_menu_ocr import (
    MENU_CLASS_NAME,
    MENU_ITEM_CLASS_NAME,
    MENU_NAME,
    MenuOcrAnalyzer,
    find_text_item,
    inset_rect,
    ocr_rect,
    row_rects,
)
from .wechat_message_analysis import (
    MESSAGE_AUTOMATION_ID,
    MESSAGE_CLASSES,
    MessageAnalyzer,
    control_metadata,
    message_signature,
    read_conversation_context,
)


SESSION_AUTOMATION_ID = "session_list"
MESSAGE_LIST_AUTOMATION_ID = "chat_message_list"
IGNORED_CONVERSATIONS = {"服务号", "公众号", "折叠的聊天"}
MEDIA_TYPES = {"image": 2, "voice": 3, "file": 4, "sticker": 6}
_CONVERSATION_METADATA = {"消息免打扰", "已置顶"}
_TIME_LABEL = re.compile(
    r"^(?:(?:昨天|前天)\s+\d{1,2}:\d{2}|\d{1,2}:\d{2}|昨天|前天|"
    r"星期[一二三四五六日天]|\d{1,2}/\d{1,2})$"
)
_CONVERSATION_READY_ATTEMPTS = 20
_CONVERSATION_READY_INTERVAL = 0.1


class ConversationNotReadyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ListenerResult:
    ok: bool
    error: str = ""


@dataclass(frozen=True)
class ReferenceResult:
    ok: bool
    token: str = ""
    error: str = ""
    pages_scanned: int = 0


class WeChatMessageService:
    """Python UIA message listener and quote controller based on DebugTool."""

    def __init__(
        self,
        project_root: Path,
        automation: Any | None = None,
        *,
        image_grab: Callable[..., Any] = ImageGrab.grab,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 0.7,
    ) -> None:
        self._automation = automation
        self._image_grab = image_grab
        self._sleep = sleep
        self._poll_interval = max(0.15, float(poll_interval))
        self._analyzer = MessageAnalyzer(project_root / "data" / "avatar-identities.json")
        self._menu_ocr = MenuOcrAnalyzer()
        # A send starts on a worker and finishes on the Qt callback thread, so
        # use a plain Lock whose lease can be released by the completion path.
        self._operation_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._lease_lock = threading.Lock()
        self._stop = threading.Event()
        self._active = threading.Event()
        self._thread: threading.Thread | None = None
        self._targets: set[str] = set()
        self._callback: Callable[[dict[str, Any]], None] | None = None
        self._conversation_snapshots: dict[str, tuple[str, int]] = {}
        self._preview_baselines: dict[str, str] = {}
        self._message_snapshots: dict[str, tuple[str, ...]] = {}
        self._leases: dict[str, bool] = {}

    def start(
        self,
        targets: set[str] | list[str] | tuple[str, ...],
        callback: Callable[[dict[str, Any]], None],
        preview_baselines: dict[str, str] | None = None,
    ) -> ListenerResult:
        clean = {str(target).strip() for target in targets if str(target).strip()}
        if not clean:
            return ListenerResult(False, "未指定监听会话")
        with self._state_lock:
            self._targets = clean
            self._callback = callback
            self._preview_baselines = {
                str(title): str(value)
                for title, value in (preview_baselines or {}).items()
                if str(title) in clean
            }
            self._active.set()
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._run,
                    name="mybot-python-message-listener",
                    daemon=True,
                )
                self._thread.start()
        return ListenerResult(True)

    def update_targets(self, targets) -> ListenerResult:
        clean = {str(target).strip() for target in targets if str(target).strip()}
        if not clean:
            return ListenerResult(False, "未指定监听会话")
        with self._state_lock:
            self._targets = clean
        return ListenerResult(True)

    def pause(self) -> ListenerResult:
        self._active.clear()
        return ListenerResult(True)

    def resume(self) -> ListenerResult:
        if self._callback is None:
            return ListenerResult(False, "Python 消息监听尚未启动")
        self._active.set()
        return ListenerResult(True)

    def stop(self) -> None:
        self._active.clear()
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        with self._lease_lock:
            tokens = tuple(self._leases)
        for token in tokens:
            self.end_operation(token)

    def begin_operation(self, timeout: float = 10) -> str:
        if not self._operation_lock.acquire(timeout=max(0.1, timeout)):
            raise TimeoutError("等待 Python UIA 消息监听释放微信超时")
        token = uuid.uuid4().hex
        with self._lease_lock:
            self._leases[token] = True
        return token

    def end_operation(self, token: str) -> None:
        with self._lease_lock:
            owned = bool(token and self._leases.pop(token, None))
        if owned:
            self._operation_lock.release()

    def prepare_reference(
        self,
        token: str,
        conversation: str,
        message: str,
        *,
        sender: str = "",
        max_pages: int = 40,
    ) -> ReferenceResult:
        with self._lease_lock:
            owns_lease = token in self._leases
        if not owns_lease:
            return ReferenceResult(False, error="无效的微信操作锁")
        try:
            automation = self._automation or self._load_automation()
            initializer = getattr(automation, "UIAutomationInitializerInThread", None)
            if initializer is None:
                return self._prepare_reference(
                    automation, conversation, message, sender, max_pages, token
                )
            with initializer():
                return self._prepare_reference(
                    automation, conversation, message, sender, max_pages, token
                )
        except Exception as exc:
            return ReferenceResult(False, token, f"{type(exc).__name__}: {exc}")

    def _run(self) -> None:
        automation = self._automation or self._load_automation()
        initializer = getattr(automation, "UIAutomationInitializerInThread", None)
        try:
            if initializer is None:
                self._listen_loop(automation)
            else:
                with initializer():
                    self._listen_loop(automation)
        except Exception:
            self._active.clear()

    def _listen_loop(self, automation: Any) -> None:
        old_timeout = getattr(automation, "TIME_OUT_SECOND", 10)
        automation.SetGlobalSearchTimeout(0.2)
        try:
            while not self._stop.is_set():
                if not self._active.wait(timeout=self._poll_interval):
                    continue
                try:
                    with self._operation_lock:
                        self._poll_once(automation)
                except Exception:
                    self._sleep(self._poll_interval)
                self._stop.wait(self._poll_interval)
        finally:
            automation.SetGlobalSearchTimeout(old_timeout)

    def _poll_once(self, automation: Any) -> None:
        session_list = automation.ListControl(
            AutomationId=SESSION_AUTOMATION_ID,
            Name="会话",
            ClassName="mmui::XTableView",
        )
        if not self._exists(session_list):
            return
        with self._state_lock:
            targets = set(self._targets)
            callback = self._callback
        if callback is None:
            return
        session_list.WheelUp(wheelTimes=1000, interval=0, waitTime=0)
        seen: set[str] = set()
        no_new_rounds = 0
        try:
            while no_new_rounds < 2 and self._active.is_set():
                new_count = 0
                for session in session_list.GetChildren():
                    raw = str(getattr(session, "Name", "") or "")
                    if raw in seen:
                        continue
                    seen.add(raw)
                    new_count += 1
                    lines = raw.splitlines()
                    title = lines[0].strip() if lines else ""
                    if not title or title not in targets or title in IGNORED_CONVERSATIONS:
                        continue
                    unread_match = re.search(r"\[([0-9]+)条\]", raw)
                    unread = int(unread_match.group(1)) if unread_match else 0
                    fingerprint = self._preview_fingerprint(raw)
                    previous = self._conversation_snapshots.get(title)
                    self._conversation_snapshots[title] = (fingerprint, unread)
                    if previous is None:
                        baseline = self._preview_baselines.pop(title, None)
                        if baseline is None or baseline == fingerprint:
                            continue
                    else:
                        previous_fingerprint, previous_unread = previous
                        if (
                            fingerprint == previous_fingerprint
                            and unread <= previous_unread
                        ):
                            continue
                    if unread <= 0:
                        unread = 1
                    if not self._active.is_set():
                        continue
                    session.Click(simulateMove=False, waitTime=0)
                    self._sleep(0.08)
                    try:
                        event = self._read_current_messages(automation, title, unread)
                    except ConversationNotReadyError:
                        if previous is None:
                            self._conversation_snapshots.pop(title, None)
                        else:
                            self._conversation_snapshots[title] = previous
                        continue
                    if event:
                        callback(event)
                no_new_rounds = no_new_rounds + 1 if new_count == 0 else 0
                session_list.WheelDown(wheelTimes=6, interval=0.01, waitTime=0.05)
        finally:
            session_list.WheelUp(wheelTimes=1000, interval=0, waitTime=0)

    def _read_current_messages(
        self, automation: Any, title: str, expected_new: int = 1
    ) -> dict[str, Any] | None:
        context = self._wait_for_conversation(automation, title)
        if context is None:
            raise ConversationNotReadyError(f"会话尚未就绪：{title}")
        message_list = automation.ListControl(
            AutomationId=MESSAGE_LIST_AUTOMATION_ID,
            Name="消息",
            ClassName="mmui::RecyclerListView",
        )
        if not self._exists(message_list):
            raise ConversationNotReadyError(f"消息区域尚未就绪：{title}")
        analyses = []
        for item in message_list.GetChildren():
            metadata = control_metadata(item)
            if (
                metadata["AutomationId"] != MESSAGE_AUTOMATION_ID
                or metadata["ClassName"] not in MESSAGE_CLASSES
            ):
                continue
            rect = self._rect(item)
            if rect is None or rect[2] - rect[0] < 100 or rect[3] - rect[1] < 20:
                continue
            image = self._image_grab(bbox=rect, all_screens=True).convert("RGB")
            analysis = self._analyzer.analyze(
                image, metadata, context, screen_origin=(rect[0], rect[1])
            )
            analyses.append(analysis)
        signatures = tuple(message_signature(item) for item in analyses)
        previous = self._message_snapshots.get(title)
        self._message_snapshots[title] = signatures
        if previous is None:
            incoming = [item for item in analyses if item["direction"] == "incoming"]
            new_items = incoming[-max(1, expected_new) :]
        else:
            overlap = 0
            for count in range(min(len(previous), len(signatures)), 0, -1):
                if previous[-count:] == signatures[:count]:
                    overlap = count
                    break
            if signatures == previous:
                new_items = []
            elif overlap:
                new_items = analyses[overlap:]
            else:
                old_values = set(previous)
                new_items = [
                    item for item in analyses
                    if message_signature(item) not in old_values
                ]
        payload = []
        now = datetime.now().isoformat(timespec="seconds")
        for analysis in new_items:
            if analysis["direction"] != "incoming" or not analysis["content"]:
                continue
            message = analysis["message"]
            quote = message.get("quote") or {}
            sender = str(analysis["sender"].get("name") or "").strip()
            if not sender:
                sender = context.name if context.kind == "private" else "对方"
            payload.append(
                {
                    "who": sender,
                    "message": analysis["content"],
                    "send_date": now,
                    "message_type": MEDIA_TYPES.get(message.get("type"), 0),
                    "is_reference": bool(quote),
                    "referenced_who": quote.get("sender", ""),
                    "referenced_message": quote.get("content", ""),
                }
            )
        if not payload:
            return None
        return {
            "type": "python_message",
            "data": {
                "chat_title": title,
                "new_message": payload,
                "history_messages": [],
            },
        }

    def _prepare_reference(
        self,
        automation: Any,
        conversation: str,
        message: str,
        sender: str,
        max_pages: int,
        token: str,
    ) -> ReferenceResult:
        if not self._select_conversation(automation, conversation):
            return ReferenceResult(False, token, f"找不到会话：{conversation}")
        message_list = automation.ListControl(
            AutomationId=MESSAGE_LIST_AUTOMATION_ID,
            Name="消息",
            ClassName="mmui::RecyclerListView",
        )
        if not self._exists(message_list):
            return ReferenceResult(False, token, "找不到消息区域")
        seen_pages: set[tuple[str, ...]] = set()
        target = self._normalize_reference(message)
        for page in range(max(1, max_pages)):
            items = [
                item
                for item in message_list.GetChildren()
                if str(getattr(item, "AutomationId", "") or "") == MESSAGE_AUTOMATION_ID
            ]
            page_signature = tuple(str(getattr(item, "Name", "") or "") for item in items)
            if page_signature in seen_pages:
                break
            seen_pages.add(page_signature)
            for item in reversed(items):
                name = self._normalize_reference(getattr(item, "Name", ""))
                if not self._reference_matches(name, target):
                    continue
                if self._quote_item(automation, item, incoming=sender.strip() not in {"我", "自己"}):
                    return ReferenceResult(True, token, pages_scanned=page + 1)
            message_list.WheelUp(wheelTimes=6, interval=0.01, waitTime=0.05)
            self._sleep(0.12)
        return ReferenceResult(False, token, "向上翻页后仍未找到要引用的消息", len(seen_pages))

    def _select_conversation(self, automation: Any, conversation: str) -> bool:
        current = read_conversation_context(automation)
        if current.name == conversation:
            return True
        session_list = automation.ListControl(
            AutomationId=SESSION_AUTOMATION_ID,
            Name="会话",
            ClassName="mmui::XTableView",
        )
        session_list.WheelUp(wheelTimes=1000, interval=0, waitTime=0)
        seen: set[str] = set()
        no_new = 0
        while no_new < 2:
            count = 0
            for session in session_list.GetChildren():
                raw = str(getattr(session, "Name", "") or "")
                if raw in seen:
                    continue
                seen.add(raw)
                count += 1
                title = raw.splitlines()[0].strip() if raw else ""
                if title == conversation:
                    session.Click(simulateMove=False, waitTime=0)
                    self._sleep(0.08)
                    return self._wait_for_conversation(
                        automation, conversation
                    ) is not None
            no_new = no_new + 1 if count == 0 else 0
            session_list.WheelDown(wheelTimes=6, interval=0.01, waitTime=0.05)
        return False

    def _wait_for_conversation(self, automation: Any, conversation: str):
        expected = str(conversation or "").strip()
        for attempt in range(_CONVERSATION_READY_ATTEMPTS):
            context = read_conversation_context(automation)
            if context.name == expected:
                return context
            if attempt + 1 < _CONVERSATION_READY_ATTEMPTS:
                self._sleep(_CONVERSATION_READY_INTERVAL)
        return None

    def _quote_item(self, automation: Any, item: Any, *, incoming: bool) -> bool:
        # DebugTool detects the row visually; use the corresponding stable side
        # of the bubble instead of relying on a MenuItem accessibility name.
        item_rect = self._rect(item) or (0, 0, 0, 32)
        item.RightClick(
            x=104 if incoming else -104,
            y=min(31, max(8, item_rect[3] - item_rect[1] - 4)),
            simulateMove=False,
            waitTime=0.08,
        )
        self._sleep(0.08)
        menu = automation.WindowControl(Name=MENU_NAME, ClassName=MENU_CLASS_NAME)
        if not self._exists(menu):
            root = getattr(automation, "GetRootControl", lambda: None)()
            if root is not None:
                menu = root.WindowControl(Name=MENU_NAME, ClassName=MENU_CLASS_NAME)
        if not self._exists(menu):
            return False
        menu_rect = self._rect(menu)
        inner = inset_rect(menu_rect) if menu_rect else None
        capture = ocr_rect(inner) if inner else None
        if capture is None:
            return False
        item_rectangles = [
            rect
            for child in menu.GetChildren()
            if str(getattr(child, "ClassName", "") or "") == MENU_ITEM_CLASS_NAME
            if (rect := self._rect(child)) is not None
        ]
        rows = row_rects(capture, item_rectangles)
        image = self._image_grab(bbox=capture, all_screens=True).convert("RGB")
        result = self._menu_ocr.analyze(image, (capture[0], capture[1]), rows)
        quote = find_text_item(result["items"], "引用")
        if quote is None:
            self._dismiss_menu(automation)
            return False
        left, top, right, bottom = quote["rect"]
        automation.Click((left + right) // 2, (top + bottom) // 2, waitTime=0.08)
        return True

    @staticmethod
    def _dismiss_menu(automation: Any) -> None:
        send_keys = getattr(automation, "SendKeys", None)
        if callable(send_keys):
            send_keys("{Esc}", waitTime=0.02)

    @staticmethod
    def _reference_matches(candidate: str, target: str) -> bool:
        return bool(candidate and target) and (
            candidate == target or candidate in target or target in candidate
        )

    @staticmethod
    def _normalize_reference(value: Any) -> str:
        normalized = re.sub(r"\s+", " ", str(value or "").strip())
        if normalized.startswith("[") and normalized.endswith("]"):
            normalized = normalized[1:-1].strip()
        return normalized

    @staticmethod
    def _preview_fingerprint(raw: str) -> str:
        content_lines: list[str] = []
        time_label = ""
        for raw_line in str(raw or "").splitlines()[1:]:
            line = raw_line.strip()
            line = re.sub(r"^\[\d+条\]\s*", "", line)
            if (
                not line
                or line in _CONVERSATION_METADATA
            ):
                continue
            if _TIME_LABEL.fullmatch(line):
                time_label = line
            else:
                content_lines.append(line)
        return f"{'\n'.join(content_lines)}|{time_label}"

    @staticmethod
    def _rect(control: Any) -> tuple[int, int, int, int] | None:
        try:
            rect = control.BoundingRectangle
            result = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
            return result if result[2] > result[0] and result[3] > result[1] else None
        except Exception:
            return None

    @staticmethod
    def _exists(control: Any) -> bool:
        try:
            exists = getattr(control, "Exists", None)
            return bool(exists(0, 0)) if callable(exists) else control is not None
        except Exception:
            return False

    @staticmethod
    def _load_automation() -> Any:
        try:
            from uiautomation import uiautomation
        except ImportError as exc:
            raise RuntimeError("缺少 uiautomation 运行依赖") from exc
        return uiautomation
