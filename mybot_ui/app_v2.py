from __future__ import annotations

import base64
import json
import os
import re
import time
import ctypes
import ctypes.wintypes
import socket
import subprocess
import uuid
from collections import deque
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .api import Gateway, GatewayResult
from .attachments import (
    ConversationAttachmentStore,
    IncomingAttachment,
    WeChatAttachmentResolver,
    attachment_type_label,
    is_image_edit_followup,
    is_image_edit_request,
)
from .auto_chat import (
    ListenerMessageCursor,
    ReplyAction,
    ReplyKind,
    incoming_dedupe_feature,
    infer_sticker_query,
    model_sticker_request,
    parse_auto_reply_segments,
    requested_action,
    sanitize_auto_reply_text,
    select_sticker_item,
    sticker_item_display_name,
    sticker_item_send_value,
    sticker_selection_candidates,
)
from .catalog import TOOLS, TOOL_MAP, build_message_reference, build_options
from .chat_engine import (
    ChatModelClient,
    ConversationMemory,
    ImageConfig,
    IncomingMessage,
    ModelConfig,
    parse_conversation_preview,
    parse_listener_event,
)
from .operation_log import operations
from .image_understanding import ImageUnderstandingCache, extract_image_understanding
from .codex_router import CodexTaskRouter, ReusableTaskReviewer
from .codex_runner import CodexCliRunner, CodexResult, CodexRuntimeConfig, CodexThreadStore
from .extension_abilities import ExtensionAbilityStore
from .episodic_memory import EpisodicMemoryStore
from .personal_memory import PersonalMemoryLearner, PersonalMemoryStore, PersonalProfile, person_id
from .reply_policy import ReplyPolicy, ReplyProfile
from .realtime_tools import RealtimeToolExecutor, detect_realtime_request


DEFAULT_WINDOW_LAYOUT = {
    "x": 782,
    "y": 0,
    "width": 1066,
    "height": 1399,
}
PENDING_IMAGE_EDIT_TTL_SECONDS = 60 * 60
STICKER_IN_FLIGHT_TTL_SECONDS = 30.0
STICKER_COOLDOWN_SECONDS = 60.0
_IMAGE_CONTEXT_REQUEST = re.compile(
    r"(?:上面|刚才|之前|最近|我发(?:的)?|这张|那张).{0,10}(?:图片|照片|原图|图)|"
    r"(?:图片|照片|原图).{0,10}(?:看|理解|识别|引用|处理|修改|改)",
    re.IGNORECASE,
)
_IMAGE_QUOTE_REQUEST = re.compile(
    r"(?:引用|带上).{0,12}(?:我发(?:的)?|上面|刚才|之前|最近|这张|那张)?.{0,8}(?:图片|照片|原图)|"
    r"(?:图片|照片|原图).{0,10}(?:引用|带上)",
    re.IGNORECASE,
)
_IMAGE_RESEND_REPLY = re.compile(
    r"(?:再|重新|麻烦|请).{0,5}(?:发|发送).{0,8}(?:图片|照片|原图|一张|一次|一下)|"
    r"(?:图片|照片|原图).{0,8}(?:再|重新).{0,5}(?:发|发送)",
    re.IGNORECASE,
)


def normalize_window_layout(settings: dict[str, Any]) -> dict[str, int]:
    configured = settings.get("window", {})
    if not isinstance(configured, dict):
        configured = {}
    result: dict[str, int] = {}
    for key, default in DEFAULT_WINDOW_LAYOUT.items():
        try:
            result[key] = int(configured.get(key, default))
        except (TypeError, ValueError):
            result[key] = default
    result["width"] = max(1050, result["width"])
    result["height"] = max(680, result["height"])
    return result


class GatewayEventBridge(QObject):
    received = Signal(object)


def button(text: str, slot: Callable, primary: bool = False) -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName("primary" if primary else "")
    widget.clicked.connect(slot)
    return widget


def label(text: str, object_name: str = "") -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    return widget


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet("QFrame#card { background: #141d28; border: 1px solid #253241; border-radius: 8px; }")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 15, 18, 15)
    layout.setSpacing(10)
    layout.addWidget(label(title, "sectionTitle"))
    return frame, layout


class ReplyPolicyDialog(QDialog):
    def __init__(self, policy: ReplyPolicy, target_names: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("回复策略")
        self.resize(760, 650)
        self._contact_profiles = dict(policy.contact_profiles)
        self._conversation_profiles = dict(policy.conversation_profiles)
        self._target_names = sorted({name.strip() for name in target_names if name.strip()})

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        persona = QWidget()
        persona_form = QFormLayout(persona)
        self.policy_ai_name = QLineEdit(policy.ai_name)
        self.policy_ai_name.setPlaceholderText("例如：圆子")
        self.policy_ai_identity = self._editor(policy.ai_identity, 120)
        self.policy_persona_traits = self._editor(policy.persona_traits, 110)
        self.policy_example_dialogues = self._editor("\n\n".join(policy.example_dialogues), 190)
        self.policy_example_dialogues.setPlaceholderText(
            "每段示例之间空一行，例如：\n对方：今天好累\n圆子：那先歇会儿，别硬扛"
        )
        persona_form.addRow("AI 名字", self.policy_ai_name)
        persona_form.addRow("身份设定", self.policy_ai_identity)
        persona_form.addRow("人格特质", self.policy_persona_traits)
        persona_form.addRow("示例对话", self.policy_example_dialogues)
        tabs.addTab(persona, "AI 人格")

        common = QWidget()
        common_form = QFormLayout(common)
        self.policy_style = self._editor(policy.style, 80)
        self.policy_boundaries = self._editor("\n".join(policy.boundaries), 140)
        self.policy_refusal = self._editor(policy.refusal_style, 80)
        self.policy_private = self._editor(policy.private_rules, 80)
        self.policy_group = self._editor(policy.group_rules, 80)
        common_form.addRow("通用回复方式", self.policy_style)
        common_form.addRow("不能回复什么", self.policy_boundaries)
        common_form.addRow("不能回复时怎么说", self.policy_refusal)
        common_form.addRow("私聊通用规则", self.policy_private)
        common_form.addRow("群聊通用规则", self.policy_group)
        tabs.addTab(common, "通用规则")

        profiles = QWidget()
        profile_layout = QVBoxLayout(profiles)
        selector = QHBoxLayout()
        self.profile_kind = QComboBox()
        self.profile_kind.addItems(["联系人", "会话"])
        self.profile_name = QComboBox()
        self.profile_name.setEditable(True)
        self.profile_name.setInsertPolicy(QComboBox.NoInsert)
        selector.addWidget(label("类型", "muted"))
        selector.addWidget(self.profile_kind)
        selector.addWidget(label("名称", "muted"))
        selector.addWidget(self.profile_name, 1)
        profile_layout.addLayout(selector)

        profile_form = QFormLayout()
        self.profile_relationship = QLineEdit()
        self.profile_relationship.setPlaceholderText("例如：家人、同事、客户、普通朋友")
        self.profile_style = self._editor("", 90)
        self.profile_instructions = self._editor("", 120)
        profile_form.addRow("关系背景", self.profile_relationship)
        profile_form.addRow("专属语气", self.profile_style)
        profile_form.addRow("附加规则", self.profile_instructions)
        profile_layout.addLayout(profile_form)

        profile_actions = QHBoxLayout()
        profile_actions.addStretch()
        profile_actions.addWidget(button("删除当前设置", self._delete_profile))
        profile_actions.addWidget(button("保存当前设置", self._save_profile, True))
        profile_layout.addLayout(profile_actions)
        tabs.addTab(profiles, "联系人 / 会话专属")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存全部策略")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.profile_kind.currentIndexChanged.connect(self._reload_profile_names)
        self.profile_name.currentTextChanged.connect(self._load_profile)
        self._reload_profile_names()

    @staticmethod
    def _editor(text: str, height: int) -> QPlainTextEdit:
        editor = QPlainTextEdit(text)
        editor.setMaximumHeight(height)
        return editor

    def _profile_store(self) -> dict[str, ReplyProfile]:
        return self._contact_profiles if self.profile_kind.currentIndex() == 0 else self._conversation_profiles

    def _reload_profile_names(self) -> None:
        current = self.profile_name.currentText().strip()
        names = set(self._profile_store())
        if self.profile_kind.currentIndex() == 1:
            names.update(self._target_names)
        self.profile_name.blockSignals(True)
        self.profile_name.clear()
        self.profile_name.addItems(sorted(names))
        if current:
            self.profile_name.setEditText(current)
        self.profile_name.blockSignals(False)
        self._load_profile(self.profile_name.currentText())

    def _load_profile(self, name: str) -> None:
        profile = self._profile_store().get(name.strip(), ReplyProfile())
        self.profile_relationship.setText(profile.relationship)
        self.profile_style.setPlainText(profile.style)
        self.profile_instructions.setPlainText(profile.instructions)

    def _save_profile(self) -> None:
        name = self.profile_name.currentText().strip()
        if not name:
            QMessageBox.warning(self, "缺少名称", "请填写联系人或会话名称。")
            return
        profile = ReplyProfile(
            relationship=self.profile_relationship.text().strip(),
            style=self.profile_style.toPlainText().strip(),
            instructions=self.profile_instructions.toPlainText().strip(),
        )
        if profile.configured:
            self._profile_store()[name] = profile
        else:
            self._profile_store().pop(name, None)
        self._reload_profile_names()

    def _delete_profile(self) -> None:
        name = self.profile_name.currentText().strip()
        if name:
            self._profile_store().pop(name, None)
            self._reload_profile_names()

    def accept(self) -> None:
        if self.profile_name.currentText().strip() and any((
            self.profile_relationship.text().strip(),
            self.profile_style.toPlainText().strip(),
            self.profile_instructions.toPlainText().strip(),
        )):
            self._save_profile()
        super().accept()

    def policy(self) -> ReplyPolicy:
        return ReplyPolicy.from_mapping({
            "ai_name": self.policy_ai_name.text(),
            "ai_identity": self.policy_ai_identity.toPlainText(),
            "persona_traits": self.policy_persona_traits.toPlainText(),
            "example_dialogues": self.policy_example_dialogues.toPlainText(),
            "reply_style": self.policy_style.toPlainText(),
            "boundaries": self.policy_boundaries.toPlainText(),
            "refusal_style": self.policy_refusal.toPlainText(),
            "private_rules": self.policy_private.toPlainText(),
            "group_rules": self.policy_group.toPlainText(),
            "contact_profiles": {
                name: profile.to_mapping() for name, profile in self._contact_profiles.items()
            },
            "conversation_profiles": {
                name: profile.to_mapping() for name, profile in self._conversation_profiles.items()
            },
        })


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config_path = Path(__file__).resolve().parent.parent / "config.json"
        self.runtime_log_path = Path(__file__).resolve().parent.parent / "runtime.log"
        self.settings, self._config_load_error = self._load_settings()
        self._reply_policy = ReplyPolicy.from_mapping(self.settings.get("chat", {}))
        self._window_layout_ready = False
        self._window_layout_timer = QTimer(self)
        self._window_layout_timer.setSingleShot(True)
        self._window_layout_timer.setInterval(650)
        self._window_layout_timer.timeout.connect(self._save_window_layout)
        self._auto_selection_save_timer = QTimer(self)
        self._auto_selection_save_timer.setSingleShot(True)
        self._auto_selection_save_timer.setInterval(300)
        self._auto_selection_save_timer.timeout.connect(self._persist_auto_chat_selection)
        self._loading_auto_chat_targets = False
        self._auto_selection_restored = False
        self.setWindowTitle("MyBot 2.0 · AI WeChat Operator")
        self.resize(1360, 860)
        self.setMinimumSize(1050, 680)
        wechat_settings = self.settings.get("wechat", {})
        if not isinstance(wechat_settings, dict):
            wechat_settings = {}
        try:
            websocket_max_message_mb = max(
                4,
                min(512, int(wechat_settings.get("max_message_mb", 64))),
            )
        except (TypeError, ValueError):
            websocket_max_message_mb = 64
        self.gateway = Gateway(
            max_message_bytes=websocket_max_message_mb * 1024 * 1024,
        )
        self._connect_in_progress = False
        self.gateway_events = GatewayEventBridge(self)
        self.gateway_events.received.connect(self._gateway_event)
        self.gateway.add_listener(self.gateway_events.received.emit)
        self.account = ""
        self.model_client = ChatModelClient()
        self.memory = ConversationMemory()
        configured_chat = self.settings.get("chat", {})
        if not isinstance(configured_chat, dict):
            configured_chat = {}
        try:
            configured_chat_concurrency = max(1, min(8, int(configured_chat.get("max_concurrency", 3))))
        except (TypeError, ValueError):
            configured_chat_concurrency = 3
        self._configured_chat_concurrency = configured_chat_concurrency
        self.model_executor = ThreadPoolExecutor(
            max_workers=max(4, configured_chat_concurrency * 2),
            thread_name_prefix="mybot-ai",
        )
        personal_memory_settings = self.settings.get("personal_memory", {})
        if not isinstance(personal_memory_settings, dict):
            personal_memory_settings = {}
        configured_aliases = personal_memory_settings.get("name_aliases", {})
        self.personal_memory_aliases = (
            {
                str(source).strip(): str(target).strip()
                for source, target in configured_aliases.items()
                if str(source).strip() and str(target).strip()
            }
            if isinstance(configured_aliases, dict)
            else {}
        )
        configured_ignored_names = personal_memory_settings.get("ignored_names", [])
        self.personal_memory_ignored_names = (
            {str(name).strip() for name in configured_ignored_names if str(name).strip()}
            if isinstance(configured_ignored_names, list)
            else set()
        )
        configured_memory_path = Path(str(personal_memory_settings.get("path", "data/personal-memory.json")))
        if not configured_memory_path.is_absolute():
            configured_memory_path = self.config_path.parent / configured_memory_path
        self.personal_memory_store = PersonalMemoryStore(
            configured_memory_path,
            aliases=self.personal_memory_aliases,
            ignored_names=self.personal_memory_ignored_names,
        )
        self.personal_memory_learner = PersonalMemoryLearner(self.model_client, self.personal_memory_store)
        configured_episode_path = Path(
            str(personal_memory_settings.get("episodic_path", "data/episodic-memory.json"))
        )
        if not configured_episode_path.is_absolute():
            configured_episode_path = self.config_path.parent / configured_episode_path
        self.episodic_memory_store = EpisodicMemoryStore(
            configured_episode_path,
            aliases=self.personal_memory_aliases,
            ignored_names=self.personal_memory_ignored_names,
        )
        self.learning_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mybot-memory")
        self.ability_store = ExtensionAbilityStore(self.config_path.parent / "extensions")
        self.codex_thread_store = CodexThreadStore(self.config_path.parent / "data" / "codex" / "threads.json")
        attachment_settings = self.settings.get("attachments", {})
        if not isinstance(attachment_settings, dict):
            attachment_settings = {}
        configured_attachment_roots = attachment_settings.get("wechat_file_roots", [])
        if not isinstance(configured_attachment_roots, list):
            configured_attachment_roots = []
        self.attachment_store = ConversationAttachmentStore(
            self.config_path.parent / "data" / "attachments",
            WeChatAttachmentResolver(configured_attachment_roots),
        )
        vision_cache_settings = self.settings.get("vision_cache", {})
        if not isinstance(vision_cache_settings, dict):
            vision_cache_settings = {}
        try:
            perceptual_threshold = int(vision_cache_settings.get("perceptual_threshold", 4) or 4)
        except (TypeError, ValueError):
            perceptual_threshold = 4
        self.image_understanding_cache = ImageUnderstandingCache(
            self.config_path.parent / "data" / "image-understanding-cache.json",
            perceptual_threshold=perceptual_threshold,
        )
        self.reusable_task_reviewer = ReusableTaskReviewer(self.model_client)
        self.realtime_tool_executor = RealtimeToolExecutor()
        self.codex_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mybot-codex")
        self.ability_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mybot-ability")
        self.auto_chat_running = False
        self._auto_start_attempted = False
        self._message_cursor = ListenerMessageCursor()
        self._auto_chat_seen: set[str] = set()
        self._auto_chat_seen_order: deque[str] = deque(maxlen=2000)
        self._auto_chat_last_reply: dict[str, float] = {}
        self._auto_chat_pending: dict[str, int] = {}
        self._auto_chat_active_tasks: set[str] = set()
        self._auto_chat_queues: dict[str, deque] = {}
        self._auto_chat_session = 0
        self._listener_targets: set[str] = set()
        self._preview_snapshots: dict[str, str] = {}
        self._preview_poll_pending = False
        self._preview_backoff_until = 0.0
        self._preview_timeout_count = 0
        self._server_auto_recovery_in_progress = False
        self._server_auto_recovery_last_at = 0.0
        self._resume_auto_chat_after_reconnect = False
        self._preview_image_fetches: set[str] = set()
        self._preview_image_retries: dict[str, tuple[str, int, float]] = {}
        self._preview_image_completed: dict[str, str] = {}
        self._latest_incoming_media: dict[str, IncomingMessage] = {}
        self._auto_chat_sent_contents: dict[str, str] = {}
        self._preview_suppressed_until: dict[str, float] = {}
        self._auto_chat_groups: set[str] = set()
        self._pending_image_edits: dict[str, tuple[str, float]] = {}
        self._auto_reply_spans: dict[str, Any] = {}
        self._sticker_catalog_items: list[dict[str, Any]] = []
        self._sticker_selection_offsets: dict[str, int] = {}
        self._sticker_in_flight: dict[str, float] = {}
        self._sticker_last_sent: dict[str, float] = {}
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(5000)
        self._preview_timer.timeout.connect(self._poll_auto_chat_previews)
        self._global_hotkey_id = 0x4D42
        self._global_hotkey_registered = False
        self._pages = QStackedWidget()
        self._nav_buttons: list[QPushButton] = []
        self._test_queue: list[tuple[str, dict[str, Any]]] = []
        self._test_total = 0
        self._test_index = 0
        self._test_failed = 0
        self._test_span = None
        self._build_shell()
        self._build_pages()
        self._install_stop_shortcut()
        self._select_page(0)
        self._append_chat("系统", "已加载自动聊天、功能目录和快速测试模块。")
        if self._config_load_error:
            self._append_chat("配置", f"读取配置失败，已使用默认值：{self._config_load_error}")
        else:
            self._append_chat("配置", f"已读取明文配置：{self.config_path}")
        self._window_layout_ready = True
        QTimer.singleShot(0, self._restore_window_layout)
        QTimer.singleShot(350, self._connect)

    def _load_settings(self) -> tuple[dict[str, Any], str]:
        if not self.config_path.exists():
            return {}, ""
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("配置根节点必须是 JSON 对象")
            return data, ""
        except Exception as exc:
            return {}, str(exc)

    def _config_value(self, section: str, key: str, env_name: str, default: Any) -> Any:
        section_data = self.settings.get(section, {})
        if isinstance(section_data, dict) and key in section_data:
            return section_data[key]
        return os.environ.get(env_name, default) if env_name else default

    def _restore_window_layout(self) -> None:
        layout = normalize_window_layout(self.settings)
        target = QRect(layout["x"], layout["y"], layout["width"], layout["height"])
        screens = self.screen().virtualSiblings() if self.screen() else []
        if screens and not any(screen.availableGeometry().intersects(target) for screen in screens):
            available = screens[0].availableGeometry()
            layout["x"] = available.x() + max(0, (available.width() - layout["width"]) // 2)
            layout["y"] = available.y() + max(0, (available.height() - layout["height"]) // 2)
        if os.name == "nt":
            flags = 0x0004 | 0x0010  # SWP_NOZORDER | SWP_NOACTIVATE
            applied = ctypes.windll.user32.SetWindowPos(
                int(self.winId()),
                0,
                layout["x"],
                layout["y"],
                layout["width"],
                layout["height"],
                flags,
            )
            if applied:
                return
        self.setGeometry(target)

    def _current_window_layout(self) -> dict[str, int] | None:
        if self.isMinimized() or self.isMaximized():
            return None
        if os.name == "nt":
            rect = ctypes.wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(int(self.winId()), ctypes.byref(rect)):
                return {
                    "x": rect.left,
                    "y": rect.top,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                }
        rect = self.frameGeometry()
        return {"x": rect.x(), "y": rect.y(), "width": rect.width(), "height": rect.height()}

    def _schedule_window_layout_save(self) -> None:
        if self._window_layout_ready and self.isVisible() and not self.isMaximized():
            self._window_layout_timer.start()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._schedule_window_layout_save()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._schedule_window_layout_save()

    def _save_window_layout(self) -> None:
        layout = self._current_window_layout()
        if layout is None:
            return
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("配置根节点必须是 JSON 对象")
            else:
                data = dict(self.settings)
            data["window"] = layout
            temporary = self.config_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.config_path)
            self.settings = data
        except Exception as exc:
            self.statusBar().showMessage(f"窗口布局保存失败：{exc}", 5000)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._window_layout_timer.stop()
        self._auto_selection_save_timer.stop()
        if hasattr(self, "auto_chat_targets"):
            self._persist_auto_chat_selection()
        if self._window_layout_ready and self.isVisible():
            self._save_window_layout()
        if self._test_span is not None:
            operations.finish(self._test_span, success=False, error="应用退出，测试中止")
            self._test_span = None
        for span in self._auto_reply_spans.values():
            operations.finish(span, success=False, error="应用退出，自动回复中止")
        self._auto_reply_spans.clear()
        if self._global_hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._global_hotkey_id)
        if self.gateway.connected and self.account:
            try:
                self.gateway.call(self.account, "PauseMessageListener", "").result(timeout=3)
            except Exception:
                pass
        self.gateway.close()
        self.model_executor.shutdown(wait=False, cancel_futures=True)
        self.learning_executor.shutdown(wait=False, cancel_futures=True)
        self.codex_executor.shutdown(wait=False, cancel_futures=True)
        self.ability_executor.shutdown(wait=False, cancel_futures=True)
        event.accept()

    def _install_stop_shortcut(self) -> None:
        self.stop_auto_chat_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), self)
        self.stop_auto_chat_shortcut.setContext(Qt.ApplicationShortcut)
        self.stop_auto_chat_shortcut.activated.connect(self._stop_auto_chat_from_shortcut)
        if os.name == "nt":
            modifiers = 0x0002 | 0x0004 | 0x4000  # Ctrl + Shift + no-repeat
            self._global_hotkey_registered = bool(
                ctypes.windll.user32.RegisterHotKey(
                    int(self.winId()), self._global_hotkey_id, modifiers, ord("Q")
                )
            )
            self.stop_auto_chat_shortcut.setEnabled(not self._global_hotkey_registered)

    def nativeEvent(self, event_type, message):  # noqa: N802
        if os.name == "nt" and self._global_hotkey_registered:
            native_message = ctypes.wintypes.MSG.from_address(int(message))
            if native_message.message == 0x0312 and native_message.wParam == self._global_hotkey_id:
                QTimer.singleShot(0, self._stop_auto_chat_from_shortcut)
                return True, 0
        return super().nativeEvent(event_type, message)

    def _stop_auto_chat_from_shortcut(self) -> None:
        if self.auto_chat_running:
            self._stop_auto_chat()
        else:
            self._append_chat("自动聊天", "当前未运行")

    def _build_shell(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(225)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 18, 18)
        side.addWidget(label("MyBot", "brand"))
        side.addWidget(label("AI WECHAT OPERATOR", "muted"))
        side.addSpacing(18)
        for index, title in enumerate(("自动聊天", "人物记忆", "功能列表", "快捷能力", "测试模块")):
            nav = QPushButton(f"  {title}")
            nav.setObjectName("nav")
            nav.setCheckable(True)
            nav.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            self._nav_buttons.append(nav)
            side.addWidget(nav)
        side.addStretch()
        side.addWidget(label("连接状态", "muted"))
        self.sidebar_status = label("● 未连接", "muted")
        self.sidebar_status.setStyleSheet("color: #eab34c;")
        side.addWidget(self.sidebar_status)
        root_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(22, 12, 22, 12)
        top.addWidget(label("微信自动聊天", "pageTitle"))
        top.addStretch()
        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(150)
        self.account_combo.currentTextChanged.connect(self._account_changed)
        top.addWidget(self.account_combo)
        self.uri_input = QLineEdit(str(self._config_value("wechat", "websocket_url", "MYBOT_WEBSOCKET_URL", "ws://127.0.0.1:5177/ws")))
        self.uri_input.setMinimumWidth(245)
        top.addWidget(self.uri_input)
        self.connect_button = button("连接", self._connect, True)
        top.addWidget(self.connect_button)
        self.restart_server_button = button("重启 Server", self._restart_server)
        self.restart_server_button.setToolTip("停止并重新启动 WeChatAuto4_X WebSocket Server，然后自动重连")
        top.addWidget(self.restart_server_button)
        self.restart_app_button = button("重启软件", self._restart_application)
        self.restart_app_button.setToolTip("保存当前状态，关闭并重新启动 MyBot 2.0；Server 保持运行")
        top.addWidget(self.restart_app_button)
        content_layout.addWidget(topbar)
        content_layout.addWidget(self._pages, 1)
        root_layout.addWidget(content, 1)
        self.statusBar().showMessage("就绪")

    def _build_pages(self) -> None:
        self._pages.addWidget(self._auto_chat_page())
        self._pages.addWidget(self._personal_memory_page())
        self._pages.addWidget(self._catalog_page())
        self._pages.addWidget(self._abilities_page())
        self._pages.addWidget(self._test_page())

    def _auto_chat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)
        title_row = QHBoxLayout()
        title_row.addWidget(label("自动聊天", "pageTitle"))
        title_row.addWidget(label("选择会话后，AI 会接管消息并自动回复", "muted"), 0, Qt.AlignBottom)
        title_row.addStretch()
        self.auto_chat_status = label("未运行", "muted")
        title_row.addWidget(self.auto_chat_status)
        layout.addLayout(title_row)

        target_card, target_box = card("接管的会话")
        target_row = QHBoxLayout()
        self.auto_chat_targets = QListWidget()
        self.auto_chat_targets.setMinimumHeight(150)
        self.auto_chat_targets.itemChanged.connect(self._auto_chat_target_changed)
        target_row.addWidget(self.auto_chat_targets, 1)
        target_buttons = QVBoxLayout()
        target_buttons.addWidget(button("刷新会话", self._refresh_auto_chat_targets))
        target_buttons.addWidget(button("全选", self._select_all_auto_targets))
        target_buttons.addWidget(button("清空", self._clear_auto_targets))
        target_buttons.addStretch()
        target_row.addLayout(target_buttons)
        target_box.addLayout(target_row)
        layout.addWidget(target_card)

        model_card, model_box = card("模型与回复策略")
        model_grid = QGridLayout()
        self.model_provider = QComboBox()
        self.model_provider.addItems(["OpenAI 兼容接口", "Ollama 本地模型"])
        primary_provider = str(self._config_value("primary", "provider", "MYBOT_AI_PRIMARY_PROVIDER", "openai"))
        self.model_provider.setCurrentIndex(1 if primary_provider == "ollama" else 0)
        self.model_base_url = QLineEdit(str(self._config_value("primary", "base_url", "MYBOT_AI_PRIMARY_URL", "https://api.openai.com")))
        self.model_name = QComboBox()
        self.model_name.setEditable(True)
        self.model_name.addItem(str(self._config_value("primary", "model", "MYBOT_AI_PRIMARY_MODEL", "gpt-5.5")))
        self.model_api_key = QLineEdit(str(self._config_value("primary", "api_key", "MYBOT_AI_PRIMARY_KEY", "")))
        self.model_api_key.setPlaceholderText("明文保存在 config.json")
        self.model_system_prompt = QLineEdit(str(self._config_value("chat", "system_prompt", "", "你是一个自然、简洁、有帮助的微信聊天助手。")))
        self.reply_keyword = QLineEdit(str(self._config_value("chat", "reply_keyword", "", "")))
        self.reply_keyword.setPlaceholderText("留空：回复所有文本；填写：只回复包含关键词的消息")
        self.reply_cooldown = QSpinBox()
        self.reply_cooldown.setRange(1, 3600)
        try:
            cooldown_seconds = int(self._config_value("chat", "cooldown_seconds", "", 2))
        except (TypeError, ValueError):
            cooldown_seconds = 2
        self.reply_cooldown.setValue(cooldown_seconds)
        self.chat_concurrency = QSpinBox()
        self.chat_concurrency.setRange(1, 8)
        self.chat_concurrency.setValue(self._configured_chat_concurrency)
        self.chat_concurrency.setToolTip("同一个会话中可同时理解和生成回复的消息数量")
        self.model_backup_url = QLineEdit(str(self._config_value("backup", "base_url", "MYBOT_AI_BACKUP_URL", "https://api.openai.com")))
        self.model_backup_name = QLineEdit(str(self._config_value("backup", "model", "MYBOT_AI_BACKUP_MODEL", "gpt-5.6-sol")))
        self.model_backup_key = QLineEdit(str(self._config_value("backup", "api_key", "MYBOT_AI_BACKUP_KEY", "")))
        self.image_base_url = QLineEdit(str(self._config_value("image", "base_url", "MYBOT_AI_IMAGE_URL", "https://api.openai.com")))
        self.image_model_name = QLineEdit(str(self._config_value("image", "model", "MYBOT_AI_IMAGE_MODEL", "gpt-image-1.5")))
        self.image_api_key = QLineEdit(str(self._config_value("image", "api_key", "MYBOT_AI_IMAGE_KEY", "")))
        model_grid.addWidget(label("提供方", "muted"), 0, 0)
        model_grid.addWidget(self.model_provider, 0, 1)
        model_grid.addWidget(label("接口地址", "muted"), 0, 2)
        model_grid.addWidget(self.model_base_url, 0, 3)
        model_grid.addWidget(label("模型", "muted"), 1, 0)
        model_grid.addWidget(self.model_name, 1, 1)
        model_grid.addWidget(label("密钥", "muted"), 1, 2)
        model_grid.addWidget(self.model_api_key, 1, 3)
        model_grid.addWidget(label("人设", "muted"), 2, 0)
        model_grid.addWidget(self.model_system_prompt, 2, 1, 1, 3)
        model_grid.addWidget(label("触发关键词", "muted"), 3, 0)
        model_grid.addWidget(self.reply_keyword, 3, 1, 1, 2)
        model_grid.addWidget(label("冷却秒数", "muted"), 3, 3)
        model_grid.addWidget(self.reply_cooldown, 3, 4)
        model_grid.addWidget(label("单会话并行", "muted"), 3, 5)
        model_grid.addWidget(self.chat_concurrency, 3, 6)
        model_grid.addWidget(label("备用接口", "muted"), 4, 0)
        model_grid.addWidget(self.model_backup_url, 4, 1)
        model_grid.addWidget(label("备用模型", "muted"), 4, 2)
        model_grid.addWidget(self.model_backup_name, 4, 3)
        model_grid.addWidget(label("备用密钥", "muted"), 5, 0)
        model_grid.addWidget(self.model_backup_key, 5, 1, 1, 3)
        model_grid.addWidget(label("生图接口", "muted"), 6, 0)
        model_grid.addWidget(self.image_base_url, 6, 1)
        model_grid.addWidget(label("生图模型", "muted"), 6, 2)
        model_grid.addWidget(self.image_model_name, 6, 3)
        model_grid.addWidget(label("生图密钥", "muted"), 7, 0)
        model_grid.addWidget(self.image_api_key, 7, 1, 1, 3)
        model_box.addLayout(model_grid)
        memory_row = QHBoxLayout()
        self.personal_memory_enabled = QCheckBox("自动学习个人偏好")
        personal_memory_settings = self.settings.get("personal_memory", {})
        enabled = not isinstance(personal_memory_settings, dict) or bool(personal_memory_settings.get("enabled", True))
        self.personal_memory_enabled.setChecked(enabled)
        self.personal_memory_enabled.setToolTip(
            "成功回复后在后台提炼明确偏好和交流习惯；不保存完整聊天记录，不阻塞当前回复"
        )
        self.personal_memory_status = label("", "muted")
        self._update_personal_memory_status()
        memory_row.addWidget(self.personal_memory_enabled)
        memory_row.addWidget(self.personal_memory_status)
        memory_row.addStretch()
        model_box.addLayout(memory_row)
        codex_row = QHBoxLayout()
        self.codex_enabled = QCheckBox("复杂任务交给 Codex CLI")
        codex_settings = self.settings.get("codex", {})
        codex_enabled = isinstance(codex_settings, dict) and bool(codex_settings.get("enabled", True))
        self.codex_enabled.setChecked(codex_enabled)
        self.codex_enabled.setToolTip("代码、文件、调试和研究任务会先确认，再由 Codex CLI 异步完成")
        self.codex_status = label("", "muted")
        self._update_codex_status()
        codex_row.addWidget(self.codex_enabled)
        codex_row.addWidget(self.codex_status)
        codex_row.addStretch()
        model_box.addLayout(codex_row)
        model_actions = QHBoxLayout()
        model_actions.addWidget(button("保存配置", self._save_settings))
        model_actions.addWidget(button("编辑回复策略", self._edit_reply_policy))
        self.reply_policy_summary = label("", "muted")
        self._update_reply_policy_summary()
        model_actions.addWidget(self.reply_policy_summary)
        model_actions.addWidget(button("刷新模型", self._refresh_models))
        model_actions.addWidget(button("测试模型", self._test_model))
        model_actions.addWidget(button("测试生图", self._test_image))
        self.auto_chat_start = button("开始自动聊天", self._start_auto_chat, True)
        self.auto_chat_stop = button("停止自动聊天", self._stop_auto_chat)
        self.auto_chat_stop.setToolTip("停止自动聊天 (Ctrl+Shift+Q)")
        self._set_auto_chat_ui_state("stopped")
        model_actions.addStretch()
        model_actions.addWidget(self.auto_chat_start)
        model_actions.addWidget(self.auto_chat_stop)
        model_box.addLayout(model_actions)
        layout.addWidget(model_card)

        log_card, log_box = card("自动聊天日志")
        self.chat_view = QPlainTextEdit()
        self.chat_view.setReadOnly(True)
        log_box.addWidget(self.chat_view, 1)

        attachment_card, attachment_box = card("会话附件")
        self.attachment_list = QListWidget()
        self.attachment_list.setMinimumWidth(300)
        self.attachment_list.setWordWrap(True)
        self.attachment_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.attachment_list.itemDoubleClicked.connect(lambda _item: self._open_selected_attachment())
        attachment_box.addWidget(self.attachment_list, 1)
        attachment_actions = QHBoxLayout()
        attachment_actions.addWidget(button("查看原图/文件", self._open_selected_attachment, True))
        attachment_actions.addWidget(button("打开所在位置", self._open_selected_attachment_folder))
        attachment_actions.addWidget(button("刷新", self._refresh_attachment_list))
        attachment_box.addLayout(attachment_actions)

        content_row = QHBoxLayout()
        content_row.addWidget(log_card, 2)
        content_row.addWidget(attachment_card, 1)
        layout.addLayout(content_row, 1)
        QTimer.singleShot(0, self._refresh_attachment_list)
        return page

    def _personal_memory_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(label("人物记忆", "pageTitle"))
        header.addWidget(label("AI 从对话中整理的人物画像与互动记忆", "muted"), 0, Qt.AlignBottom)
        header.addStretch()
        self.memory_page_status = label("", "muted")
        header.addWidget(self.memory_page_status)
        header.addWidget(button("刷新记忆", self._refresh_personal_memory_page))
        layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        people_card, people_box = card("人物")
        people_card.setMinimumWidth(245)
        people_card.setMaximumWidth(340)
        self.memory_search = QLineEdit()
        self.memory_search.setPlaceholderText("搜索姓名、称呼或画像")
        self.memory_search.textChanged.connect(self._filter_personal_memory_people)
        people_box.addWidget(self.memory_search)
        self.memory_people = QListWidget()
        self.memory_people.setWordWrap(True)
        self.memory_people.currentItemChanged.connect(
            lambda _current, _previous: self._load_selected_personal_memory()
        )
        people_box.addWidget(self.memory_people, 1)
        splitter.addWidget(people_card)

        details = QTabWidget()
        profile_page = QWidget()
        profile_layout = QVBoxLayout(profile_page)
        profile_layout.setContentsMargins(16, 16, 16, 14)
        identity_row = QHBoxLayout()
        self.memory_person_name = label("未选择人物", "sectionTitle")
        self.memory_profile_meta = label("", "muted")
        identity_row.addWidget(self.memory_person_name)
        identity_row.addStretch()
        identity_row.addWidget(self.memory_profile_meta)
        profile_layout.addLayout(identity_row)

        identity_form = QFormLayout()
        self.memory_preferred_name = QLineEdit()
        self.memory_preferred_name.setPlaceholderText("对方希望圆子如何称呼")
        self.memory_summary = QPlainTextEdit()
        self.memory_summary.setPlaceholderText("AI 对这个人的整体了解")
        self.memory_summary.setMaximumHeight(90)
        self.memory_communication_style = QPlainTextEdit()
        self.memory_communication_style.setPlaceholderText("适合对方的交流语气和表达习惯")
        self.memory_communication_style.setMaximumHeight(76)
        identity_form.addRow("偏好称呼", self.memory_preferred_name)
        identity_form.addRow("人物总结", self.memory_summary)
        identity_form.addRow("沟通风格", self.memory_communication_style)
        profile_layout.addLayout(identity_form)

        memory_grid = QGridLayout()
        memory_grid.setHorizontalSpacing(14)
        memory_grid.setVerticalSpacing(6)
        self.memory_facts = QPlainTextEdit()
        self.memory_preferences = QPlainTextEdit()
        self.memory_current_context = QPlainTextEdit()
        self.memory_avoid_topics = QPlainTextEdit()
        editors = (
            (self.memory_facts, "每行一条已经确认的稳定事实"),
            (self.memory_preferences, "每行一条兴趣或明确偏好"),
            (self.memory_current_context, "每行一条近期状态或正在进行的事情"),
            (self.memory_avoid_topics, "每行一条不喜欢或应避免的内容"),
        )
        for editor, placeholder in editors:
            editor.setPlaceholderText(placeholder)
            editor.setMinimumHeight(110)
        memory_grid.addWidget(label("稳定事实", "muted"), 0, 0)
        memory_grid.addWidget(label("兴趣偏好", "muted"), 0, 1)
        memory_grid.addWidget(self.memory_facts, 1, 0)
        memory_grid.addWidget(self.memory_preferences, 1, 1)
        memory_grid.addWidget(label("近期状态", "muted"), 2, 0)
        memory_grid.addWidget(label("避免话题", "muted"), 2, 1)
        memory_grid.addWidget(self.memory_current_context, 3, 0)
        memory_grid.addWidget(self.memory_avoid_topics, 3, 1)
        memory_grid.setRowStretch(1, 1)
        memory_grid.setRowStretch(3, 1)
        profile_layout.addLayout(memory_grid, 1)

        profile_actions = QHBoxLayout()
        profile_actions.addStretch()
        self.memory_delete_button = button("删除人物", self._delete_selected_personal_memory)
        self.memory_save_button = button("保存修改", self._save_selected_personal_memory, True)
        profile_actions.addWidget(self.memory_delete_button)
        profile_actions.addWidget(self.memory_save_button)
        profile_layout.addLayout(profile_actions)
        details.addTab(profile_page, "人物画像")

        episode_page = QWidget()
        episode_layout = QVBoxLayout(episode_page)
        episode_layout.setContentsMargins(12, 12, 12, 12)
        self.memory_episode_table = QTableWidget(0, 4)
        self.memory_episode_table.setHorizontalHeaderLabels(("时间", "对方消息", "圆子回复", "重要度"))
        self.memory_episode_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.memory_episode_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.memory_episode_table.setAlternatingRowColors(True)
        self.memory_episode_table.setWordWrap(True)
        episode_header = self.memory_episode_table.horizontalHeader()
        episode_header.setStretchLastSection(False)
        episode_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        episode_header.setSectionResizeMode(1, QHeaderView.Stretch)
        episode_header.setSectionResizeMode(2, QHeaderView.Stretch)
        episode_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        episode_layout.addWidget(self.memory_episode_table, 1)
        episode_layout.addWidget(label("按时间倒序展示最近 100 条互动；重要度越高，越容易在相关话题中被调用。", "muted"))
        details.addTab(episode_page, "互动记忆")
        splitter.addWidget(details)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([275, 820])
        layout.addWidget(splitter, 1)

        self._memory_person_names: list[str] = []
        self._set_personal_memory_editor_enabled(False)
        QTimer.singleShot(0, self._refresh_personal_memory_page)
        return page

    def _selected_personal_memory_name(self) -> str:
        item = self.memory_people.currentItem()
        return str(item.data(Qt.UserRole) or "").strip() if item is not None else ""

    @staticmethod
    def _personal_memory_editor_items(editor: QPlainTextEdit) -> list[str]:
        return [line.strip() for line in editor.toPlainText().splitlines() if line.strip()]

    def _set_personal_memory_editor_enabled(self, enabled: bool) -> None:
        for widget in (
            self.memory_preferred_name,
            self.memory_summary,
            self.memory_communication_style,
            self.memory_facts,
            self.memory_preferences,
            self.memory_current_context,
            self.memory_avoid_topics,
            self.memory_save_button,
            self.memory_delete_button,
        ):
            widget.setEnabled(enabled)

    def _clear_personal_memory_editor(self) -> None:
        self.memory_person_name.setText("未选择人物")
        self.memory_profile_meta.setText("")
        self.memory_preferred_name.clear()
        self.memory_summary.clear()
        self.memory_communication_style.clear()
        self.memory_facts.clear()
        self.memory_preferences.clear()
        self.memory_current_context.clear()
        self.memory_avoid_topics.clear()
        self.memory_episode_table.setRowCount(0)
        self._set_personal_memory_editor_enabled(False)

    def _refresh_personal_memory_page(self, preferred_person: str = "") -> None:
        if not hasattr(self, "memory_people"):
            return
        selected = preferred_person.strip() or self._selected_personal_memory_name()
        span = operations.start("ui", "personal_memory_refresh", details={"selected": selected})
        try:
            self.personal_memory_store.reload()
            self.episodic_memory_store.reload()
            self._memory_person_names = sorted(
                set(self.personal_memory_store.names()) | set(self.episodic_memory_store.names())
            )
            self._filter_personal_memory_people(selected)
            self._update_personal_memory_status()
            operations.finish(
                span,
                success=True,
                result={
                    "person_count": len(self._memory_person_names),
                    "episode_count": self.episodic_memory_store.count(),
                },
            )
        except Exception as exc:
            operations.finish(span, success=False, error=exc)
            self.statusBar().showMessage(f"人物记忆刷新失败：{exc}", 5000)

    def _filter_personal_memory_people(self, preferred_person: str = "") -> None:
        if not hasattr(self, "memory_people"):
            return
        query = self.memory_search.text().strip().casefold()
        current = preferred_person.strip() or self._selected_personal_memory_name()
        self.memory_people.blockSignals(True)
        self.memory_people.clear()
        selected_row = -1
        for person in self._memory_person_names:
            profile = self.personal_memory_store.get(person)
            searchable = " ".join((
                person,
                profile.preferred_name,
                profile.summary,
                profile.communication_style,
                *profile.facts,
                *profile.preferences,
            )).casefold()
            if query and query not in searchable:
                continue
            text = person
            if profile.preferred_name and profile.preferred_name != person:
                text += f"\n称呼：{profile.preferred_name}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, person)
            self.memory_people.addItem(item)
            if person == current:
                selected_row = self.memory_people.count() - 1
        self.memory_people.blockSignals(False)
        if selected_row < 0 and self.memory_people.count():
            selected_row = 0
        if selected_row >= 0:
            self.memory_people.setCurrentRow(selected_row)
        else:
            self._clear_personal_memory_editor()

    def _load_selected_personal_memory(self) -> None:
        person = self._selected_personal_memory_name()
        if not person:
            self._clear_personal_memory_editor()
            return
        profile = self.personal_memory_store.get(person)
        episode_count = self.episodic_memory_store.count(person)
        self.memory_person_name.setText(person)
        metadata = [f"学习消息 {profile.message_count} 条", f"互动记忆 {episode_count} 条"]
        if profile.updated_at:
            metadata.append("更新于 " + profile.updated_at.replace("T", " ")[:19])
        self.memory_profile_meta.setText(" · ".join(metadata))
        self.memory_preferred_name.setText(profile.preferred_name)
        self.memory_summary.setPlainText(profile.summary)
        self.memory_communication_style.setPlainText(profile.communication_style)
        self.memory_facts.setPlainText("\n".join(profile.facts))
        self.memory_preferences.setPlainText("\n".join(profile.preferences))
        self.memory_current_context.setPlainText("\n".join(profile.current_context))
        self.memory_avoid_topics.setPlainText("\n".join(profile.avoid_topics))
        episodes = self.episodic_memory_store.recent(person, limit=100)
        self.memory_episode_table.setRowCount(len(episodes))
        for row, episode in enumerate(episodes):
            values = (
                episode.timestamp.replace("T", " ")[:19],
                episode.user_message,
                episode.assistant_reply,
                str(episode.importance),
            )
            for column, value in enumerate(values):
                self.memory_episode_table.setItem(row, column, QTableWidgetItem(value))
        self.memory_episode_table.resizeRowsToContents()
        self._set_personal_memory_editor_enabled(True)

    def _save_selected_personal_memory(self) -> None:
        person = self._selected_personal_memory_name()
        if not person:
            return
        existing = self.personal_memory_store.get(person)
        profile = PersonalProfile.from_mapping({
            "preferred_name": self.memory_preferred_name.text(),
            "summary": self.memory_summary.toPlainText(),
            "facts": self._personal_memory_editor_items(self.memory_facts),
            "preferences": self._personal_memory_editor_items(self.memory_preferences),
            "communication_style": self.memory_communication_style.toPlainText(),
            "current_context": self._personal_memory_editor_items(self.memory_current_context),
            "avoid_topics": self._personal_memory_editor_items(self.memory_avoid_topics),
            "message_count": existing.message_count,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        if not profile.configured:
            QMessageBox.warning(self, "人物画像为空", "至少保留一项人物信息；如需彻底清除，请使用“删除人物”。")
            return
        span = operations.start("ui", "personal_memory_save", details={"person": person})
        try:
            self.personal_memory_store.update(person, profile)
            operations.finish(span, success=True, result={"person": person})
            self.statusBar().showMessage(f"已保存 {person} 的人物画像", 4000)
            self._refresh_personal_memory_page(person)
        except Exception as exc:
            operations.finish(span, success=False, error=exc)
            QMessageBox.critical(self, "保存人物记忆失败", str(exc))

    def _delete_selected_personal_memory(self) -> None:
        person = self._selected_personal_memory_name()
        if not person:
            return
        episode_count = self.episodic_memory_store.count(person)
        message = f"确认删除“{person}”的人物画像和 {episode_count} 条互动记忆？\n删除后无法撤销。"
        if QMessageBox.question(self, "删除人物记忆", message) != QMessageBox.Yes:
            return
        span = operations.start("ui", "personal_memory_delete", details={"person": person})
        try:
            profile_deleted = self.personal_memory_store.delete(person)
            episodes_deleted = self.episodic_memory_store.delete_person(person)
            operations.finish(
                span,
                success=True,
                result={"profile_deleted": profile_deleted, "episodes_deleted": episodes_deleted},
            )
            self.statusBar().showMessage(f"已删除 {person} 的人物记忆", 4000)
            self._refresh_personal_memory_page()
        except Exception as exc:
            operations.finish(span, success=False, error=exc)
            QMessageBox.critical(self, "删除人物记忆失败", str(exc))

    def _catalog_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 20)
        row = QHBoxLayout()
        row.addWidget(label("功能列表", "pageTitle"))
        row.addWidget(label(f"统一登记 {len(TOOLS)} 个 AI 可调用功能", "muted"), 0, Qt.AlignBottom)
        row.addStretch()
        self.catalog_search = QLineEdit()
        self.catalog_search.setPlaceholderText("搜索功能、分类或说明")
        self.catalog_search.textChanged.connect(self._filter_catalog)
        row.addWidget(self.catalog_search)
        layout.addLayout(row)
        self.catalog_table = QTableWidget(len(TOOLS), 6)
        self.catalog_table.setHorizontalHeaderLabels(("函数", "功能", "分类", "说明", "风险", "测试"))
        self.catalog_table.setAlternatingRowColors(True)
        self.catalog_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.catalog_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.catalog_table.doubleClicked.connect(self._catalog_to_agent)
        for r, spec in enumerate(TOOLS):
            values = (spec.function, spec.name, spec.category, spec.description, spec.risk, self._test_label(spec.test_kind))
            for c, value in enumerate(values):
                self.catalog_table.setItem(r, c, QTableWidgetItem(value))
        self.catalog_table.horizontalHeader().setStretchLastSection(True)
        self.catalog_table.setColumnWidth(0, 220)
        self.catalog_table.setColumnWidth(1, 150)
        self.catalog_table.setColumnWidth(2, 90)
        self.catalog_table.setColumnWidth(3, 420)
        layout.addWidget(self.catalog_table, 1)
        layout.addWidget(label("双击任意功能可将其发送到 AI 执行台；复杂参数可使用：执行 FunctionName {JSON}", "muted"))
        return page

    def _abilities_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(label("快捷能力", "pageTitle"))
        header.addWidget(label("已验证技能包会在 Codex 调度前按触发词匹配", "muted"), 0, Qt.AlignBottom)
        header.addStretch()
        self.ability_summary = label("", "muted")
        header.addWidget(self.ability_summary)
        header.addWidget(button("刷新列表", self._refresh_ability_list))
        layout.addLayout(header)

        self.ability_table = QTableWidget(0, 7)
        self.ability_table.setHorizontalHeaderLabels(
            ("能力名称", "ID", "触发词", "说明", "技能包", "验证", "使用次数")
        )
        self.ability_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ability_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ability_table.setAlternatingRowColors(True)
        self.ability_table.setWordWrap(True)
        self.ability_table.horizontalHeader().setStretchLastSection(True)
        self.ability_table.setColumnWidth(0, 180)
        self.ability_table.setColumnWidth(1, 170)
        self.ability_table.setColumnWidth(2, 260)
        self.ability_table.setColumnWidth(3, 360)
        self.ability_table.setColumnWidth(4, 300)
        self.ability_table.setColumnWidth(5, 170)
        self.ability_table.setColumnWidth(6, 90)
        layout.addWidget(self.ability_table, 1)
        self._refresh_ability_list()
        return page

    def _refresh_ability_list(self) -> None:
        if not hasattr(self, "ability_table"):
            return
        abilities = self.ability_store.list_abilities()
        self.ability_table.setRowCount(0)
        for ability in abilities:
            row = self.ability_table.rowCount()
            self.ability_table.insertRow(row)
            triggers = ability.get("triggers", [])
            if not isinstance(triggers, list):
                triggers = [str(triggers)] if triggers else []
            values = (
                str(ability.get("name", "")),
                str(ability.get("id", "")),
                "、".join(str(value) for value in triggers if str(value).strip()),
                str(ability.get("description", "")),
                str(ability.get("skill") or ability.get("recipe") or ""),
                str(ability.get("validation", "未记录")),
                str(ability.get("usage_count", 0)),
            )
            for column, value in enumerate(values):
                self.ability_table.setItem(row, column, QTableWidgetItem(value))
        self.ability_summary.setText(f"已加载 {len(abilities)} 个技能包")

    def _test_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(label("测试模块", "pageTitle"))
        row.addWidget(label("按真实协议顺序执行，快速发现失效功能", "muted"), 0, Qt.AlignBottom)
        row.addStretch()
        layout.addLayout(row)

        config_card, config = card("测试参数")
        grid = QGridLayout()
        self.test_target = QComboBox()
        self.test_target.setEditable(True)
        self.test_target.lineEdit().setPlaceholderText("测试群聊或联系人")
        self.test_message = QLineEdit("[MyBot2.0] 自动化回归测试")
        bundled_icon = self.config_path.parent / "sdk" / "Images" / "icon.png"
        workspace_icon = self.config_path.parent.parent / "wechatautosdk" / "Images" / "icon.png"
        self.test_file = QLineEdit(str(bundled_icon if bundled_icon.is_file() else workspace_icon))
        grid.addWidget(label("目标会话", "muted"), 0, 0)
        grid.addWidget(self.test_target, 0, 1)
        grid.addWidget(label("测试文本", "muted"), 1, 0)
        grid.addWidget(self.test_message, 1, 1)
        grid.addWidget(label("测试图片/文件", "muted"), 2, 0)
        grid.addWidget(self.test_file, 2, 1)
        config.addLayout(grid)
        action_row = QHBoxLayout()
        action_row.addWidget(button("运行安全测试", self._run_safe_tests, True))
        action_row.addWidget(button("运行完整测试", self._run_full_tests))
        action_row.addWidget(button("扫描表情包", self._scan_all_stickers))
        action_row.addWidget(button("运行聊天闭环", self._run_auto_chat_loop_test))
        action_row.addWidget(button("刷新测试目标", self._refresh_test_targets))
        action_row.addStretch()
        config.addLayout(action_row)
        layout.addWidget(config_card)

        self.test_progress = QProgressBar()
        self.test_progress.setValue(0)
        layout.addWidget(self.test_progress)
        self.test_table = QTableWidget(0, 5)
        self.test_table.setHorizontalHeaderLabels(("功能", "状态", "耗时", "参数", "结果"))
        self.test_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.test_table.horizontalHeader().setStretchLastSection(True)
        self.test_table.setColumnWidth(0, 230)
        self.test_table.setColumnWidth(1, 72)
        self.test_table.setColumnWidth(2, 70)
        self.test_table.setColumnWidth(3, 140)
        layout.addWidget(self.test_table, 1)
        return page

    def _select_page(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        for i, nav in enumerate(self._nav_buttons):
            nav.setChecked(i == index)
        if index == 1 and hasattr(self, "memory_people"):
            self._refresh_personal_memory_page()

    def _connect(self) -> None:
        if self.gateway.connected:
            self._run_future(self.gateway.disconnect(), lambda _: self._set_connection(False, "已断开"))
            return
        if self._connect_in_progress:
            return
        self._connect_in_progress = True
        self.connect_button.setEnabled(False)
        self.statusBar().showMessage("正在连接 WebSocket Server…")
        self._run_future(self.gateway.connect(self.uri_input.text().strip()), self._connection_result)

    def _server_executable(self) -> Path:
        configured = self._config_value("server", "exe_path", "MYBOT_SERVER_EXE", "")
        if configured:
            return Path(str(configured)).expanduser().resolve()
        return (
            Path(__file__).resolve().parents[2]
            / "wechatautosdk"
            / "WeChatAuto4_X"
            / "WebSocketServer"
            / "Server"
            / "bin"
            / "Debug"
            / "net10.0-windows"
            / "Server.exe"
        )

    def _restart_server(self) -> None:
        if not self.restart_server_button.isEnabled():
            self._server_auto_recovery_in_progress = False
            return
        self._resume_auto_chat_after_reconnect = (
            self._resume_auto_chat_after_reconnect or self.auto_chat_running
        )
        executable = self._server_executable()
        if not executable.is_file():
            self._server_auto_recovery_in_progress = False
            QMessageBox.warning(self, "Server 不存在", f"找不到 Server.exe：\n{executable}")
            return
        self.restart_server_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.statusBar().showMessage("正在重启 WebSocket Server…")
        self._append_chat("系统", f"正在重启 Server：{executable}")

        if self.auto_chat_running and self.gateway.connected and self.account:
            try:
                self.gateway.call(self.account, "PauseMessageListener", "").result(timeout=3)
            except Exception as exc:
                self._append_chat("自动聊天", f"暂停监听失败，继续重启：{exc}")
            self.auto_chat_running = False
            self._auto_chat_session += 1
            self._preview_timer.stop()
            self._auto_chat_pending.clear()
            self._auto_chat_active_tasks.clear()
            self._auto_chat_queues.clear()
            self._set_auto_chat_ui_state("stopped")
        try:
            self.gateway.disconnect().result(timeout=3)
        except Exception:
            pass
        self._set_connection(False, "Server 重启中")
        future = self.model_executor.submit(
            self._restart_server_worker,
            executable,
            self.uri_input.text().strip(),
        )

        def finished(result: GatewayResult) -> None:
            self.restart_server_button.setEnabled(True)
            self.connect_button.setEnabled(True)
            if not result.ok:
                self._server_auto_recovery_in_progress = False
                self._append_chat("系统", f"Server 重启失败：{result.error}")
                self.statusBar().showMessage("Server 重启失败", 6000)
                return
            self._append_chat("系统", f"Server 已启动，PID={result.value['pid']}，正在自动重连")
            self.statusBar().showMessage("Server 已启动，正在重连…", 5000)
            QTimer.singleShot(350, self._connect)

        self._run_future(future, finished)

    def _recover_stalled_server(self, error: str) -> None:
        now = time.monotonic()
        if self._server_auto_recovery_in_progress:
            return
        if now - self._server_auto_recovery_last_at < 60.0:
            return
        self._server_auto_recovery_in_progress = True
        self._server_auto_recovery_last_at = now
        self._resume_auto_chat_after_reconnect = self.auto_chat_running
        operations.event("workflow", "server_stall_auto_recovery", {
            "error": error,
            "preview_timeout_count": self._preview_timeout_count,
        })
        self._append_chat("自动聊天", "连续读取会话超时，正在自动重启 Server 并恢复接管")
        QTimer.singleShot(0, self._restart_server)

    @staticmethod
    def _restart_application_helper(process_id: int, app_root: Path) -> list[str]:
        escaped_root = str(app_root.resolve()).replace("'", "''")
        escaped_log = str((app_root.resolve() / "logs" / "restart-helper.log")).replace("'", "''")
        script = (
            "$ErrorActionPreference='Stop'; "
            f"$log='{escaped_log}'; "
            "try { "
            "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null; "
            f"Add-Content -LiteralPath $log -Value ('{{0:o}} waiting for PID {int(process_id)}' -f [DateTime]::Now); "
            f"while (Get-Process -Id {int(process_id)} -ErrorAction SilentlyContinue) "
            "{ Start-Sleep -Milliseconds 200 }; "
            "Start-Sleep -Milliseconds 300; "
            f"$child=Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d','/c','run.cmd') "
            f"-WorkingDirectory '{escaped_root}' -WindowStyle Hidden -PassThru; "
            "Add-Content -LiteralPath $log -Value ('{0:o} launched run.cmd, PID {1}' -f [DateTime]::Now,$child.Id) "
            "} catch { "
            "Add-Content -LiteralPath $log -Value ('{0:o} restart failed: {1}' -f [DateTime]::Now,$_.Exception.Message); "
            "exit 1 }"
        )
        return [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            script,
        ]

    def _restart_application(self) -> None:
        if not self.restart_app_button.isEnabled():
            return
        app_root = self.config_path.parent
        span = operations.start(
            "ui",
            "application_restart",
            details={"process_id": os.getpid(), "app_root": str(app_root)},
        )
        self.restart_app_button.setEnabled(False)
        self._auto_selection_save_timer.stop()
        self._persist_auto_chat_selection()
        self._save_window_layout()
        try:
            subprocess.Popen(
                self._restart_application_helper(os.getpid(), app_root),
                cwd=str(app_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            operations.finish(span, success=True, result={"restart_scheduled": True})
            self.statusBar().showMessage("正在重启 MyBot 2.0…")
            QTimer.singleShot(0, self.close)
        except Exception as exc:
            self.restart_app_button.setEnabled(True)
            operations.finish(span, success=False, error=exc)
            QMessageBox.critical(self, "重启软件失败", str(exc))

    @staticmethod
    def _server_pids(executable: Path) -> list[int]:
        if os.name != "nt":
            return []
        escaped = str(executable).replace("'", "''")
        script = (
            "$target='" + escaped + "'; "
            "Get-CimInstance Win32_Process -Filter \"Name='Server.exe'\" | "
            "Where-Object { $_.ExecutablePath -eq $target } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        pids: list[int] = []
        for line in completed.stdout.splitlines():
            try:
                pids.append(int(line.strip()))
            except ValueError:
                continue
        return pids

    @classmethod
    def _restart_server_worker(cls, executable: Path, websocket_url: str) -> GatewayResult:
        span = operations.start(
            "ui",
            "server_restart",
            details={"executable": str(executable), "websocket_url": websocket_url},
        )
        try:
            for pid in cls._server_pids(executable):
                stopped = subprocess.run(
                    ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                if stopped.returncode != 0:
                    detail = (stopped.stderr or stopped.stdout).strip()
                    raise RuntimeError(f"无法停止旧 Server (PID {pid})：{detail or '权限不足'}")
            parsed = urlparse(websocket_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 5177
            server_environment = os.environ.copy()
            server_environment["ASPNETCORE_URLS"] = f"http://{host}:{port}"
            process = subprocess.Popen(
                [str(executable)],
                cwd=str(executable.parent),
                env=server_environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Server 启动后立即退出，退出码 {process.returncode}")
                try:
                    with socket.create_connection((host, port), timeout=0.4):
                        result = {"pid": process.pid, "path": str(executable)}
                        operations.finish(
                            span,
                            success=True,
                            result=result,
                            details={"host": host, "port": port},
                        )
                        return GatewayResult(True, result)
                except OSError:
                    time.sleep(0.25)
            raise TimeoutError(f"等待 Server 端口 {host}:{port} 超时")
        except Exception as exc:
            operations.finish(span, success=False, error=exc)
            return GatewayResult(False, error=str(exc))

    def _connection_result(self, result: GatewayResult) -> None:
        self._connect_in_progress = False
        self.connect_button.setEnabled(True)
        if not result.ok:
            message = result.error or "连接失败"
            self._set_connection(False, message)
            self._append_chat("系统", f"连接失败，3 秒后重试：{message}")
            QTimer.singleShot(
                3000,
                lambda: None if self.gateway.connected else self._connect(),
            )
            return
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        self.account_combo.addItems(self.gateway.clients)
        self.account_combo.blockSignals(False)
        self.account = self.gateway.clients[0] if self.gateway.clients else ""
        self._set_connection(True, f"已连接 {self.gateway.uri}")
        self._append_chat("系统", f"已连接测试账号：{self.account}")
        should_resume_auto_chat = (
            self.auto_chat_running or self._resume_auto_chat_after_reconnect
        )
        self._resume_auto_chat_after_reconnect = False
        self._server_auto_recovery_in_progress = False
        self._preview_timeout_count = 0

        def listener_reset(_result: GatewayResult) -> None:
            self._listener_targets.clear()
            self._refresh_auto_chat_targets()
            if should_resume_auto_chat:
                self._append_chat("自动聊天", "连接已恢复，正在重新接管原会话")
                self._start_auto_chat(preserve_session=True)

        # A previous frontend can disappear while the SDK listener remains
        # alive in the long-running server. Always take ownership from a
        # paused baseline before reading conversations or starting a new run.
        self._run_future(
            self.gateway.call(self.account, "PauseMessageListener", ""),
            listener_reset,
        )

    def _set_connection(self, connected: bool, message: str) -> None:
        self.gateway.connected = connected
        self.connect_button.setText("断开" if connected else "连接")
        self.sidebar_status.setText("● 已连接" if connected else "● 未连接")
        self.sidebar_status.setStyleSheet("color: #58d69b;" if connected else "color: #eab34c;")
        self.statusBar().showMessage(message, 5000)

    def _account_changed(self, account: str) -> None:
        if account:
            self.account = account

    def _run_future(self, future, callback: Callable[[GatewayResult], None]) -> None:
        def poll() -> None:
            if future.done():
                try:
                    callback(future.result())
                except Exception as exc:
                    self.statusBar().showMessage(str(exc), 6000)
                return
            QTimer.singleShot(50, poll)
        poll()

    def _append_chat(self, role: str, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{stamp}] {role}\n{text}\n"
        self.chat_view.appendPlainText(entry)
        try:
            with self.runtime_log_path.open("a", encoding="utf-8") as stream:
                stream.write(entry + "\n")
        except OSError:
            pass

    def _refresh_attachment_list(self) -> None:
        widget = getattr(self, "attachment_list", None)
        if widget is None:
            return
        selected_path = ""
        if widget.currentItem() is not None:
            selected_path = str(widget.currentItem().data(Qt.UserRole) or "")
        widget.clear()
        targets = self._selected_auto_chat_targets() if hasattr(self, "auto_chat_targets") else set()
        for conversation in sorted(targets):
            for attachment in reversed(self.attachment_store.all(conversation)):
                size = f"{attachment.size / 1024:.1f} KB" if attachment.size < 1024 * 1024 else f"{attachment.size / 1024 / 1024:.2f} MB"
                item = QListWidgetItem(
                    f"{conversation}\n{attachment.name} · {attachment_type_label(attachment)} · {size}"
                )
                item.setData(Qt.UserRole, attachment.path)
                item.setToolTip(
                    f"类型：{attachment.mime_type or attachment_type_label(attachment)}\n"
                    f"接收时间：{attachment.received_at or '未知'}\n"
                    f"SHA-256：{attachment.sha256}\n"
                    f"位置：{attachment.path}"
                )
                widget.addItem(item)
                if attachment.path == selected_path:
                    widget.setCurrentItem(item)

    def _selected_attachment_path(self) -> Path | None:
        widget = getattr(self, "attachment_list", None)
        item = widget.currentItem() if widget is not None else None
        if item is None:
            self.statusBar().showMessage("请先选择一个会话附件", 4000)
            return None
        path = Path(str(item.data(Qt.UserRole) or ""))
        if not path.is_file():
            self.statusBar().showMessage("附件原文件已不存在", 5000)
            return None
        return path

    def _open_selected_attachment(self) -> None:
        path = self._selected_attachment_path()
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            operations.event("attachment", "open_original", {"path": str(path)})

    def _open_selected_attachment_folder(self) -> None:
        path = self._selected_attachment_path()
        if path is not None:
            subprocess.Popen(["explorer.exe", f"/select,{path}"])
            operations.event("attachment", "open_containing_folder", {"path": str(path)})

    def _gateway_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "connection_error":
            self._append_chat("系统", f"连接异常：{event.get('data', '')}")
            self._set_connection(False, "连接异常，正在重试")
            QTimer.singleShot(
                1500,
                lambda: None if self.gateway.connected else self._connect(),
            )
        elif event.get("type") == "echo":
            self._handle_auto_chat_event(event)
            if not parse_listener_event(event.get("data", ""), self_names={self.account}):
                self._append_chat("监听", self._format_value(event.get("data", "")))

    @staticmethod
    def _format_value(value: Any, limit: int = 1200) -> str:
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        return text if len(text) <= limit else text[:limit] + "…"

    @staticmethod
    def _test_label(kind: str) -> str:
        return {"safe": "自动", "configured": "需参数", "manual": "人工确认"}.get(kind, kind)

    def _filter_catalog(self, query: str) -> None:
        query = query.strip().lower()
        for row in range(self.catalog_table.rowCount()):
            values = [self.catalog_table.item(row, col).text().lower() for col in range(self.catalog_table.columnCount())]
            self.catalog_table.setRowHidden(row, bool(query) and not any(query in value for value in values))

    def _catalog_to_agent(self) -> None:
        row = self.catalog_table.currentRow()
        if row < 0:
            return
        function = self.catalog_table.item(row, 0).text()
        self._select_page(0)
        self._append_chat("功能列表", f"已选中 {function}。自动聊天只负责消息接管；该功能可在测试模块或 SDK 中单独验证。")

    def _refresh_auto_chat_targets(self) -> None:
        if not self.gateway.connected:
            return

        def loaded(result: GatewayResult) -> None:
            if not result.ok or not isinstance(result.value, list):
                self._append_chat("自动聊天", f"读取会话失败：{result.error}")
                return
            names = [str(item).strip() for item in result.value if str(item).strip()]
            checked = self._selected_auto_chat_targets()
            if not self._auto_selection_restored:
                checked.update(self._configured_auto_chat_targets(set(names)))
                self._auto_selection_restored = True
            startup_targets = self._consume_auto_start_targets(set(names))
            checked.update(startup_targets)
            self._loading_auto_chat_targets = True
            try:
                self.auto_chat_targets.clear()
                for name in names:
                    item = QListWidgetItem(name, self.auto_chat_targets)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if name in checked else Qt.Unchecked)
            finally:
                self._loading_auto_chat_targets = False
            self._append_chat("自动聊天", f"已加载 {self.auto_chat_targets.count()} 个群聊/私聊")
            self._refresh_attachment_list()
            self._refresh_test_targets()
            if startup_targets and not self.auto_chat_running:
                self._append_chat("自动聊天", "启动时自动锁定：" + "、".join(sorted(startup_targets)))
                operations.event("workflow", "auto_chat_startup_lock", {
                    "account": self.account,
                    "targets": sorted(startup_targets),
                })
                QTimer.singleShot(0, self._start_auto_chat)

            def groups_loaded(group_result: GatewayResult) -> None:
                if group_result.ok and isinstance(group_result.value, list):
                    self._auto_chat_groups = {str(name).strip() for name in group_result.value if str(name).strip()}

            self._run_future(self.gateway.call(self.account, "GetAllChatGroups", ""), groups_loaded)

        self._run_future(self.gateway.call(self.account, "GetAllConversations", ""), loaded)

    def _consume_auto_start_targets(self, available: set[str]) -> set[str]:
        if self._auto_start_attempted:
            return set()
        self._auto_start_attempted = True
        chat_settings = self.settings.get("chat", {})
        if not isinstance(chat_settings, dict) or not bool(chat_settings.get("auto_start_enabled", False)):
            return set()
        return MainWindow._configured_auto_chat_targets(self, available)

    def _configured_auto_chat_targets(self, available: set[str]) -> set[str]:
        chat_settings = self.settings.get("chat", {})
        if not isinstance(chat_settings, dict):
            return set()
        configured = chat_settings.get("auto_start_targets", [])
        if not isinstance(configured, list):
            return set()
        targets = {str(value).strip() for value in configured if str(value).strip()}
        return targets & available

    def _selected_auto_chat_targets(self) -> set[str]:
        return {
            self.auto_chat_targets.item(index).text()
            for index in range(self.auto_chat_targets.count())
            if self.auto_chat_targets.item(index).checkState() == Qt.Checked
        }

    def _auto_chat_target_changed(self, _item: QListWidgetItem) -> None:
        self._refresh_attachment_list()
        if not self._loading_auto_chat_targets:
            self._auto_selection_save_timer.start()

    def _persist_auto_chat_selection(self) -> None:
        targets = sorted(self._selected_auto_chat_targets())
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("配置根节点必须是 JSON 对象")
            else:
                data = dict(self.settings)
            existing_chat = data.get("chat", {})
            chat_settings = dict(existing_chat) if isinstance(existing_chat, dict) else {}
            if chat_settings.get("auto_start_targets") == targets:
                return
            chat_settings["auto_start_targets"] = targets
            data["chat"] = chat_settings
            temporary = self.config_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.config_path)
            self.settings = data
            operations.event("ui", "auto_chat_selection_saved", {"targets": targets})
        except Exception as exc:
            operations.event("ui", "auto_chat_selection_save_failed", {"error": str(exc)})
            self.statusBar().showMessage(f"接管会话保存失败：{exc}", 5000)

    def _select_all_auto_targets(self) -> None:
        for index in range(self.auto_chat_targets.count()):
            self.auto_chat_targets.item(index).setCheckState(Qt.Checked)

    def _clear_auto_targets(self) -> None:
        for index in range(self.auto_chat_targets.count()):
            self.auto_chat_targets.item(index).setCheckState(Qt.Unchecked)

    def _save_settings(self) -> None:
        span = operations.start("ui", "save_settings", details={"path": str(self.config_path)})
        existing_voice = self.settings.get("voice", {})
        existing_server = self.settings.get("server", {})
        existing_window = self._current_window_layout() or self.settings.get("window", {})
        existing_chat = self.settings.get("chat", {})
        chat_settings = dict(existing_chat) if isinstance(existing_chat, dict) else {}
        chat_settings.update({
            "system_prompt": self.model_system_prompt.text().strip(),
            "reply_keyword": self.reply_keyword.text().strip(),
            "cooldown_seconds": self.reply_cooldown.value(),
            "max_concurrency": self.chat_concurrency.value(),
            "auto_start_targets": sorted(self._selected_auto_chat_targets()),
            **self._reply_policy.to_mapping(),
        })
        data = dict(self.settings)
        data.update({
            "wechat": {
                "websocket_url": self.uri_input.text().strip(),
            },
            "server": existing_server if isinstance(existing_server, dict) else {},
            "window": existing_window if isinstance(existing_window, dict) else {},
            "primary": {
                "provider": "ollama" if self.model_provider.currentIndex() == 1 else "openai",
                "base_url": self.model_base_url.text().strip(),
                "model": self.model_name.currentText().strip(),
                "api_key": self.model_api_key.text().strip(),
            },
            "backup": {
                "provider": "openai",
                "base_url": self.model_backup_url.text().strip(),
                "model": self.model_backup_name.text().strip(),
                "api_key": self.model_backup_key.text().strip(),
            },
            "image": {
                "provider": "openai",
                "base_url": self.image_base_url.text().strip(),
                "model": self.image_model_name.text().strip(),
                "api_key": self.image_api_key.text().strip(),
            },
            "chat": chat_settings,
            "personal_memory": {
                "enabled": self.personal_memory_enabled.isChecked(),
                "path": str(self.personal_memory_store.path),
                "episodic_path": str(self.episodic_memory_store.path),
                "name_aliases": dict(sorted(self.personal_memory_aliases.items())),
                "ignored_names": sorted(self.personal_memory_ignored_names),
            },
            "codex": {
                **(self.settings.get("codex", {}) if isinstance(self.settings.get("codex", {}), dict) else {}),
                "enabled": self.codex_enabled.isChecked(),
            },
            "voice": existing_voice if isinstance(existing_voice, dict) else {},
        })
        try:
            self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.settings = data
            self._append_chat("配置", f"已保存明文配置：{self.config_path}")
            self.statusBar().showMessage("配置已保存", 5000)
            operations.finish(span, success=True, result={"path": str(self.config_path)})
        except Exception as exc:
            operations.finish(span, success=False, error=exc)
            QMessageBox.critical(self, "保存配置失败", str(exc))

    def _update_reply_policy_summary(self) -> None:
        contacts = len(self._reply_policy.contact_profiles)
        conversations = len(self._reply_policy.conversation_profiles)
        self.reply_policy_summary.setText(
            f"AI：{self._reply_policy.ai_name} · 专属：{contacts} 联系人 / {conversations} 会话"
        )

    def _update_personal_memory_status(self, suffix: str = "") -> None:
        text = f"已理解 {self.personal_memory_store.count()} 人"
        self.personal_memory_status.setText(f"{text} · {suffix}" if suffix else text)
        if hasattr(self, "memory_page_status"):
            page_text = (
                f"{self.personal_memory_store.count()} 人 · "
                f"{self.episodic_memory_store.count()} 条互动"
            )
            self.memory_page_status.setText(f"{page_text} · {suffix}" if suffix else page_text)

    def _update_codex_status(self, suffix: str = "") -> None:
        text = f"快捷能力 {self.ability_store.count()} 个"
        self.codex_status.setText(f"{text} · {suffix}" if suffix else text)

    def _codex_runtime_config(self) -> CodexRuntimeConfig:
        settings = self.settings.get("codex", {})
        if not isinstance(settings, dict):
            settings = {}
        root = self.config_path.parent
        executable = Path(str(settings.get("executable", "tools/codex/codex-x86_64-pc-windows-msvc.exe")))
        proxy = Path(str(settings.get("proxy_executable", "tools/codex/codex-responses-api-proxy-x86_64-pc-windows-msvc.exe")))
        if not executable.is_absolute():
            executable = root / executable
        if not proxy.is_absolute():
            proxy = root / proxy
        try:
            timeout = max(30, int(settings.get("timeout_seconds", 900)))
        except (TypeError, ValueError):
            timeout = 900
        return CodexRuntimeConfig(
            executable=executable.resolve(),
            proxy_executable=proxy.resolve(),
            project_root=root.resolve(),
            base_url=self.model_base_url.text().strip(),
            api_key=self.model_api_key.text().strip(),
            model=self.model_name.currentText().strip(),
            timeout_seconds=timeout,
        )

    def _codex_runner(self) -> CodexCliRunner:
        return CodexCliRunner(self._codex_runtime_config(), self.ability_store, self.codex_thread_store)

    def _edit_reply_policy(self) -> None:
        targets = [
            self.auto_chat_targets.item(index).text()
            for index in range(self.auto_chat_targets.count())
        ]
        dialog = ReplyPolicyDialog(self._reply_policy, targets, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._reply_policy = dialog.policy()
        self._update_reply_policy_summary()
        operations.event("ui", "reply_policy_updated", {
            "ai_name": self._reply_policy.ai_name,
            "contact_profile_count": len(self._reply_policy.contact_profiles),
            "conversation_profile_count": len(self._reply_policy.conversation_profiles),
            "boundary_count": len(self._reply_policy.boundaries),
        })
        self._save_settings()

    def _model_config(self) -> ModelConfig:
        provider = "ollama" if self.model_provider.currentIndex() == 1 else "openai"
        return ModelConfig(
            provider=provider,
            base_url=self.model_base_url.text().strip(),
            model=self.model_name.currentText().strip(),
            api_key=self.model_api_key.text().strip(),
            system_prompt=self.model_system_prompt.text().strip(),
        )

    def _backup_model_config(self) -> ModelConfig | None:
        url = self.model_backup_url.text().strip()
        model = self.model_backup_name.text().strip()
        if not url or not model:
            return None
        return ModelConfig(
            provider="openai",
            base_url=url,
            model=model,
            api_key=self.model_backup_key.text().strip(),
            system_prompt=self.model_system_prompt.text().strip(),
        )

    def _auto_chat_model_timeout(self) -> int:
        chat_settings = self.settings.get("chat", {})
        if not isinstance(chat_settings, dict):
            chat_settings = {}
        try:
            configured = int(chat_settings.get("auto_chat_timeout_seconds", 25))
        except (TypeError, ValueError):
            configured = 25
        return max(10, min(60, configured))

    def _image_config(self) -> ImageConfig:
        return ImageConfig(
            base_url=self.image_base_url.text().strip(),
            model=self.image_model_name.text().strip(),
            api_key=self.image_api_key.text().strip(),
        )

    def _refresh_models(self) -> None:
        config = self._model_config()
        self._append_chat("自动聊天", "正在读取模型列表…")
        future = self.model_executor.submit(self.model_client.list_models, config)

        def poll() -> None:
            if not future.done():
                QTimer.singleShot(100, poll)
                return
            try:
                models = future.result()
                self.model_name.clear()
                self.model_name.addItems(models)
                self._append_chat("自动聊天", f"可用模型：{', '.join(models) or '未发现模型'}")
            except Exception as exc:
                self._append_chat("自动聊天", f"读取模型失败：{exc}")
        poll()

    def _test_model(self) -> None:
        config = self._model_config()
        backup = self._backup_model_config()
        future = self.model_executor.submit(
            self.model_client.generate_with_fallback,
            config,
            backup,
            [{"role": "user", "content": "只回复：模型连接正常"}],
        )

        def poll() -> None:
            if not future.done():
                QTimer.singleShot(100, poll)
                return
            try:
                self._append_chat("自动聊天", f"模型测试成功：{future.result()}")
            except Exception as exc:
                self._append_chat("自动聊天", f"模型测试失败：{exc}")
        poll()

    def _test_image(self) -> None:
        config = self._image_config()
        self._append_chat("自动聊天", f"正在测试生图接口（{config.model}）…")
        future = self.model_executor.submit(self.model_client.generate_image, config, "一张简洁的彩色几何测试图")

        def poll() -> None:
            if not future.done():
                QTimer.singleShot(100, poll)
                return
            try:
                path = future.result()
                self._append_chat("自动聊天", f"生图测试成功，文件已保存：{path}")
            except Exception as exc:
                self._append_chat("自动聊天", f"生图测试失败：{exc}")
        poll()

    def _set_auto_chat_ui_state(self, state: str, target_count: int = 0, message: str = "") -> None:
        start_styles = {
            "stopped": """
                QPushButton { background: #2f6fed; color: #ffffff; border: 1px solid #4c82ed;
                              border-radius: 6px; padding: 7px 15px; font-weight: 600; }
                QPushButton:hover { background: #3b7af0; }
            """,
            "starting": """
                QPushButton:disabled { background: #7a5b19; color: #ffe7aa; border: 1px solid #a87b20;
                                       border-radius: 6px; padding: 7px 15px; font-weight: 600; }
            """,
            "running": """
                QPushButton:disabled { background: #176342; color: #d6ffeb; border: 1px solid #2b9b6b;
                                       border-radius: 6px; padding: 7px 15px; font-weight: 600; }
            """,
            "stopping": """
                QPushButton:disabled { background: #633036; color: #ffd9dc; border: 1px solid #a44b55;
                                       border-radius: 6px; padding: 7px 15px; font-weight: 600; }
            """,
            "error": """
                QPushButton { background: #2f6fed; color: #ffffff; border: 1px solid #4c82ed;
                              border-radius: 6px; padding: 7px 15px; font-weight: 600; }
                QPushButton:hover { background: #3b7af0; }
            """,
        }
        status_texts = {
            "stopped": "● 未运行",
            "starting": "● 正在连接监听...",
            "running": f"● 运行中 · {target_count} 个会话",
            "stopping": "● 正在停止...",
            "error": "● 启动失败",
        }
        status_colors = {
            "stopped": "#8b9aac",
            "starting": "#eab34c",
            "running": "#58d69b",
            "stopping": "#eab34c",
            "error": "#ff747f",
        }
        if state not in status_texts:
            raise ValueError(f"Unknown auto-chat UI state: {state}")

        self.auto_chat_start.setText({
            "stopped": "开始自动聊天",
            "starting": "正在启动...",
            "running": "自动聊天运行中",
            "stopping": "自动聊天运行中",
            "error": "重新开始自动聊天",
        }[state])
        self.auto_chat_stop.setText("正在停止..." if state == "stopping" else "停止自动聊天")
        self.auto_chat_start.setEnabled(state in {"stopped", "error"})
        self.auto_chat_stop.setEnabled(state == "running")
        self.auto_chat_start.setStyleSheet(start_styles[state])
        self.auto_chat_stop.setStyleSheet("""
            QPushButton { background: #8f2f3a; color: #ffffff; border: 1px solid #c34c5a;
                          border-radius: 6px; padding: 7px 15px; font-weight: 600; }
            QPushButton:hover { background: #a53a47; }
            QPushButton:disabled { background: #252f3b; color: #697789; border-color: #354253; }
        """)
        self.auto_chat_status.setText(status_texts[state])
        self.auto_chat_status.setStyleSheet(f"color: {status_colors[state]}; font-weight: 600;")
        self.auto_chat_status.setToolTip(message if state == "error" else "")

    def _start_auto_chat(self, *, preserve_session: bool = False) -> None:
        targets = set(self._selected_auto_chat_targets())
        self._auto_selection_save_timer.stop()
        self._persist_auto_chat_selection()
        config = self._model_config()
        span = operations.start(
            "workflow",
            "auto_chat_start",
            details={
                "account": self.account,
                "targets": sorted(targets),
                "model": config.model,
                "preserve_session": preserve_session,
            },
        )
        if not targets:
            operations.finish(span, success=False, error="未选择会话")
            QMessageBox.warning(self, "未选择会话", "请至少勾选一个群聊或私聊。")
            return
        if not config.model:
            operations.finish(span, success=False, error="未选择模型")
            QMessageBox.warning(self, "未选择模型", "请填写模型名称后再开始。")
            return
        if not self.gateway.connected:
            operations.finish(span, success=False, error="WebSocket Server 未连接")
            QMessageBox.warning(self, "未连接", "请先连接 WebSocket Server。")
            return

        self._set_auto_chat_ui_state("starting", len(targets))

        def activated(result: GatewayResult) -> None:
            if not result.ok or result.value is False:
                error = str(result.error or result.value or "未知错误")
                operations.finish(span, success=False, error=error)
                if preserve_session:
                    self.auto_chat_running = False
                self._set_auto_chat_ui_state("error", message=error)
                self._append_chat("自动聊天", f"启动监听失败：{error}")
                return
            self._listener_targets = set(targets)
            if not preserve_session:
                self._auto_chat_session += 1
            self.auto_chat_running = True
            self._set_auto_chat_ui_state("running", len(targets))
            self._append_chat("自动聊天", "已开始接管：" + "、".join(sorted(targets)))
            self._preview_snapshots.clear()
            self._preview_poll_pending = False
            self._preview_backoff_until = 0.0
            self._auto_chat_sent_contents.clear()
            self._preview_suppressed_until.clear()
            self._message_cursor.reset()
            self._preview_timer.start()
            self._append_chat("自动聊天", "监听已启动，预览列表每 5 秒进行一次兜底检查")
            operations.finish(span, success=True, result={"targets": sorted(targets)})

        if not self._listener_targets:
            options = build_options(
                "AddMessageListener",
                {
                    "targets": sorted(targets),
                    "open": False,
                    "monitor_read_conversations": True,
                    "file_save_directory": str(self.attachment_store.root.resolve()),
                },
            )
            self._run_future(self.gateway.call(self.account, "AddMessageListener", options), activated)
            return

        changes = [
            *(('RemoveListeningFriend', build_options('RemoveListeningFriend', {'who': who})) for who in sorted(self._listener_targets - targets)),
            *(('AddListeningFriend', build_options('AddListeningFriend', {'who': who})) for who in sorted(targets - self._listener_targets)),
            ("ResumeMessageListener", ""),
        ]
        self._run_gateway_sequence(changes, activated)

    def _run_gateway_sequence(self, calls: list[tuple[str, Any]], callback: Callable[[GatewayResult], None]) -> None:
        if not calls:
            callback(GatewayResult(True, True))
            return
        function, options = calls[0]

        def done(result: GatewayResult) -> None:
            if not result.ok or result.value is False:
                callback(result)
                return
            self._run_gateway_sequence(calls[1:], callback)

        self._run_future(self.gateway.call(self.account, function, options), done)

    def _stop_auto_chat(self) -> None:
        target_count = len(self._selected_auto_chat_targets())
        span = operations.start(
            "workflow",
            "auto_chat_stop",
            details={"account": self.account, "target_count": target_count},
        )
        self._set_auto_chat_ui_state("stopping", target_count)

        def stopped(result: GatewayResult) -> None:
            if not result.ok or result.value is False:
                error = str(result.error or result.value or "未知错误")
                operations.finish(span, success=False, error=error)
                self._set_auto_chat_ui_state("running", target_count)
                self._append_chat("自动聊天", f"停止监听失败：{error}")
                return
            self._auto_chat_session += 1
            self.auto_chat_running = False
            self._preview_timer.stop()
            self._preview_poll_pending = False
            self._auto_chat_pending.clear()
            self._auto_chat_active_tasks.clear()
            self._auto_chat_queues.clear()
            for reply_span in self._auto_reply_spans.values():
                operations.finish(reply_span, success=False, error="自动聊天已停止")
            self._auto_reply_spans.clear()
            self._set_auto_chat_ui_state("stopped")
            self._append_chat("自动聊天", "已停止消息接管")
            operations.finish(span, success=True, result={"target_count": target_count})
        self._run_future(self.gateway.call(self.account, "PauseMessageListener", ""), stopped)

    def _handle_auto_chat_event(self, event: dict[str, Any]) -> None:
        if not self.auto_chat_running:
            return
        messages = parse_listener_event(event.get("data", ""), self_names={self.account})
        for incoming in messages:
            self._accept_auto_message(incoming)

    def _accept_auto_message(self, incoming) -> None:
        selected = self._selected_auto_chat_targets()
        keyword = self.reply_keyword.text().strip()
        incoming_has_media = bool(incoming.image_base64) or any(
            item.kind in {"image", "sticker"}
            for item in getattr(incoming, "attachments", ())
        )
        if incoming.chat_title not in selected:
            self._append_chat("忽略消息", f"会话未勾选：{incoming.chat_title}")
            return
        if keyword and keyword not in incoming.content:
            self._append_chat("忽略消息", f"未命中关键词：{incoming.chat_title} · {incoming.who}")
            return
        if (
            self._message_cursor.is_outgoing_echo(incoming.chat_title, incoming.content)
            or self._message_cursor.is_outgoing_voice_echo(incoming.chat_title, incoming.content)
            or self._message_cursor.is_outgoing_file_echo(incoming.chat_title, incoming.content)
        ):
            self._append_chat("忽略消息", f"发送回声：{incoming.chat_title}")
            return
        if (
            not incoming_has_media
            and self._message_cursor.is_outgoing_media_echo(incoming.chat_title, incoming.content)
        ):
            self._append_chat("忽略消息", f"发送媒体回声：{incoming.chat_title}")
            operations.event("workflow", "outgoing_media_echo_suppressed", {
                "chat_title": incoming.chat_title,
                "content": incoming.content,
            })
            return
        # Listener and preview polling expose different timestamps and private
        # sender labels. A minute-level identity keeps both surfaces aligned.
        incoming_key = incoming_dedupe_feature(
            incoming,
            include_sender=incoming.chat_title in getattr(self, "_auto_chat_groups", set()),
        )
        if not self._message_cursor.accept_incoming(incoming.chat_title, incoming_key):
            self._append_chat("忽略消息", f"重复消息：{incoming.chat_title} · {incoming.who}")
            return
        if incoming_has_media or bool(
            re.fullmatch(r"\[(?:图片|动画表情)\]", str(incoming.content).strip())
        ):
            latest_media = getattr(self, "_latest_incoming_media", None)
            if latest_media is None:
                latest_media = {}
                self._latest_incoming_media = latest_media
            latest_media[incoming.chat_title] = incoming
        media_label = " · 含图片" if incoming.image_base64 else ""
        attachment_store = getattr(self, "attachment_store", None)
        remembered_attachments = (
            attachment_store.remember(
                incoming.chat_title,
                incoming.attachments,
                received_at=incoming.send_date,
                image_base64=incoming.image_base64,
                message_kind=(
                    "sticker"
                    if incoming.content.startswith(("动画表情", "[动画表情]"))
                    else "image"
                ),
            )
            if attachment_store is not None
            else ()
        )
        if remembered_attachments:
            media_label += " · 附件 " + "、".join(item.name for item in remembered_attachments)
            operations.event("attachment", "incoming_attachment_recorded", {
                "chat_title": incoming.chat_title,
                "sender": incoming.who,
                "attachments": [
                    {"name": item.name, "kind": item.kind, "has_path": bool(item.path)}
                    for item in remembered_attachments
                ],
            })
            self._refresh_attachment_list()
        self._append_chat("收到消息", f"{incoming.chat_title} · {incoming.who}: {incoming.content}{media_label}")
        self._auto_chat_queues.setdefault(incoming.chat_title, deque()).append(incoming)
        self._process_next_auto_message(incoming.chat_title)

    def _poll_auto_chat_previews(self) -> None:
        if (
            not self.auto_chat_running
            or self._preview_poll_pending
            or not self.gateway.connected
            or getattr(self, "_original_image_fetch_count", 0) > 0
            or bool(getattr(self, "_auto_chat_pending", {}))
            or time.monotonic() < getattr(self, "_preview_backoff_until", 0.0)
        ):
            return
        self._preview_poll_pending = True

        def loaded(result: GatewayResult) -> None:
            self._preview_poll_pending = False
            if not self.auto_chat_running:
                return
            if not result.ok:
                is_timeout = "timeout" in str(result.error).casefold()
                self._preview_timeout_count = (
                    self._preview_timeout_count + 1 if is_timeout else 0
                )
                backoff_seconds = 10 if is_timeout else 60
                self._preview_backoff_until = time.monotonic() + backoff_seconds
                operations.event("workflow", "preview_poll_backoff", {
                    "seconds": backoff_seconds,
                    "error": result.error,
                })
                if is_timeout and self._preview_timeout_count >= 2:
                    self._recover_stalled_server(str(result.error))
                return
            self._preview_backoff_until = 0.0
            self._preview_timeout_count = 0
            if not isinstance(result.value, list):
                return
            image_completed = getattr(self, "_preview_image_completed", None)
            if image_completed is None:
                image_completed = {}
                self._preview_image_completed = image_completed
            image_retries = getattr(self, "_preview_image_retries", None)
            if image_retries is None:
                image_retries = {}
                self._preview_image_retries = image_retries
            latest_media = getattr(self, "_latest_incoming_media", None)
            if latest_media is None:
                latest_media = {}
                self._latest_incoming_media = latest_media
            selected = self._selected_auto_chat_targets()
            for item in result.value:
                if not isinstance(item, dict):
                    continue
                title = str(
                    item.get("conversation_title")
                    or item.get("ConversationTitle")
                    or item.get("title")
                    or ""
                ).strip()
                if title not in selected:
                    continue
                content = str(
                    item.get("conversation_content")
                    or item.get("ConversationContent")
                    or item.get("content")
                    or ""
                ).strip()
                time_label = item.get("time") or item.get("Time") or ""
                fingerprint = f"{content}|{time_label}"
                previous = self._preview_snapshots.get(title)
                self._preview_snapshots[title] = fingerprint
                is_image_preview = bool(
                    re.search(r"(?:^|[:：]\s*)\[?图片\]?$", content, re.IGNORECASE)
                )
                if previous is None:
                    continue
                suppressed_until = getattr(self, "_preview_suppressed_until", {}).get(title, 0.0)
                if time.monotonic() < suppressed_until:
                    if is_image_preview:
                        image_completed[title] = fingerprint
                    continue
                message_cursor = getattr(self, "_message_cursor", None)
                if message_cursor is not None and message_cursor.is_outgoing_echo(title, content):
                    self._append_chat("忽略消息", f"发送回声预览：{title}")
                    if is_image_preview:
                        image_completed[title] = fingerprint
                    continue
                last_sent = self._auto_chat_sent_contents.get(title, "")
                if last_sent and content in {last_sent, f"{self.account}: {last_sent}", f"{self.account}：{last_sent}"}:
                    continue
                if previous == fingerprint and not is_image_preview:
                    continue
                # The SDK reports PascalCase fields and can retain an unread
                # counter after opening the conversation. Normalize both the
                # SDK and demo payloads before applying sender filtering.
                preview = {
                    "conversation_title": title,
                    "conversation_content": content,
                    "time": time_label,
                    "not_read_numbr": 0,
                }
                incoming = parse_conversation_preview(preview, self_names={self.account})
                if incoming and not (title in self._auto_chat_groups and incoming.who == "对方"):
                    if is_image_preview:
                        latest_media[title] = IncomingMessage(
                            title,
                            incoming.who or "对方",
                            "[图片]",
                            datetime.now().isoformat(timespec="seconds"),
                            message_type=1,
                        )
                        if image_completed.get(title) == fingerprint:
                            continue
                        retry = image_retries.get(title)
                        if retry and retry[0] == fingerprint and time.monotonic() < retry[2]:
                            continue
                        operations.event("workflow", "image_preview_waiting_for_media", {
                            "chat_title": title,
                            "content": content,
                            "retry_attempt": retry[1] if retry and retry[0] == fingerprint else 0,
                        })
                        self._fetch_preview_image(title, str(time_label), fingerprint)
                        continue
                    self._accept_auto_message(incoming)

        self._run_future(self.gateway.call(self.account, "GetVisibleConversations", ""), loaded)

    def _fetch_preview_image(
        self,
        chat_title: str,
        time_label: str = "",
        fingerprint: str = "",
    ) -> None:
        pending = getattr(self, "_preview_image_fetches", None)
        if pending is None:
            pending = set()
            self._preview_image_fetches = pending
        if chat_title in pending or not self.auto_chat_running or not self.gateway.connected:
            return
        pending.add(chat_title)
        span = operations.start(
            "attachment",
            "preview_image_fetch",
            details={"chat_title": chat_title, "time": time_label},
        )

        def fetched(result: GatewayResult) -> None:
            pending.discard(chat_title)
            if not self.auto_chat_running:
                operations.finish(span, success=False, error="自动聊天会话已停止")
                return
            if not result.ok or not isinstance(result.value, dict):
                error = result.error or "SDK 没有返回原图数据"
                operations.finish(span, success=False, error=error)
                self._append_chat("图片理解", f"{chat_title}: 原图提取失败：{error}")
                self._schedule_preview_image_retry(chat_title, fingerprint, error)
                return
            payload = dict(result.value)
            payload.setdefault("who", "对方")
            payload.setdefault("message", "[图片]")
            payload.setdefault("send_date", datetime.now().isoformat(timespec="seconds"))
            messages = parse_listener_event(
                {"chat_title": chat_title, "new_message": [payload]},
                self_names={self.account},
            )
            if not messages or not (
                messages[0].image_base64
                or any(item.kind in {"image", "sticker"} for item in messages[0].attachments)
            ):
                operations.finish(span, success=False, error="原图数据无法解析")
                self._append_chat("图片理解", f"{chat_title}: 已复制图片但无法解析原图")
                self._schedule_preview_image_retry(chat_title, fingerprint, "原图数据无法解析")
                return
            incoming = messages[0]
            if fingerprint:
                completed = getattr(self, "_preview_image_completed", None)
                if completed is None:
                    completed = {}
                    self._preview_image_completed = completed
                completed[chat_title] = fingerprint
            retries = getattr(self, "_preview_image_retries", None)
            if retries is not None:
                retries.pop(chat_title, None)
            operations.finish(span, success=True, result={
                "chat_title": chat_title,
                "has_image": bool(incoming.image_base64),
                "attachment_count": len(incoming.attachments),
            })
            operations.event("attachment", "preview_image_ready", {
                "chat_title": chat_title,
                "sender": incoming.who,
                "has_image": bool(incoming.image_base64),
                "attachments": [item.name for item in incoming.attachments],
            })
            self._accept_auto_message(incoming)

        self._run_future(
            self.gateway.call(self.account, "GetLatestOriginalImage", {"who": chat_title}),
            fetched,
        )

    def _schedule_preview_image_retry(self, chat_title: str, fingerprint: str, error: str) -> None:
        retries = getattr(self, "_preview_image_retries", None)
        if retries is None:
            retries = {}
            self._preview_image_retries = retries
        previous = retries.get(chat_title)
        attempts = previous[1] + 1 if previous and previous[0] == fingerprint else 1
        delay = min(20.0, 1.5 * (2 ** min(attempts - 1, 4)))
        retries[chat_title] = (
            fingerprint,
            attempts,
            time.monotonic() + delay,
        )
        operations.event("attachment", "preview_image_retry_scheduled", {
            "chat_title": chat_title,
            "attempt": attempts,
            "delay_seconds": delay,
            "error": error,
        })

    def _suppress_outgoing_media_preview(self, chat_title: str, seconds: float = 6.0) -> None:
        values = getattr(self, "_preview_suppressed_until", None)
        if values is None:
            values = {}
            self._preview_suppressed_until = values
        values[chat_title] = max(values.get(chat_title, 0.0), time.monotonic() + seconds)

    def _remember_auto_chat_message(self, feature: str) -> None:
        if len(self._auto_chat_seen_order) >= 2000:
            self._auto_chat_seen.discard(self._auto_chat_seen_order.popleft())
        self._auto_chat_seen_order.append(feature)
        self._auto_chat_seen.add(feature)

    @staticmethod
    def _auto_task_key(incoming: Any) -> str:
        feature = str(getattr(incoming, "feature", "") or "").strip()
        return feature or f"message-{id(incoming)}"

    def _remember_pending_image_edit(self, chat_title: str, request: str) -> None:
        text = str(request or "").strip()
        if text:
            pending = getattr(self, "_pending_image_edits", None)
            if pending is None:
                pending = {}
                self._pending_image_edits = pending
            pending[chat_title] = (text, time.monotonic())

    def _pending_image_edit_request(self, chat_title: str) -> str:
        values = getattr(self, "_pending_image_edits", None)
        if not values:
            return ""
        pending = values.get(chat_title)
        if pending is None:
            return ""
        request, created_at = pending
        if time.monotonic() - created_at > PENDING_IMAGE_EDIT_TTL_SECONDS:
            values.pop(chat_title, None)
            return ""
        return request

    def _clear_pending_image_edit(self, chat_title: str) -> None:
        pending = getattr(self, "_pending_image_edits", None)
        if pending is not None:
            pending.pop(chat_title, None)

    def _recent_conversation_image(self, chat_title: str) -> IncomingAttachment | None:
        attachment_store = getattr(self, "attachment_store", None)
        if attachment_store is None:
            return None
        try:
            images = attachment_store.recent(chat_title, kinds={"image", "sticker"})
        except (OSError, ValueError):
            return None
        return images[-1] if images else None

    def _recent_image_base64(self, chat_title: str) -> tuple[str, IncomingAttachment | None]:
        attachment = MainWindow._recent_conversation_image(self, chat_title)
        if attachment is None:
            return "", None
        try:
            raw = Path(attachment.path).read_bytes()
        except OSError:
            return "", None
        return base64.b64encode(raw).decode("ascii"), attachment

    def _auto_chat_active_count(self, chat_title: str) -> int:
        pending = self._auto_chat_pending
        if isinstance(pending, dict):
            return max(0, int(pending.get(chat_title, 0)))
        return 1 if chat_title in pending else 0

    def _process_next_auto_message(self, chat_title: str) -> None:
        queue = self._auto_chat_queues.get(chat_title)
        if not self.auto_chat_running or not queue:
            return
        active_count = MainWindow._auto_chat_active_count(self, chat_title)
        concurrency_control = getattr(self, "chat_concurrency", None)
        concurrency = max(1, int(concurrency_control.value())) if concurrency_control else 3
        if active_count >= concurrency:
            return
        remaining = self.reply_cooldown.value() - (
            time.monotonic() - self._auto_chat_last_reply.get(chat_title, 0)
        )
        if active_count == 0 and remaining > 0:
            QTimer.singleShot(max(50, int(remaining * 1000)), lambda: self._process_next_auto_message(chat_title))
            return
        incoming = queue.popleft()
        if incoming.chat_title not in self._selected_auto_chat_targets():
            self._process_next_auto_message(chat_title)
            return
        task_key = MainWindow._auto_task_key(incoming)
        if isinstance(self._auto_chat_pending, dict):
            self._auto_chat_pending[chat_title] = active_count + 1
        else:
            self._auto_chat_pending.add(chat_title)
        active_tasks = getattr(self, "_auto_chat_active_tasks", None)
        if active_tasks is None:
            active_tasks = set()
            self._auto_chat_active_tasks = active_tasks
        active_tasks.add(task_key)
        session = self._auto_chat_session
        action = requested_action(incoming.content)
        explicit_image_edit = (
            action.kind is ReplyKind.TEXT and is_image_edit_request(incoming.content)
        )
        pending_image_edit = MainWindow._pending_image_edit_request(self, incoming.chat_title)
        has_incoming_image = bool(incoming.image_base64) or any(
            item.kind == "image" for item in getattr(incoming, "attachments", ())
        )
        resume_pending_edit = bool(pending_image_edit) and (
            has_incoming_image or is_image_edit_followup(incoming.content)
        )
        image_edit_request = (
            incoming.content if explicit_image_edit else pending_image_edit if resume_pending_edit else ""
        )
        is_image_edit = bool(image_edit_request)
        image_for_model = incoming.image_base64
        visual_context = ""
        if not image_for_model and _IMAGE_CONTEXT_REQUEST.search(incoming.content):
            image_for_model, recent_image = MainWindow._recent_image_base64(
                self,
                incoming.chat_title,
            )
            if recent_image is not None:
                operations.event("attachment", "recent_image_context_loaded", {
                    "chat_title": incoming.chat_title,
                    "name": recent_image.name,
                    "received_at": recent_image.received_at,
                    "request": incoming.content,
                })
        if image_for_model:
            cached_understanding = self.image_understanding_cache.lookup(image_for_model)
            if cached_understanding is not None:
                image_for_model = ""
                visual_context = (
                    f"[视觉语义缓存命中，类型：{cached_understanding.kind}] "
                    f"{cached_understanding.description}"
                )
        self._auto_reply_spans[task_key] = operations.start(
            "workflow",
            "auto_reply",
            details={
                "account": self.account,
                "chat_title": incoming.chat_title,
                "sender": incoming.who,
                "content": incoming.content,
                "has_image": bool(image_for_model),
                "reply_kind": "image_edit" if is_image_edit else action.kind.value,
                "task_key": task_key,
                "conversation_concurrency": concurrency,
            },
        )
        QTimer.singleShot(0, lambda: self._process_next_auto_message(chat_title))
        if is_image_edit:
            MainWindow._remember_pending_image_edit(
                self,
                incoming.chat_title,
                image_edit_request,
            )
            operations.event("workflow", "image_edit_route", {
                "chat_title": incoming.chat_title,
                "source": (
                    "explicit"
                    if explicit_image_edit
                    else "pending_with_image"
                    if has_incoming_image
                    else "pending_followup"
                ),
            })
            self.memory.add_user(
                incoming.chat_title,
                incoming.who,
                incoming.content,
                image_for_model,
                visual_context,
            )
            self._original_image_fetch_count = getattr(self, "_original_image_fetch_count", 0) + 1
            future = self.model_executor.submit(
                self._fetch_latest_original_and_edit,
                incoming,
                image_edit_request,
            )
            self._finish_auto_image(future, incoming, session, mode="edited")
            return
        realtime_request = (
            detect_realtime_request(
                incoming.content,
                self.memory.transcript(incoming.chat_title),
            )
            if self.codex_enabled.isChecked() and action.kind is ReplyKind.TEXT
            else None
        )
        if realtime_request is not None:
            self.memory.add_user(
                incoming.chat_title,
                incoming.who,
                incoming.content,
                image_for_model,
                visual_context,
            )
            operations.event("tool", "realtime_tool_route", {
                "chat_title": incoming.chat_title,
                "kind": realtime_request.kind,
            })
            future = self.model_executor.submit(self.realtime_tool_executor.execute, realtime_request)
            self._start_auto_realtime_tool(future, incoming, session)
            return
        if (
            self.codex_enabled.isChecked()
            and action.kind is ReplyKind.TEXT
            and CodexTaskRouter.should_delegate(incoming.content)
        ):
            self.memory.add_user(
                incoming.chat_title,
                incoming.who,
                incoming.content,
                image_for_model,
                visual_context,
            )
            operations.event("codex", "codex_task_route", {
                "chat_title": incoming.chat_title,
                "source": "explicit",
            })
            self._start_auto_codex(incoming, session, route_source="explicit")
            return
        if action.kind is ReplyKind.IMAGE:
            self.memory.add_user(
                incoming.chat_title,
                incoming.who,
                incoming.content,
                image_for_model,
                visual_context,
            )
            future = self.model_executor.submit(
                self.model_client.generate_image,
                self._image_config(),
                action.argument,
            )
            self._finish_auto_image(future, incoming, session)
            return
        if action.kind is ReplyKind.EMOJI:
            self._send_auto_emoji(incoming, session, action.argument)
            return
        if action.kind is ReplyKind.STICKER:
            self._send_auto_sticker(incoming, session, action.argument)
            return
        self.memory.add_user(
            incoming.chat_title,
            incoming.who,
            incoming.content,
            image_for_model,
            visual_context,
        )
        config = self._model_config()
        policy_messages, matched_policy, _memory_name = self._resolved_persona_messages(incoming)
        operations.event("workflow", "auto_reply_policy_resolved", {
            "chat_title": incoming.chat_title,
            "sender": incoming.who,
            "matched_policy": matched_policy,
        })
        context = self.memory.context(incoming.chat_title, config.system_prompt, policy_messages)
        if action.kind is ReplyKind.TEXT and self.codex_enabled.isChecked():
            context.insert(1, {
                "role": "system",
                "content": CodexTaskRouter.model_instruction(),
            })
        if action.kind is ReplyKind.TEXT:
            context.insert(1, {
                "role": "system",
                "content": (
                    "如果当前语境最适合只用一个收藏或自定义表情包回应，可以只返回 "
                    "<MYBOT_STICKER>；需要指定风格时只返回 <MYBOT_STICKER:关键词>。"
                    "不要把标记和文字混合，不要频繁使用，也不要选择微信默认 Emoji。"
                ),
            })
        if action.kind is ReplyKind.VOICE:
            context.insert(1, {
                "role": "system",
                "content": (
                    "本次生成的文字会由程序转换成微信语音消息发送。"
                    "直接自然地回答用户，不要声称自己不能、不方便或无法发送语音。"
                ),
            })
        future = self.model_executor.submit(
            self.model_client.generate_with_fallback,
            config,
            self._backup_model_config(),
            context,
            timeout=self._auto_chat_model_timeout(),
        )
        self._finish_auto_reply(
            future,
            incoming,
            session,
            action,
            visual_cache_hit=bool(visual_context),
        )

    def _resolved_persona_messages(self, incoming) -> tuple[list[str], list[str], str]:
        is_group = incoming.chat_title in self._auto_chat_groups
        policy_messages, matched_policy = self._reply_policy.system_messages(
            chat_title=incoming.chat_title,
            sender=incoming.who,
            is_group=is_group,
        )
        memory_name = person_id(
            incoming.chat_title,
            incoming.who,
            is_group,
            self.personal_memory_aliases,
        )
        if not self.personal_memory_enabled.isChecked():
            return policy_messages, matched_policy, memory_name
        learned_prompt = self.personal_memory_store.get(memory_name).prompt(
            memory_name,
            incoming.content,
        )
        if learned_prompt:
            policy_messages.append(learned_prompt)
            matched_policy.append(f"learned:{memory_name}")
        episodic_prompt = self.episodic_memory_store.prompt(memory_name, incoming.content)
        if episodic_prompt:
            policy_messages.append(episodic_prompt)
            matched_policy.append(f"episodes:{memory_name}")
        return policy_messages, matched_policy, memory_name

    def _persona_task_messages(
        self,
        incoming,
        *,
        purpose: str,
        task_result: str = "",
    ) -> list[dict[str, str]]:
        policy_messages, matched_policy, memory_name = self._resolved_persona_messages(incoming)
        is_group = incoming.chat_title in self._auto_chat_groups
        if purpose == "ack":
            instruction = (
                "你马上要实际执行一个需要工具和时间的任务。结合既定人格、示例对话、"
                "双方关系和最近聊天，只写一句自然的微信开场，表示现在去做。"
                "像熟人聊天，不用客服腔，不复述完整需求，不解释内部工具，不承诺具体完成时间，"
                "也不能声称已经完成。控制在 8 到 35 个汉字，不要使用分段标记。"
                "禁止照抄“这个任务需要一些时间，我处理完成后把结果发给你”。"
            )
            payload = (
                f"场景：{'群聊' if is_group else '私聊'}\n"
                f"当前发送者：{incoming.who}\n"
                f"最近对话：\n{self.memory.transcript(incoming.chat_title, max_chars=1200)}\n"
                f"需要开始处理的事：{incoming.content}"
            )
        else:
            locked_facts = MainWindow._codex_result_anchors(task_result)
            instruction = (
                "下面是工具已经实际完成并验证的结果。把它改写成符合既定人格、示例对话、"
                "双方关系和最近聊天的微信回复。先说结果，语气自然，不使用报告腔，不提 Codex、"
                "CLI、后台或内部流程；不得改变成功或失败状态，不得遗漏关键数字、路径、限制和"
                "验证结论，不得添加工具结果中没有的事实。需要多条消息时只能用 "
                "<MYBOT_SPLIT> 分隔，最多四条，总长度不超过 1600 字。"
                "下方列出的事实锁必须逐字出现在回复中，不能改写或换算。"
            )
            payload = (
                f"场景：{'群聊' if is_group else '私聊'}\n"
                f"当前发送者：{incoming.who}\n"
                f"对方原始请求：{incoming.content}\n"
                f"最近对话：\n{self.memory.transcript(incoming.chat_title, max_chars=1200)}\n\n"
                "必须逐字保留的事实锁：\n- "
                + ("\n- ".join(locked_facts) if locked_facts else "[无]")
                + "\n\n"
                f"工具完成结果：\n{task_result[:1800]}"
            )
        operations.event("codex", "codex_persona_context", {
            "purpose": purpose,
            "chat_title": incoming.chat_title,
            "person": memory_name,
            "matched_policy": matched_policy,
        })
        return [
            {"role": "system", "content": self._model_config().system_prompt},
            *({"role": "system", "content": item} for item in policy_messages),
            {"role": "system", "content": instruction},
            {"role": "user", "content": payload},
        ]

    @staticmethod
    def _valid_codex_acknowledgement(value: str) -> bool:
        if not value or len(value) > 80 or "\n" in value or "<MYBOT" in value:
            return False
        lowered = value.casefold()
        if any(marker in lowered for marker in ("codex", "cli", "后台")):
            return False
        if any(marker in value for marker in ("已经完成", "已经处理好", "已经查完")):
            return False
        return value != "这个任务需要一些时间，我处理完成后把结果发给你"

    @staticmethod
    def _codex_result_anchors(value: str) -> tuple[str, ...]:
        text = str(value)
        anchors: list[str] = []
        patterns = (
            r"(?<![A-Za-z0-9_/\\])(?:[A-Za-z]:[\\/])?[A-Za-z0-9_.@+-]+(?:[\\/][A-Za-z0-9_.@+ -]+)+",
            r"(?<![A-Za-z0-9_/\\])[A-Za-z0-9_.-]+\.(?:py|json|toml|ya?ml|md|txt|log|js|ts|tsx|jsx|html|css)(?![A-Za-z0-9_])",
            r"(?<!\d)\d+(?:\.\d+)?\s*(?:项|个|条|次|秒|分钟|小时|毫秒|ms|%|MB|GB)(?![A-Za-z0-9])",
        )
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                anchor = str(match).strip("`'\"，,。.;；:：()（）[]【】")
                if anchor and anchor not in anchors:
                    anchors.append(anchor)
        for marker in (
            "全部通过", "测试通过", "验证通过", "执行成功", "执行失败", "处理失败",
            "尚未完成", "需要重启", "无需重启", "重启后生效", "已修改", "已修复",
        ):
            if marker in text and marker not in anchors:
                anchors.append(marker)
        return tuple(anchors[:20])

    @staticmethod
    def _codex_result_preserves_facts(raw_result: str, reply: str) -> bool:
        return all(anchor in reply for anchor in MainWindow._codex_result_anchors(raw_result))

    def _start_auto_codex(self, incoming, session: int, *, route_source: str = "explicit") -> None:
        task_id = uuid.uuid4().hex
        fallback_acknowledgement = sanitize_auto_reply_text(CodexTaskRouter.acknowledgement(
            incoming.content,
            is_group=incoming.chat_title in self._auto_chat_groups,
        ))
        operations.event("codex", "codex_task_enqueue", {
            "task_id": task_id,
            "chat_title": incoming.chat_title,
            "sender": incoming.who,
            "request_length": len(incoming.content),
            "route_source": route_source,
        })
        runner = self._codex_runner()
        conversation_context = self.memory.transcript(incoming.chat_title)

        def run_codex_task():
            attachments = self.attachment_store.for_request(
                incoming.chat_title,
                incoming.content,
                received_at=incoming.send_date,
            )
            operations.event("attachment", "codex_task_inputs_resolved", {
                "task_id": task_id,
                "chat_title": incoming.chat_title,
                "attachment_count": len(attachments),
                "attachments": [
                    {"name": item.name, "kind": item.kind, "size": item.size}
                    for item in attachments
                ],
            })
            return runner.run(
                incoming.chat_title,
                incoming.content,
                conversation_context=conversation_context,
                task_id=task_id,
                attachments=attachments,
            )

        codex_future = self.codex_executor.submit(run_codex_task)
        self._finish_auto_codex_ack(
            codex_future,
            runner,
            incoming,
            session,
            task_id,
            fallback_acknowledgement,
        )

    def _finish_auto_codex_ack(
        self,
        codex_future,
        runner: CodexCliRunner,
        incoming,
        session: int,
        task_id: str,
        acknowledgement: str,
    ) -> None:
        if session != self._auto_chat_session or not self.auto_chat_running:
            self._finish_auto_message(incoming, success=False, error="自动聊天会话已停止")
            return
        self._message_cursor.record_outgoing(incoming.chat_title, acknowledgement)
        reference, reference_reason = self._auto_reply_reference(incoming)
        options = build_options("SendMessage", {
            "who": incoming.chat_title,
            "message": acknowledgement,
            "refer": reference,
        })
        if reference:
            operations.event("workflow", "auto_reply_reference", {
                "chat_title": incoming.chat_title,
                "sender": incoming.who,
                "reason": reference_reason,
                "phase": "codex_ack",
            })

        def acknowledged(result: GatewayResult) -> None:
            if session != self._auto_chat_session or not result.ok or result.value is False:
                self._append_chat("Codex", f"任务确认消息发送失败：{result.error or result.value}")
                self._finish_auto_message(
                    incoming,
                    success=False,
                    error=result.error or result.value,
                )
                return
            self.memory.add_assistant(incoming.chat_title, acknowledgement)
            self._auto_chat_sent_contents[incoming.chat_title] = acknowledgement
            self._append_chat("Codex", f"{incoming.chat_title}: {acknowledgement}")
            operations.event("codex", "codex_task_ack", {
                "task_id": task_id,
                "chat_title": incoming.chat_title,
                "source": "local_router",
            })
            self._finish_auto_codex(codex_future, runner, incoming, session)

        self._run_future(self.gateway.call(self.account, "SendMessage", options), acknowledged)

    def _finish_auto_codex(self, future, runner: CodexCliRunner, incoming, session: int) -> None:
        if not future.done():
            QTimer.singleShot(250, lambda: self._finish_auto_codex(future, runner, incoming, session))
            return
        if session != self._auto_chat_session or not self.auto_chat_running:
            self._finish_auto_message(incoming, success=False, error="Codex 完成时自动聊天已停止")
            return
        try:
            codex_result = future.result()
            raw_reply = sanitize_auto_reply_text(codex_result.text.strip()[:1_800])
            if not raw_reply:
                raise ValueError("Codex 返回了空结果")
            operations.event("codex", "codex_task_complete", {
                "task_id": codex_result.task_id,
                "thread_id": codex_result.thread_id,
                "reply_length": len(raw_reply),
                "matched_abilities": list(codex_result.matched_abilities),
            })
        except Exception as exc:
            self._append_chat("Codex", f"任务执行失败：{exc}")
            failure = "这次没弄好，我再看看"
            self._send_auto_text_segments(incoming, session, (failure,), failure)
            return

        after_sent = lambda: self._after_codex_reply(runner, incoming, codex_result)
        if codex_result.output_files:
            self._send_codex_output_files(
                incoming,
                session,
                codex_result,
                after_sent=lambda sent, failed: self._send_codex_delivery_completion(
                    incoming,
                    session,
                    sent,
                    failed,
                    after_sent=after_sent,
                ),
            )
            return

        humanize_future = self.model_executor.submit(
            self.model_client.generate,
            self._model_config(),
            self._persona_task_messages(
                incoming,
                purpose="result",
                task_result=raw_reply,
            ),
            timeout=15,
        )
        self._finish_auto_codex_humanize(
            humanize_future,
            runner,
            incoming,
            session,
            codex_result,
            raw_reply,
        )

    def _finish_auto_codex_humanize(
        self,
        future,
        runner: CodexCliRunner,
        incoming,
        session: int,
        codex_result: CodexResult,
        raw_reply: str,
    ) -> None:
        if not future.done():
            QTimer.singleShot(100, lambda: self._finish_auto_codex_humanize(
                future,
                runner,
                incoming,
                session,
                codex_result,
                raw_reply,
            ))
            return
        if session != self._auto_chat_session or not self.auto_chat_running:
            self._finish_auto_message(incoming, success=False, error="自动聊天会话已停止")
            return
        source = "model"
        try:
            reply = sanitize_auto_reply_text(str(future.result()).strip()[:1_800])
            if not reply or "<MYBOT_DELEGATE_CODEX>" in reply:
                raise ValueError("人格模型没有返回可发送的任务结果")
            if not self._codex_result_preserves_facts(raw_reply, reply):
                missing = [
                    anchor
                    for anchor in self._codex_result_anchors(raw_reply)
                    if anchor not in reply
                ]
                raise ValueError("人格改写遗漏事实锁：" + "、".join(missing[:6]))
            segments = parse_auto_reply_segments(reply)
        except Exception as exc:
            source = "codex_fallback"
            reply = raw_reply
            segments = parse_auto_reply_segments(reply)
            operations.event("codex", "codex_persona_result_fallback", {
                "task_id": codex_result.task_id,
                "error": f"{type(exc).__name__}: {exc}",
            })
        operations.event("codex", "codex_task_humanized", {
            "task_id": codex_result.task_id,
            "source": source,
            "raw_length": len(raw_reply),
            "reply_length": len(reply),
        })
        after_sent = lambda: self._after_codex_reply(runner, incoming, codex_result)
        self._send_auto_text_segments(
            incoming,
            session,
            segments,
            reply,
            after_sent=after_sent,
        )

    def _send_codex_delivery_completion(
        self,
        incoming,
        session: int,
        sent: tuple[str, ...],
        failed: tuple[str, ...],
        *,
        after_sent: Callable[[], None],
    ) -> None:
        if sent and not failed:
            message = (
                f"{sent[0]} 做好了，已经发给你了"
                if len(sent) == 1
                else "文件都做好了，已经发给你了"
            )
        elif sent:
            message = f"文件已发给你，但 {failed[0]} 没发出去"
        else:
            message = "文件做好了，但这次没发出去"
        self._send_auto_text_segments(
            incoming,
            session,
            (message,),
            message,
            after_sent=after_sent,
        )

    def _send_codex_output_files(
        self,
        incoming,
        session: int,
        result: CodexResult,
        *,
        after_sent: Callable[[tuple[str, ...], tuple[str, ...]], None],
    ) -> None:
        pending = deque(result.output_files)
        failed: list[str] = []
        sent_files: list[str] = []

        def send_next() -> None:
            if session != self._auto_chat_session or not self.auto_chat_running:
                self._finish_auto_message(incoming, success=False, error="自动聊天会话已停止")
                return
            if not pending:
                operations.event("attachment", "codex_outputs_delivered", {
                    "task_id": result.task_id,
                    "chat_title": incoming.chat_title,
                    "sent_count": len(result.output_files) - len(failed),
                    "failed": failed,
                })
                after_sent(tuple(sent_files), tuple(failed))
                return
            file_path = pending.popleft()
            try:
                options = build_options("SendFile", {"who": incoming.chat_title, "files": [file_path]})
            except Exception as exc:
                failed.append(Path(file_path).name)
                operations.event("attachment", "codex_output_send_failed", {
                    "task_id": result.task_id,
                    "name": Path(file_path).name,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                QTimer.singleShot(0, send_next)
                return

            def sent(gateway_result: GatewayResult) -> None:
                if not gateway_result.ok or gateway_result.value is False:
                    self._message_cursor.cancel_outgoing_file(
                        incoming.chat_title,
                        Path(file_path).name,
                    )
                    failed.append(Path(file_path).name)
                    self._append_chat(
                        "Codex",
                        f"成果文件发送失败：{Path(file_path).name} · {gateway_result.error or gateway_result.value}",
                    )
                else:
                    sent_files.append(Path(file_path).name)
                    self._append_chat("Codex", f"已向 {incoming.chat_title} 发送成果文件：{Path(file_path).name}")
                QTimer.singleShot(220, send_next)

            self._message_cursor.record_outgoing_file(
                incoming.chat_title,
                Path(file_path).name,
            )
            self._suppress_outgoing_media_preview(incoming.chat_title)
            self._run_future(self.gateway.call(self.account, "SendFile", options), sent)

        send_next()

    def _after_codex_reply(self, runner: CodexCliRunner, incoming, result: CodexResult) -> None:
        operations.event("codex", "codex_task_reply", {
            "task_id": result.task_id,
            "chat_title": incoming.chat_title,
        })
        settings = self.settings.get("codex", {})
        if isinstance(settings, dict) and not bool(settings.get("auto_learn_abilities", True)):
            return
        primary = self._model_config()
        backup = self._backup_model_config()

        def review_and_distill():
            review_span = operations.start(
                "codex",
                "codex_ability_review",
                operation_id=result.task_id,
                details={"request_length": len(incoming.content)},
            )
            try:
                decision = self.reusable_task_reviewer.review(
                    primary=primary,
                    backup=backup,
                    request=incoming.content,
                    result=result.text,
                )
                operations.finish(review_span, success=True, result={
                    "reusable": decision.reusable,
                    "reason": decision.reason,
                    "name": decision.name,
                })
                if not decision.reusable:
                    return None
                return runner.distill_ability(
                    task_id=result.task_id,
                    request=incoming.content,
                    result=result.text,
                    suggested_name=decision.name,
                    suggested_triggers=decision.triggers,
                    forbidden_terms=(incoming.chat_title, incoming.who, self.account),
                )
            except Exception as exc:
                if 'decision' not in locals():
                    operations.finish(review_span, success=False, error=f"{type(exc).__name__}: {exc}")
                raise

        future = self.ability_executor.submit(review_and_distill)

        def poll() -> None:
            if not future.done():
                QTimer.singleShot(500, poll)
                return
            try:
                ability = future.result()
                if ability:
                    self._update_codex_status(f"新沉淀 {ability['name']}")
                    self._append_chat("Codex 能力", f"已验证并沉淀：{ability['name']}")
                else:
                    self._update_codex_status("本次无需沉淀")
            except Exception as exc:
                self._update_codex_status("最近沉淀失败")
                self._append_chat("Codex 能力", f"能力沉淀失败，不影响任务结果：{exc}")

        QTimer.singleShot(500, poll)

    @staticmethod
    def _image_prompt(content: str) -> str:
        text = content.strip()
        for prefix in ("/image", "生成图片", "画图", "生图"):
            if text.lower().startswith(prefix.lower()):
                return text[len(prefix):].lstrip("：: ，,") or "一张适合微信聊天分享的图片"
        return ""

    def _finish_auto_reply(
        self,
        future,
        incoming,
        session: int,
        action: ReplyAction,
        visual_cache_hit: bool = False,
    ) -> None:
        if not future.done():
            QTimer.singleShot(
                100,
                lambda: self._finish_auto_reply(
                    future,
                    incoming,
                    session,
                    action,
                    visual_cache_hit=visual_cache_hit,
                ),
            )
            return
        if session != self._auto_chat_session or not self.auto_chat_running:
            self._finish_auto_message(incoming, success=False, error="自动聊天会话已停止")
            return
        try:
            raw_reply = str(future.result()).strip()
            reply, image_understanding = extract_image_understanding(raw_reply)
            incoming_image = str(getattr(incoming, "image_base64", "") or "")
            if incoming_image and not visual_cache_hit:
                if image_understanding is None:
                    operations.event("vision_cache", "classification_missing", {
                        "chat_title": incoming.chat_title,
                        "sender": incoming.who,
                    })
                else:
                    self.image_understanding_cache.remember(
                        incoming_image,
                        image_understanding,
                        source_conversation=incoming.chat_title,
                    )
                    self.memory.resolve_latest_visual(
                        incoming.chat_title,
                        incoming.who,
                        incoming.content,
                        image_understanding.kind,
                        image_understanding.description,
                    )
            if (
                action.kind is ReplyKind.TEXT
                and self.codex_enabled.isChecked()
                and CodexTaskRouter.model_requested_delegate(reply)
            ):
                operations.event("codex", "codex_task_route", {
                    "chat_title": incoming.chat_title,
                    "source": "model",
                })
                self._start_auto_codex(incoming, session, route_source="model")
                return
            sticker_query = model_sticker_request(reply) if action.kind is ReplyKind.TEXT else None
            if sticker_query is not None:
                operations.event("sticker", "model_sticker_route", {
                    "chat_title": incoming.chat_title,
                    "query": sticker_query,
                })
                self._send_auto_sticker(incoming, session, sticker_query)
                return
            reply = sanitize_auto_reply_text(reply)
            if _IMAGE_RESEND_REPLY.search(reply) and (
                bool(getattr(incoming, "image_base64", ""))
                or MainWindow._recent_conversation_image(self, incoming.chat_title) is not None
                or incoming.chat_title in getattr(self, "_latest_incoming_media", {})
            ):
                operations.event("workflow", "image_resend_reply_blocked", {
                    "chat_title": incoming.chat_title,
                    "sender": getattr(incoming, "who", ""),
                    "request": getattr(incoming, "content", ""),
                })
                reply = "我看得到上面那张图，直接按这张处理"
            segments = parse_auto_reply_segments(reply)
        except Exception as exc:
            self._append_chat("自动聊天", f"模型生成失败：{exc}")
            self._finish_auto_message(incoming, success=False, error=exc)
            return

        if action.kind is ReplyKind.VOICE:
            self._send_auto_voice(incoming, session, " ".join(segments), reply)
            return
        self._send_auto_text_segments(incoming, session, segments, reply)

    def _start_auto_realtime_tool(self, future, incoming, session: int) -> None:
        acknowledgement = "稍等，我去看一下"
        self._message_cursor.record_outgoing(incoming.chat_title, acknowledgement)
        reference, reference_reason = self._auto_reply_reference(incoming)
        options = build_options("SendMessage", {
            "who": incoming.chat_title,
            "message": acknowledgement,
            "refer": reference,
        })
        if reference:
            operations.event("workflow", "auto_reply_reference", {
                "chat_title": incoming.chat_title,
                "sender": incoming.who,
                "reason": reference_reason,
                "phase": "realtime_ack",
            })

        def acknowledged(result: GatewayResult) -> None:
            if result.ok and result.value is not False:
                self.memory.add_assistant(incoming.chat_title, acknowledgement)
                self._auto_chat_sent_contents[incoming.chat_title] = acknowledgement
                self._append_chat("实时工具", f"{incoming.chat_title}: {acknowledgement}")
                operations.event("tool", "realtime_tool_ack", {
                    "chat_title": incoming.chat_title,
                    "source": "local_router",
                })
            else:
                self._append_chat("实时工具", f"查询提示发送失败：{result.error or result.value}")
            self._finish_auto_realtime_tool(future, incoming, session)

        self._run_future(self.gateway.call(self.account, "SendMessage", options), acknowledged)

    def _finish_auto_realtime_tool(self, future, incoming, session: int) -> None:
        if not future.done():
            QTimer.singleShot(100, lambda: self._finish_auto_realtime_tool(future, incoming, session))
            return
        if session != self._auto_chat_session or not self.auto_chat_running:
            self._finish_auto_message(incoming, success=False, error="自动聊天会话已停止")
            return
        try:
            reply = sanitize_auto_reply_text(str(future.result()).strip())
            segments = parse_auto_reply_segments(reply)
        except Exception as exc:
            self._append_chat("实时工具", f"执行失败，转交 Codex：{exc}")
            operations.event("tool", "realtime_tool_fallback", {
                "chat_title": incoming.chat_title,
                "error": f"{type(exc).__name__}: {exc}",
            })
            self._start_auto_codex(incoming, session, route_source="realtime_fallback")
            return
        self._send_auto_text_segments(incoming, session, segments, reply)

    def _auto_reply_reference(self, incoming: Any) -> tuple[dict[str, Any] | None, str]:
        content = str(getattr(incoming, "content", "") or "").strip()
        if not content:
            return None, "unsupported_message"
        if _IMAGE_QUOTE_REQUEST.search(content):
            latest_media = getattr(self, "_latest_incoming_media", {}).get(incoming.chat_title)
            if latest_media is not None:
                reference = build_message_reference(
                    getattr(latest_media, "who", "对方") or "对方",
                    "[图片]",
                    getattr(latest_media, "send_date", "") or datetime.now().isoformat(timespec="seconds"),
                )
                if reference is not None:
                    return reference, "explicit_incoming_image"
            recent_image = MainWindow._recent_conversation_image(self, incoming.chat_title)
            if recent_image is not None:
                reference = build_message_reference(
                    "对方",
                    "[图片]",
                    recent_image.received_at or datetime.now().isoformat(timespec="seconds"),
                )
                if reference is not None:
                    return reference, "explicit_incoming_image"
        reason = ""
        has_media = bool(getattr(incoming, "image_base64", "")) or bool(
            getattr(incoming, "attachments", ())
        )
        is_media_placeholder = bool(re.match(r"^\[[^\]\r\n]{1,24}\]$", content))
        if has_media or is_media_placeholder:
            reason = "media_reply"
        elif incoming.chat_title in getattr(self, "_auto_chat_groups", set()):
            reason = "group_context"
        elif MainWindow._auto_chat_active_count(self, incoming.chat_title) > 1:
            reason = "parallel_messages"
        else:
            try:
                sent_at = datetime.fromisoformat(
                    str(getattr(incoming, "send_date", "") or "").replace("Z", "+00:00")
                ).replace(tzinfo=None)
                if (datetime.now() - sent_at).total_seconds() >= 60:
                    reason = "delayed_reply"
            except ValueError:
                pass
        if not reason:
            return None, "direct_reply"
        return (
            build_message_reference(incoming.who, content, getattr(incoming, "send_date", "")),
            reason,
        )

    def _send_auto_text_segments(
        self,
        incoming,
        session: int,
        segments: tuple[str, ...],
        full_reply: str,
        after_sent: Callable[[], None] | None = None,
    ) -> None:
        segments = tuple(
            cleaned
            for cleaned in (sanitize_auto_reply_text(segment) for segment in segments)
            if cleaned
        )
        full_reply = sanitize_auto_reply_text(full_reply)
        if not segments:
            self._finish_auto_message(incoming, success=False, error="回复清理后为空")
            return
        pending = deque(segments)
        reference, reference_reason = self._auto_reply_reference(incoming)
        reference_logged = False

        def send_next() -> None:
            nonlocal reference_logged
            if session != self._auto_chat_session or not self.auto_chat_running:
                self._finish_auto_message(incoming, success=False, error="自动聊天会话已停止")
                return
            if not pending:
                self._auto_chat_last_reply[incoming.chat_title] = time.monotonic()
                self._auto_chat_sent_contents[incoming.chat_title] = segments[-1]
                self.memory.add_assistant(incoming.chat_title, full_reply)
                self._schedule_personal_learning(incoming, full_reply)
                self._append_chat("自动回复", f"{incoming.chat_title}: {' | '.join(segments)}")
                self._finish_auto_message(
                    incoming,
                    result={
                        "reply_kind": "text",
                        "segment_count": len(segments),
                        "referenced": bool(reference),
                        "reference_reason": reference_reason,
                    },
                )
                if after_sent is not None:
                    after_sent()
                return
            is_first_segment = len(pending) == len(segments)
            segment = pending.popleft()
            self._message_cursor.record_outgoing(incoming.chat_title, segment)
            options = build_options("SendMessage", {
                "who": incoming.chat_title,
                "message": segment,
                "refer": reference if is_first_segment else None,
            })
            if reference and not reference_logged:
                reference_logged = True
                operations.event("workflow", "auto_reply_reference", {
                    "chat_title": incoming.chat_title,
                    "sender": incoming.who,
                    "reason": reference_reason,
                    "phase": "reply",
                })

            def sent(result: GatewayResult) -> None:
                if session != self._auto_chat_session or not result.ok or result.value is False:
                    self._append_chat("自动聊天", f"回复发送失败：{result.error or result.value}")
                    self._finish_auto_message(
                        incoming,
                        success=False,
                        error=result.error or result.value,
                    )
                    return
                QTimer.singleShot(220, send_next)

            self._run_future(self.gateway.call(self.account, "SendMessage", options), sent)

        send_next()

    def _send_auto_voice(self, incoming, session: int, text: str, full_reply: str) -> None:
        text = sanitize_auto_reply_text(text)
        full_reply = sanitize_auto_reply_text(full_reply)
        voice = self.settings.get("voice", {}) if isinstance(self.settings.get("voice", {}), dict) else {}
        request = {
            "input": text,
            "speed": float(voice.get("speed", 1.0)),
            "style": str(voice.get("style", "轻松自然，像朋友聊天")),
        }
        options = build_options(
            "SendStreamingVoiceMessage",
            {"who": incoming.chat_title, "request": request},
        )
        # Register before the SDK call: preview polling can see the new bubble
        # before the asynchronous send-success callback runs.
        self._message_cursor.record_outgoing_voice(incoming.chat_title, text)
        self._suppress_outgoing_media_preview(incoming.chat_title)

        def sent(result: GatewayResult) -> None:
            if session != self._auto_chat_session or not result.ok or result.value is False:
                self._message_cursor.cancel_outgoing_voice(incoming.chat_title, text)
                self._append_chat("自动聊天", f"语音发送失败：{result.error or result.value}")
                self._finish_auto_message(
                    incoming,
                    success=False,
                    error=result.error or result.value,
                )
                return
            self._auto_chat_last_reply[incoming.chat_title] = time.monotonic()
            self.memory.add_assistant(incoming.chat_title, full_reply)
            self._schedule_personal_learning(incoming, full_reply)
            self._append_chat("自动回复", f"{incoming.chat_title}: 已发送语音 · {text}")
            self._finish_auto_message(incoming, result={"reply_kind": "voice"})

        self._run_future(self.gateway.call(self.account, "SendStreamingVoiceMessage", options), sent)

    def _send_auto_emoji(self, incoming, session: int, emoji: str) -> None:
        # Automatic chat never sends WeChat's default emoji. An explicit
        # “表情” request is resolved against custom/saved sticker catalogs.
        self._send_auto_sticker(incoming, session, emoji)

    def _reserve_auto_sticker(self, incoming) -> bool:
        chat_title = incoming.chat_title
        now = time.monotonic()
        in_flight = getattr(self, "_sticker_in_flight", None)
        if in_flight is None:
            in_flight = {}
            self._sticker_in_flight = in_flight
        started_at = in_flight.get(chat_title)
        last_sent = getattr(self, "_sticker_last_sent", {}).get(chat_title, 0.0)
        reason = ""
        if started_at is not None and now - started_at < STICKER_IN_FLIGHT_TTL_SECONDS:
            reason = "in_flight"
        elif last_sent and now - last_sent < STICKER_COOLDOWN_SECONDS:
            reason = "cooldown"
        if reason:
            operations.event("sticker", "duplicate_sticker_suppressed", {
                "chat_title": chat_title,
                "sender": incoming.who,
                "reason": reason,
                "cooldown_seconds": STICKER_COOLDOWN_SECONDS,
            })
            self._finish_auto_message(incoming, result={
                "reply_kind": "sticker",
                "suppressed": True,
                "reason": reason,
            })
            return False
        in_flight[chat_title] = now
        return True

    def _release_auto_sticker(self, chat_title: str, *, sent: bool = False) -> None:
        getattr(self, "_sticker_in_flight", {}).pop(chat_title, None)
        if sent:
            last_sent = getattr(self, "_sticker_last_sent", None)
            if last_sent is None:
                last_sent = {}
                self._sticker_last_sent = last_sent
            last_sent[chat_title] = time.monotonic()

    def _send_auto_sticker(self, incoming, session: int, sticker: str) -> None:
        if not MainWindow._reserve_auto_sticker(self, incoming):
            return
        cached_items = list(getattr(self, "_sticker_catalog_items", []))
        scan_future = (
            self.gateway.call(self.account, "ScanAllStickers", "")
            if not cached_items
            else None
        )

        def scanned(result: GatewayResult) -> None:
            value = result.value if result.ok and isinstance(result.value, dict) else {}
            items = value.get("Items") or value.get("items") or cached_items
            items = [item for item in items if isinstance(item, dict)]
            if items:
                self._sticker_catalog_items = items
            context_query = infer_sticker_query(
                sticker,
                self.memory.transcript(incoming.chat_title, max_chars=2400)
                if hasattr(self, "memory")
                else "",
            )
            ranked = sticker_selection_candidates(items, context_query)
            candidates = [item for _score, item in ranked]
            if not candidates:
                selected, reason = select_sticker_item(items, context_query)
                operations.event("sticker", "sticker_selection_failed", {
                    "chat_title": incoming.chat_title,
                    "query": sticker,
                    "context_query": context_query,
                    "reason": reason,
                    "catalog_count": len(items),
                })
                self._send_auto_sticker_fallback(incoming, session, reason)
                return
            if len(candidates) == 1:
                selected = candidates[0]
                self._send_auto_sticker_request(
                    incoming,
                    session,
                    str(selected.get("Category") or selected.get("category") or ""),
                    sticker_item_send_value(selected),
                    sticker_item_display_name(selected),
                    "目录中只有一个匹配项",
                )
                return
            # Keep the prompt compact while retaining every currently scanned
            # semantic choice. Unlabelled visual hashes are listed as custom.
            candidates = candidates[:80]
            choices = "\n".join(
                f"{index}: {sticker_item_display_name(item)}"
                for index, item in enumerate(candidates)
            )
            messages = [{
                "role": "system",
                "content": (
                    "你只负责给微信对话选择一个最贴合语境的收藏或自定义表情包。"
                    "结合最近对话、当前消息和用户指定风格，从候选中选一个。"
                    "只返回候选编号，不要解释，不要输出其他字符。"
                ),
            }, {
                "role": "user",
                "content": (
                    f"最近对话：\n{self.memory.transcript(incoming.chat_title, max_chars=1800)}\n\n"
                    f"当前发送者：{incoming.who}\n当前消息：{incoming.content}\n"
                    f"指定风格：{sticker or '未指定，由语境决定'}\n\n候选：\n{choices}"
                ),
            }]
            future = self.model_executor.submit(
                self.model_client.generate,
                self._model_config(),
                messages,
                timeout=10,
            )
            self._finish_auto_sticker_choice(
                future,
                incoming,
                session,
                sticker,
                candidates,
                context_query,
            )

        if scan_future is None:
            scanned(GatewayResult(True, {"Items": cached_items}))
        else:
            self._run_future(scan_future, scanned)

    def _finish_auto_sticker_choice(
        self,
        future,
        incoming,
        session: int,
        query: str,
        candidates: list[dict[str, Any]],
        context_query: str = "",
    ) -> None:
        if not future.done():
            QTimer.singleShot(
                100,
                lambda: self._finish_auto_sticker_choice(
                    future,
                    incoming,
                    session,
                    query,
                    candidates,
                    context_query,
                ),
            )
            return
        if session != self._auto_chat_session or not self.auto_chat_running:
            MainWindow._release_auto_sticker(self, incoming.chat_title)
            self._finish_auto_message(incoming, success=False, error="自动聊天会话已停止")
            return
        offsets = getattr(self, "_sticker_selection_offsets", None)
        if offsets is None:
            offsets = {}
            self._sticker_selection_offsets = offsets
        key = f"{incoming.chat_title}\x00{query.casefold()}"
        selection_index = offsets.get(key, 0)
        source = "model"
        try:
            raw_choice = str(future.result()).strip()
            match = re.fullmatch(r"\s*(\d{1,3})\s*", raw_choice)
            if match is None:
                raise ValueError(f"模型返回了无效编号：{raw_choice[:80]}")
            candidate_index = int(match.group(1))
            if not 0 <= candidate_index < len(candidates):
                raise ValueError(f"模型编号越界：{candidate_index}")
            selected = candidates[candidate_index]
            reason = f"AI 根据对话选择候选 {candidate_index}"
        except Exception as exc:
            source = "local_fallback"
            selected, reason = select_sticker_item(
                candidates,
                context_query or query,
                selection_index=selection_index,
            )
            if selected is None:
                self._send_auto_sticker_fallback(incoming, session, reason)
                return
            operations.event("sticker", "sticker_model_choice_failed", {
                "chat_title": incoming.chat_title,
                "query": query,
                "error": f"{type(exc).__name__}: {exc}",
            })
        offsets[key] = selection_index + 1
        category = str(selected.get("Category") or selected.get("category") or "")
        send_value = sticker_item_send_value(selected)
        display_name = sticker_item_display_name(selected)
        mode = str(selected.get("Mode") or selected.get("mode") or "semantic")
        operations.event("sticker", "sticker_selection", {
            "chat_title": incoming.chat_title,
            "query": query,
            "context_query": context_query or query,
            "category": category,
            "sticker": display_name,
            "mode": mode,
            "reason": reason,
            "source": source,
            "selection_index": selection_index,
        })
        self._send_auto_sticker_request(
            incoming,
            session,
            category,
            send_value,
            display_name,
            reason,
        )

    def _send_auto_sticker_fallback(self, incoming, session: int, reason: str) -> None:
        MainWindow._release_auto_sticker(self, incoming.chat_title)
        message = "这会儿没找到合适的，先不乱发了"
        self._send_auto_text_segments(incoming, session, (message,), message)

    def _send_auto_sticker_request(
        self,
        incoming,
        session: int,
        category: str,
        sticker: str,
        display_name: str,
        selection_reason: str = "",
    ) -> None:
        options = build_options(
            "SendSticker",
            {"who": incoming.chat_title, "category": category, "sticker": sticker},
        )

        def sent(result: GatewayResult) -> None:
            if session != self._auto_chat_session or not result.ok or result.value is False:
                MainWindow._release_auto_sticker(self, incoming.chat_title)
                self._append_chat("自动聊天", f"表情包发送失败：{result.error or result.value}")
                self._finish_auto_message(
                    incoming,
                    success=False,
                    error=result.error or result.value,
                )
                return
            MainWindow._release_auto_sticker(self, incoming.chat_title, sent=True)
            self._auto_chat_last_reply[incoming.chat_title] = time.monotonic()
            self.memory.add_user(incoming.chat_title, incoming.who, incoming.content)
            memory_text = f"[表情包] {display_name}；选择原因：{selection_reason or '目录匹配'}"
            self.memory.add_assistant(incoming.chat_title, memory_text)
            self._schedule_personal_learning(incoming, memory_text)
            self._append_chat("自动回复", f"{incoming.chat_title}: 已发送表情包 {display_name}")
            self._finish_auto_message(incoming, result={
                "reply_kind": "sticker",
                "sticker": display_name,
                "category": category,
                "reason": selection_reason,
            })

        self._suppress_outgoing_media_preview(incoming.chat_title)
        self._run_future(self.gateway.call(self.account, "SendSticker", options), sent)

    def _fetch_latest_original_and_edit(
        self,
        incoming: IncomingMessage,
        edit_request: str = "",
    ) -> str:
        try:
            result = self.gateway.call(
                self.account,
                "GetLatestOriginalImage",
                {"who": incoming.chat_title},
            ).result(timeout=40)
        except Exception as exc:
            result = GatewayResult(False, error=f"{type(exc).__name__}: {exc}")
        source = None
        source_origin = ""
        if result.ok and isinstance(result.value, dict):
            payload = result.value
            image_file = str(payload.get("image_file") or payload.get("ImageFile") or "").strip()
            image_base64 = str(
                payload.get("image_base64_str")
                or payload.get("image_base64")
                or payload.get("imageBase64Str")
                or ""
            ).strip()
            candidates = ()
            if image_file:
                candidates = self.attachment_store.remember(
                    incoming.chat_title,
                    (IncomingAttachment(Path(image_file).name, image_file, "image"),),
                    received_at=incoming.send_date,
                )
            elif image_base64:
                candidates = self.attachment_store.remember(
                    incoming.chat_title,
                    (),
                    received_at=incoming.send_date,
                    image_base64=image_base64,
                    message_kind="image",
                )
            source = next((item for item in reversed(candidates) if item.kind == "image"), None)
            if source is not None:
                source_origin = "wechat_latest_original"

        if source is None:
            trusted = self.attachment_store.all(incoming.chat_title)
            source = next(
                (item for item in reversed(trusted) if item.kind == "image"),
                None,
            )
            if source is not None:
                source_origin = "private_attachment_store"
        if source is None:
            error = result.error if not result.ok else "当前聊天记录中没有提取到可复制的原图"
            raise RuntimeError(error)

        operations.event("attachment", "image_edit_source_resolved", {
            "chat_title": incoming.chat_title,
            "name": source.name,
            "kind": source.kind,
            "source": source_origin,
            "request": edit_request or incoming.content,
        })
        request = str(edit_request or incoming.content).strip()
        edit_prompt = (
            "严格基于输入原图进行局部编辑，保留原图的构图、人物、环境、光线、透视和"
            "未被要求修改的内容，只执行用户明确提出的变化。用户要求："
            + request
        )
        return self.model_client.edit_image(
            self._image_config(),
            edit_prompt,
            source.path,
        )

    def _finish_auto_image(self, future, incoming, session: int, *, mode: str = "generated") -> None:
        if not future.done():
            QTimer.singleShot(100, lambda: self._finish_auto_image(future, incoming, session, mode=mode))
            return
        if mode == "edited":
            self._original_image_fetch_count = max(
                0,
                getattr(self, "_original_image_fetch_count", 0) - 1,
            )
        if session != self._auto_chat_session or not self.auto_chat_running:
            self._finish_auto_message(incoming, success=False, error="自动聊天会话已停止")
            return
        try:
            image_path = str(future.result())
            options = build_options("SendFile", {"who": incoming.chat_title, "files": [image_path]})
        except Exception as exc:
            action_name = "改图" if mode == "edited" else "生图"
            self._append_chat("自动聊天", f"{action_name}失败：{exc}")
            self._finish_auto_message(incoming, success=False, error=exc)
            return

        def sent(result: GatewayResult) -> None:
            send_succeeded = result.ok and result.value is not False
            if not send_succeeded:
                self._message_cursor.cancel_outgoing_media(incoming.chat_title, "[图片]")
            if session != self._auto_chat_session or not send_succeeded:
                self._append_chat("自动聊天", f"图片发送失败：{result.error or result.value}")
                self._finish_auto_message(
                    incoming,
                    success=False,
                    error=result.error or result.value,
                )
                return
            self._auto_chat_last_reply[incoming.chat_title] = time.monotonic()
            memory_text = "[已修改并发送图片]" if mode == "edited" else "[已生成并发送图片]"
            if mode == "edited":
                MainWindow._clear_pending_image_edit(self, incoming.chat_title)
            self.memory.add_assistant(incoming.chat_title, memory_text)
            self._schedule_personal_learning(incoming, memory_text)
            action_name = "修改图片" if mode == "edited" else "生成图片"
            self._append_chat("自动回复", f"{incoming.chat_title}: 已发送{action_name}")
            self._finish_auto_message(
                incoming,
                result={"reply_kind": "image_edit" if mode == "edited" else "image"},
            )

        self._suppress_outgoing_media_preview(incoming.chat_title)
        self._message_cursor.record_outgoing_media(incoming.chat_title, "[图片]")
        self._run_future(self.gateway.call(self.account, "SendFile", options), sent)

    def _schedule_personal_learning(self, incoming, assistant_reply: str) -> None:
        if not self.personal_memory_enabled.isChecked() or not incoming.content.strip():
            return
        is_group = incoming.chat_title in self._auto_chat_groups
        memory_name = person_id(
            incoming.chat_title,
            incoming.who,
            is_group,
            self.personal_memory_aliases,
        )
        if not memory_name or memory_name in {"对方", "系统", "我"}:
            return
        try:
            self.episodic_memory_store.add(memory_name, incoming.content, assistant_reply)
        except Exception as exc:
            self._append_chat("情景记忆", f"{memory_name} 的互动记录失败：{exc}")
        future = self.learning_executor.submit(
            self.personal_memory_learner.learn,
            primary=self._model_config(),
            backup=self._backup_model_config(),
            name=memory_name,
            user_message=incoming.content,
            assistant_reply=assistant_reply,
        )

        def poll() -> None:
            if not future.done():
                QTimer.singleShot(250, poll)
                return
            try:
                learned = future.result()
                self._update_personal_memory_status(f"刚更新 {memory_name}")
                operations.event("workflow", "personal_memory_ready", {
                    "person": memory_name,
                    "message_count": learned.message_count,
                })
            except Exception as exc:
                self._update_personal_memory_status("最近学习失败")
                self._append_chat("个人记忆", f"{memory_name} 的档案更新失败：{exc}")

        QTimer.singleShot(250, poll)

    def _finish_auto_message(
        self,
        incoming: Any,
        *,
        success: bool = True,
        result: Any = None,
        error: Any = None,
    ) -> None:
        chat_title = str(
            incoming if isinstance(incoming, str) else getattr(incoming, "chat_title", "")
        )
        task_key = chat_title if isinstance(incoming, str) else MainWindow._auto_task_key(incoming)
        span = self._auto_reply_spans.pop(task_key, None)
        if span is not None:
            operations.finish(span, success=success, result=result, error=error)
        active_tasks = getattr(self, "_auto_chat_active_tasks", set())
        was_active = task_key in active_tasks
        active_tasks.discard(task_key)
        pending = self._auto_chat_pending
        if isinstance(pending, dict):
            if was_active:
                remaining = max(0, int(pending.get(chat_title, 0)) - 1)
                if remaining:
                    pending[chat_title] = remaining
                else:
                    pending.pop(chat_title, None)
        else:
            pending.discard(chat_title)
        QTimer.singleShot(0, lambda: self._process_next_auto_message(chat_title))

    def _refresh_test_targets(self) -> None:
        if not self.gateway.connected:
            return

        def loaded(result: GatewayResult) -> None:
            if not result.ok or not isinstance(result.value, list):
                return
            current = self.test_target.currentText()
            self.test_target.clear()
            self.test_target.addItems([str(item) for item in result.value])
            if current:
                self.test_target.setEditText(current)

        self._run_future(self.gateway.call(self.account, "GetAllChatGroups", ""), loaded)

    def _run_safe_tests(self) -> None:
        target = self.test_target.currentText().strip()
        tests: list[tuple[str, dict[str, Any]]] = [
            ("GetOwerInfo", {}),
            ("GetVisibleConversations", {}),
            ("GetAllConversations", {}),
            ("GetAllChatGroups", {}),
            ("GetAllFriendNames", {}),
            ("GetTitle", {}),
            ("Max", {}),
            ("Restore", {}),
            ("OpenMoments", {}),
            ("CloseMoments", {}),
        ]
        if target:
            tests.extend([
                ("SearchFriend", {"who": target}),
                ("GetChatGroupMemberList", {"group_name": target}),
                ("GetGroupOwner", {"group_name": target}),
                ("IsOwnerChatGroup", {"group_name": target}),
            ])
        self._start_tests(tests)

    def _run_auto_chat_loop_test(self) -> None:
        selected = sorted(self._selected_auto_chat_targets())
        target = selected[0] if selected else self.test_target.currentText().strip()
        content = self.test_message.text().strip()
        if not self.auto_chat_running:
            QMessageBox.warning(self, "自动聊天未运行", "请先勾选同一目标并开始自动聊天。")
            return
        if not target or target not in self._selected_auto_chat_targets():
            QMessageBox.warning(self, "目标未接管", "测试目标必须是当前已勾选并接管的会话。")
            return
        if not content:
            QMessageBox.warning(self, "测试文本为空", "请输入要模拟的入站消息。")
            return
        stamp = datetime.now().isoformat(timespec="seconds")
        self._append_chat("闭环测试", f"模拟入站：{target} · 测试联系人: {content}")
        self._accept_auto_message(
            IncomingMessage(
                chat_title=target,
                who="测试联系人",
                content=content,
                send_date=f"loop-test-{stamp}",
            )
        )

    def _scan_all_stickers(self) -> None:
        self._append_chat("表情包", "开始扫描全部表情分类，结果将在测试模块中显示")
        self._start_tests([("ScanAllStickers", {})])

    def _run_full_tests(self) -> None:
        target = self.test_target.currentText().strip()
        file_path = self.test_file.text().strip()
        marker = self.test_message.text().strip() or "[MyBot2.0] 自动化回归测试"
        if not target:
            QMessageBox.warning(self, "缺少参数", "请选择测试目标。")
            return
        if not Path(file_path).exists():
            QMessageBox.warning(self, "文件不存在", file_path)
            return
        tests = [
            ("SearchFriend", {"who": target}),
            ("ScanAllStickers", {}),
            ("SendMessage", {"who": target, "message": marker}),
            ("SendEmoji", {"who": target, "emoji": "微笑"}),
            ("SendFile", {"who": target, "files": [file_path]}),
            ("SetTopMost", {"who": target, "setting": True}),
            ("SetTopMost", {"who": target, "setting": False}),
            ("AddMoments", {"content": marker, "images": [file_path]}),
            ("RemoveMoments", {"content": marker}),
        ]
        self._start_tests(tests)

    def _start_tests(self, tests: list[tuple[str, dict[str, Any]]]) -> None:
        if not self.gateway.connected:
            span = operations.start("workflow", "test_suite", details={"test_count": len(tests)})
            operations.finish(span, success=False, error="WebSocket Server 未连接")
            QMessageBox.warning(self, "未连接", "请先连接 WebSocket Server。")
            return
        if self._test_span is not None:
            operations.finish(self._test_span, success=False, error="被新的测试任务替换")
        self._test_span = operations.start(
            "workflow",
            "test_suite",
            details={
                "account": self.account,
                "tests": [{"function": function, "args": args} for function, args in tests],
            },
        )
        self._test_queue = list(tests)
        self._test_total = len(tests)
        self._test_index = 0
        self._test_failed = 0
        self.test_table.setRowCount(0)
        self.test_progress.setMaximum(max(1, len(tests)))
        self.test_progress.setValue(0)
        self._run_next_test()

    def _run_next_test(self) -> None:
        if not self._test_queue:
            self.statusBar().showMessage(f"测试完成：{self._test_total} 项", 8000)
            if self._test_span is not None:
                operations.finish(
                    self._test_span,
                    success=self._test_failed == 0,
                    result={
                        "total": self._test_total,
                        "passed": self._test_total - self._test_failed,
                        "failed": self._test_failed,
                    },
                    error=None if self._test_failed == 0 else f"{self._test_failed} 项测试失败",
                )
                self._test_span = None
            return
        function, args = self._test_queue.pop(0)
        row = self.test_table.rowCount()
        self.test_table.insertRow(row)
        self.test_table.setItem(row, 0, QTableWidgetItem(f"{TOOL_MAP[function].name} ({function})"))
        self.test_table.setItem(row, 1, QTableWidgetItem("运行中"))
        self.test_table.setItem(row, 3, QTableWidgetItem(self._format_value(args, 300)))
        started = datetime.now()
        try:
            options = build_options(function, args)
        except Exception as exc:
            self._finish_test_row(row, started, False, str(exc))
            return

        def done(result: GatewayResult) -> None:
            passed = self._tool_succeeded(function, result)
            self._finish_test_row(row, started, passed, result.value if result.ok else result.error)

        self._run_future(self.gateway.call(self.account, function, options), done)

    def _finish_test_row(self, row: int, started: datetime, passed: bool, value: Any) -> None:
        elapsed = (datetime.now() - started).total_seconds()
        self.test_table.setItem(row, 1, QTableWidgetItem("通过" if passed else "失败"))
        self.test_table.setItem(row, 2, QTableWidgetItem(f"{elapsed:.1f}s"))
        self.test_table.setItem(row, 4, QTableWidgetItem(self._format_value(value, 500)))
        self._test_index += 1
        if not passed:
            self._test_failed += 1
        self.test_progress.setValue(self._test_index)
        QTimer.singleShot(120, self._run_next_test)

    @staticmethod
    def _tool_succeeded(function: str, result: GatewayResult) -> bool:
        if not result.ok:
            return False
        # Predicate queries can legitimately return false without indicating
        # a transport or execution failure.
        return result.value is not False or function in {"IsOwnerChatGroup"}
