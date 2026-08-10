from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .api import Gateway, GatewayResult, encode_upload


def button(text: str, slot: Callable, primary: bool = False) -> QPushButton:
    item = QPushButton(text)
    item.setObjectName("primary" if primary else "")
    item.clicked.connect(slot)
    return item


def label(text: str, object_name: str = "") -> QLabel:
    item = QLabel(text)
    if object_name:
        item.setObjectName(object_name)
    return item


def card(title: str, body: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet("QFrame#card { background: #141d28; border: 1px solid #253241; border-radius: 8px; }")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 15, 18, 15)
    layout.setSpacing(10)
    layout.addWidget(label(title, "sectionTitle"))
    if body:
        layout.addWidget(body)
    return frame, layout


class MainWindow(QMainWindow):
    status_changed = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MyBot 2.0 · WeChat Automation Console")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 700)
        self.gateway = Gateway()
        self.gateway.add_listener(self._gateway_event)
        self.account = "演示账号"
        self.logs: list[str] = []
        self._auto_reply_last: dict[str, float] = {}
        self._nav_buttons: list[QPushButton] = []
        self._pages = QStackedWidget()
        self._build_shell()
        self._build_pages()
        self._select_page(0)
        self._log("前端已启动，当前为演示模式")
        self._refresh_overview()
        QTimer.singleShot(350, self._connect)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.gateway.close()
        event.accept()

    def _build_shell(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 18, 18)
        side.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_row.addWidget(label("MyBot", "brand"))
        brand_row.addWidget(label("2.0", "muted"), 0, Qt.AlignBottom)
        side.addLayout(brand_row)
        side.addWidget(label("WECHAT AUTOMATION", "muted"))
        side.addSpacing(16)
        nav_items = [("总览", "概览"), ("消息中心", "消息"), ("通讯录", "通讯录"), ("群管理", "群管理"), ("朋友圈", "朋友圈"), ("监听中心", "监听"), ("系统设置", "设置")]
        for index, (title, page) in enumerate(nav_items):
            nav = QPushButton(f"  {title}")
            nav.setObjectName("nav")
            nav.setCheckable(True)
            nav.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            self._nav_buttons.append(nav)
            side.addWidget(nav)
        side.addStretch()
        side.addWidget(label("服务端连接", "muted"))
        self.sidebar_status = label("● 演示模式", "muted")
        self.sidebar_status.setStyleSheet("color: #eab34c;")
        side.addWidget(self.sidebar_status)
        side.addWidget(label("PySide6 · WebSocket", "muted"))
        root_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content, 1)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(24, 13, 24, 13)
        top_layout.addWidget(label("控制台", "pageTitle"))
        top_layout.addStretch()
        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(180)
        self.account_combo.addItem(self.account)
        self.account_combo.currentTextChanged.connect(self._account_changed)
        top_layout.addWidget(label("微信账号", "muted"))
        top_layout.addWidget(self.account_combo)
        self.uri_input = QLineEdit("ws://127.0.0.1:5177/ws")
        self.uri_input.setMinimumWidth(250)
        self.uri_input.setToolTip("WeChatAuto4_X WebSocket Server 地址")
        top_layout.addWidget(self.uri_input)
        self.connect_btn = button("连接", self._connect, True)
        top_layout.addWidget(self.connect_btn)
        content_layout.addWidget(topbar)
        content_layout.addWidget(self._pages, 1)
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪")

    def _build_pages(self) -> None:
        self._pages.addWidget(self._overview_page())
        self._pages.addWidget(self._messaging_page())
        self._pages.addWidget(self._contacts_page())
        self._pages.addWidget(self._groups_page())
        self._pages.addWidget(self._moments_page())
        self._pages.addWidget(self._monitor_page())
        self._pages.addWidget(self._settings_page())

    def _select_page(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        for i, nav in enumerate(self._nav_buttons):
            nav.setChecked(i == index)

    def _account_changed(self, value: str) -> None:
        if value:
            self.account = value
            self._log(f"已切换账号：{value}")

    def _connect(self) -> None:
        if self.gateway.connected:
            self._run(self.gateway.disconnect(), lambda _: self._set_connection(False, "已断开"))
            return
        self.connect_btn.setEnabled(False)
        self.status_bar.showMessage("正在连接 WebSocket Server …")
        self._run(self.gateway.connect(self.uri_input.text().strip()), self._connection_result)

    def _connection_result(self, result: GatewayResult) -> None:
        self.connect_btn.setEnabled(True)
        if result.ok:
            self.account_combo.blockSignals(True)
            self.account_combo.clear()
            self.account_combo.addItems(self.gateway.clients)
            self.account_combo.blockSignals(False)
            if self.gateway.clients:
                self.account = self.gateway.clients[0]
            if hasattr(self, "overview_online_count"):
                self.overview_online_count.setText(str(len(self.gateway.clients)))
            self._set_connection(True, f"已连接 {self.gateway.uri}")
        else:
            self._set_connection(False, result.error or "连接失败，已切换演示模式")
        self._refresh_overview(refresh_groups=result.ok)

    def _set_connection(self, connected: bool, message: str) -> None:
        self.gateway.connected = connected
        self.connect_btn.setText("断开" if connected else "连接")
        if connected:
            self.sidebar_status.setText("● 已连接")
            self.sidebar_status.setStyleSheet("color: #58d69b;")
        else:
            self.sidebar_status.setText("● 演示模式")
            self.sidebar_status.setStyleSheet("color: #eab34c;")
        self.status_bar.showMessage(message, 5000)
        self._log(message)

    def _run(self, future, callback: Callable[[GatewayResult], None]) -> None:
        def poll() -> None:
            if future.done():
                try:
                    callback(future.result())
                except Exception as exc:  # pragma: no cover - defensive UI guard
                    self._error(str(exc))
                return
            QTimer.singleShot(60, poll)

        poll()

    def _call(self, function: str, options: Any = "", callback: Callable[[Any], None] | None = None) -> None:
        def finish(result: GatewayResult) -> None:
            if not result.ok:
                self._error(result.error)
                return
            self._log(f"执行 {function}")
            if result.value is False:
                self._error(f"{function} 执行失败")
                return
            if callback:
                callback(result.value)

        self._run(self.gateway.call(self.account, function, options), finish)

    def _error(self, message: str) -> None:
        self._log(f"错误：{message}")
        self.status_bar.showMessage(message, 6000)

    def _log(self, message: str) -> None:
        stamp = __import__("datetime").datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"{stamp}  {message}")
        if len(self.logs) > 200:
            self.logs.pop(0)
        if hasattr(self, "activity_log"):
            self.activity_log.setPlainText("\n".join(reversed(self.logs[-30:])))

    def _gateway_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "connection_error":
            self._log(f"服务端连接异常：{event.get('data', '')}")
        elif event.get("type") == "echo":
            self._log("收到服务端监听事件")

    def _refresh_overview(self, refresh_groups: bool = False) -> None:
        callback = self._overview_conversations_then_groups if refresh_groups else self._overview_conversations
        self._call("GetVisibleConversations", "", callback)

    def _overview_conversations_then_groups(self, conversations: Any) -> None:
        self._overview_conversations(conversations)
        if hasattr(self, "group_name"):
            self._load_groups()

    def _overview_conversations(self, conversations: Any) -> None:
        if not isinstance(conversations, list):
            return
        self.overview_conversation_count.setText(str(len(conversations)))
        self.overview_unread_count.setText(str(sum(self._conversation_unread(x) for x in conversations)))
        self.overview_list.clear()
        for item in conversations[:6]:
            if isinstance(item, dict):
                title = self._conversation_title(item)
                unread = self._conversation_unread(item)
            else:
                title, unread = str(item), 0
            self.overview_list.addItem(f"{title}   {'● ' + str(unread) if unread else ''}")

    @staticmethod
    def _conversation_title(item: dict[str, Any]) -> str:
        return str(item.get("title") or item.get("conversation_title") or item.get("name") or "未知会话")

    @staticmethod
    def _conversation_unread(item: Any) -> int:
        if not isinstance(item, dict):
            return 0
        value = item.get("unreadCount", item.get("not_read_numbr", 0))
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _overview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(18)
        intro = QHBoxLayout()
        intro.addWidget(label("运行总览", "pageTitle"))
        intro.addWidget(label("管理多个微信实例，编排日常消息与社交自动化", "muted"), 0, Qt.AlignBottom)
        intro.addStretch()
        intro.addWidget(button("刷新数据", self._refresh_overview))
        layout.addLayout(intro)

        metrics = QGridLayout()
        metrics.setSpacing(14)
        metric_specs = [("在线微信", "1", "当前可控制的客户端"), ("会话总数", "0", "包含好友与群聊"), ("未读消息", "0", "可从监听中心处理"), ("运行状态", "正常", "UI 与网关线程")]
        self.overview_conversation_count = None
        for index, (title, value, hint) in enumerate(metric_specs):
            frame = QFrame()
            frame.setObjectName("card")
            frame.setStyleSheet("QFrame#card { background: #141d28; border: 1px solid #253241; border-radius: 8px; }")
            box = QVBoxLayout(frame)
            box.setContentsMargins(17, 14, 17, 14)
            box.addWidget(label(title, "muted"))
            value_label = label(value)
            value_label.setFont(QFont("Segoe UI", 25, QFont.Bold))
            value_label.setStyleSheet("color: #f4f8fc;")
            box.addWidget(value_label)
            box.addWidget(label(hint, "muted"))
            metrics.addWidget(frame, 0, index)
            if title == "在线微信":
                self.overview_online_count = value_label
            elif title == "会话总数":
                self.overview_conversation_count = value_label
            elif title == "未读消息":
                self.overview_unread_count = value_label
        layout.addLayout(metrics)

        body = QHBoxLayout()
        body.setSpacing(14)
        left, left_box = card("快捷操作")
        actions = QGridLayout()
        actions.setSpacing(10)
        for i, (text, page_index) in enumerate([("发送消息", 1), ("查看通讯录", 2), ("群管理", 3), ("启动监听", 5)]):
            actions.addWidget(button(text, lambda checked=False, p=page_index: self._select_page(p)), i // 2, i % 2)
        left_box.addLayout(actions)
        left_box.addWidget(label("常用入口会根据当前账号执行操作。真实服务端连接后，演示数据将自动替换。", "muted"))
        body.addWidget(left, 1)
        right, right_box = card("最近会话")
        self.overview_list = QListWidget()
        right_box.addWidget(self.overview_list)
        body.addWidget(right, 1)
        layout.addLayout(body, 1)

        log_card, log_box = card("活动日志")
        self.activity_log = QPlainTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumHeight(150)
        log_box.addWidget(self.activity_log)
        layout.addWidget(log_card)
        return page

    def _messaging_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)
        title_row = QHBoxLayout()
        title_row.addWidget(label("消息中心", "pageTitle"))
        title_row.addWidget(label("文本、文件、表情、语音和历史消息", "muted"), 0, Qt.AlignBottom)
        title_row.addStretch()
        title_row.addWidget(button("刷新会话", self._load_conversations))
        layout.addLayout(title_row)
        body = QHBoxLayout()
        body.setSpacing(14)
        conv_card, conv_box = card("会话列表")
        self.conversation_search = QLineEdit()
        self.conversation_search.setPlaceholderText("搜索好友或群聊")
        self.conversation_search.textChanged.connect(self._filter_conversations)
        conv_box.addWidget(self.conversation_search)
        self.conversation_list = QListWidget()
        self.conversation_list.currentTextChanged.connect(self._conversation_selected)
        conv_box.addWidget(self.conversation_list, 1)
        body.addWidget(conv_card, 1)
        chat_card, chat_box = card("聊天工作区")
        chat_head = QHBoxLayout()
        self.chat_target = QLineEdit()
        self.chat_target.setPlaceholderText("好友/群聊名称，留空表示当前窗口")
        chat_head.addWidget(self.chat_target, 1)
        chat_head.addWidget(button("读取历史", self._load_history))
        chat_box.addLayout(chat_head)
        self.history_view = QPlainTextEdit()
        self.history_view.setReadOnly(True)
        chat_box.addWidget(self.history_view, 1)
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("输入要发送的消息… 支持群聊 @提醒")
        self.message_input.setMaximumHeight(100)
        chat_box.addWidget(self.message_input)
        send_row = QHBoxLayout()
        self.at_input = QLineEdit()
        self.at_input.setPlaceholderText("@对象，多个用逗号分隔")
        send_row.addWidget(self.at_input, 1)
        send_row.addWidget(button("发送文字", self._send_message, True))
        send_row.addWidget(button("发送文件", self._send_file))
        send_row.addWidget(button("发送语音", self._send_voice))
        send_row.addWidget(button("表情", self._send_emoji))
        chat_box.addLayout(send_row)
        action_row = QHBoxLayout()
        action_row.addWidget(button("语音通话", self._voice_chat))
        action_row.addWidget(button("视频通话", self._video_chat))
        action_row.addWidget(button("拍一拍", self._tap_user))
        action_row.addWidget(button("转发最近 5 条", self._forward_recent))
        action_row.addWidget(button("会话置顶", lambda: self._set_conversation_flag("SetTopMost", True)))
        action_row.addWidget(button("免打扰", lambda: self._set_conversation_flag("SetDoNotDisturb", True)))
        action_row.addStretch()
        chat_box.addLayout(action_row)
        body.addWidget(chat_card, 2)
        layout.addLayout(body, 1)
        return page

    def _load_conversations(self) -> None:
        self._call("GetVisibleConversations", "", self._set_conversations)

    def _set_conversations(self, items: Any) -> None:
        self.conversation_list.clear()
        for item in items or []:
            title = self._conversation_title(item) if isinstance(item, dict) else str(item)
            row = QListWidgetItem(title)
            row.setData(Qt.UserRole, title)
            self.conversation_list.addItem(row)
        self._filter_conversations(self.conversation_search.text())

    def _filter_conversations(self, text: str) -> None:
        for index in range(self.conversation_list.count()):
            item = self.conversation_list.item(index)
            item.setHidden(bool(text.strip()) and text.strip().lower() not in item.text().lower())

    def _conversation_selected(self, target: str) -> None:
        if target:
            self.chat_target.setText(target)
            self._load_history()

    def _load_history(self) -> None:
        target = self.chat_target.text().strip() or None
        function = "GetChatHistory_Who" if target else "GetChatHistory_Current_Window"
        options = {"who": target, "fetch_date": date.today().isoformat()} if target else date.today().isoformat()
        self._call(function, options, self._set_history)

    def _set_history(self, items: Any) -> None:
        lines = []
        for item in items or []:
            if isinstance(item, dict):
                timestamp = item.get("time") or item.get("send_date_time") or item.get("date_time") or "--:--"
                sender = item.get("sender") or item.get("who") or "未知"
                content = item.get("content") or item.get("message") or ""
                lines.append(f"[{timestamp}] {sender}: {content}")
            else:
                lines.append(str(item))
        self.history_view.setPlainText("\n".join(lines) or "暂无消息")

    def _send_message(self) -> None:
        message = self.message_input.toPlainText().strip()
        if not message:
            return self._error("消息内容不能为空")
        ats = [x.strip() for x in self.at_input.text().split(",") if x.strip()]
        options = {"who": self.chat_target.text().strip(), "message": message, "atUser": json.dumps(ats, ensure_ascii=False), "refer": "null"}
        self._call("SendMessage", options, lambda _: self._after_send(message))

    def _after_send(self, message: str) -> None:
        self.history_view.appendPlainText(f"[刚刚] 我: {message}")
        self.message_input.clear()

    def _send_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择要发送的文件")
        if not files:
            return
        uploads = {path: encode_upload(path) for path in files}
        self._call("SendFile", {"who": self.chat_target.text().strip(), "files": json.dumps(files), "upload": json.dumps(uploads)})

    def _send_voice(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择语音文件", filter="Audio (*.wav *.mp3 *.pcm)")
        if path:
            self._call("SendVoiceMessage", {"who": self.chat_target.text().strip(), "filePath": path, "upload": encode_upload(path)})

    def _send_emoji(self) -> None:
        self._call("SendEmoji", {"who": self.chat_target.text().strip(), "emoji": "微笑", "atUser": "[]"})

    def _voice_chat(self) -> None:
        self._call("SendVoiceChat", self.chat_target.text().strip())

    def _video_chat(self) -> None:
        self._call("SendVedioChat", self.chat_target.text().strip())

    def _tap_user(self) -> None:
        target = self.chat_target.text().strip()
        if target:
            self._call("TapWho", {"who": target, "prev_scroll_number": 30})

    def _forward_recent(self) -> None:
        target = self.chat_target.text().strip()
        recipients = [x.strip() for x in self.at_input.text().split(",") if x.strip()]
        if target and recipients:
            self._call("ForwardMultipleMessage", {"who": target, "to": json.dumps(recipients, ensure_ascii=False), "f_type": "ForwardMerge", "row_count": 5})
        elif target:
            self._error("请在 @对象 输入框中填写转发目标")

    def _set_conversation_flag(self, function: str, setting: bool) -> None:
        self._call(function, {"who": self.chat_target.text().strip(), "setting": setting})

    def _contacts_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(label("通讯录", "pageTitle"))
        row.addWidget(label("好友查询、添加和管理", "muted"), 0, Qt.AlignBottom)
        row.addStretch()
        row.addWidget(button("刷新通讯录", self._load_contacts))
        layout.addLayout(row)
        toolbar = QHBoxLayout()
        self.contact_search = QLineEdit()
        self.contact_search.setPlaceholderText("筛选昵称 / 备注 / wxid")
        self.contact_search.textChanged.connect(self._filter_contacts)
        toolbar.addWidget(self.contact_search, 1)
        self.contact_name = QLineEdit()
        self.contact_name.setPlaceholderText("要添加的微信号或手机号")
        toolbar.addWidget(self.contact_name, 1)
        toolbar.addWidget(button("添加好友", self._add_friend, True))
        layout.addLayout(toolbar)
        self.contact_table = QTableWidget(0, 4)
        self.contact_table.setHorizontalHeaderLabels(["昵称", "备注", "微信 ID", "操作"])
        self.contact_table.horizontalHeader().setStretchLastSection(True)
        self.contact_table.setAlternatingRowColors(True)
        layout.addWidget(self.contact_table, 1)
        return page

    def _load_contacts(self) -> None:
        # GetAllFriends on some server builds tries to read an empty avatar path.
        # Names are sufficient for the contact workflow and work across builds.
        self._call("GetAllFriendNames", "", self._set_contacts)

    def _set_contacts(self, contacts: Any) -> None:
        self.contact_table.setRowCount(0)
        for contact in contacts or []:
            if not isinstance(contact, dict):
                contact = {"nickName": str(contact)}
            row = self.contact_table.rowCount()
            self.contact_table.insertRow(row)
            nickname = contact.get("nickName") or contact.get("nick_name") or contact.get("nickname") or contact.get("name") or ""
            memo = contact.get("remark") or contact.get("memo_name") or ""
            wxid = contact.get("wxid") or contact.get("wx_id") or ""
            self.contact_table.setItem(row, 0, QTableWidgetItem(str(nickname)))
            self.contact_table.setItem(row, 1, QTableWidgetItem(str(memo)))
            self.contact_table.setItem(row, 2, QTableWidgetItem(str(wxid)))
            remove = button("删除", lambda checked=False, n=str(nickname): self._remove_friend(n))
            self.contact_table.setCellWidget(row, 3, remove)
        self._filter_contacts(self.contact_search.text())

    def _filter_contacts(self, text: str) -> None:
        query = text.strip().lower()
        for row in range(self.contact_table.rowCount()):
            values = [self.contact_table.item(row, col).text().lower() for col in range(3) if self.contact_table.item(row, col)]
            self.contact_table.setRowHidden(row, bool(query) and not any(query in value for value in values))

    def _add_friend(self) -> None:
        name = self.contact_name.text().strip()
        if name:
            options = {"interval_time": 5, "is_close_win": True, "say_hi": "", "suffix": "", "label": ""}
            self._call("AddFriends", {"friends": json.dumps([name], ensure_ascii=False), "options": json.dumps(options)}, lambda _: self._log(f"已提交好友申请：{name}"))

    def _remove_friend(self, name: str) -> None:
        if QMessageBox.question(self, "确认删除", f"确认删除好友「{name}」？") == QMessageBox.Yes:
            self._call("RemoveFriend", name, lambda _: self._load_contacts())

    def _groups_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(label("群管理", "pageTitle"))
        row.addWidget(label("成员、群名、备注与公告", "muted"), 0, Qt.AlignBottom)
        row.addStretch()
        layout.addLayout(row)
        top, top_box = card("目标群聊")
        line = QHBoxLayout()
        self.group_name = QComboBox()
        self.group_name.setEditable(True)
        self.group_name.setInsertPolicy(QComboBox.NoInsert)
        self.group_name.lineEdit().setPlaceholderText("选择或输入群聊名称")
        line.addWidget(self.group_name, 1)
        self.group_refresh_btn = button("刷新群聊", self._load_groups)
        line.addWidget(self.group_refresh_btn)
        line.addWidget(button("读取成员", self._load_group_members, True))
        line.addWidget(button("获取群主", self._get_group_owner))
        top_box.addLayout(line)
        layout.addWidget(top)
        body = QHBoxLayout()
        member_card, member_box = card("群成员")
        self.group_members = QListWidget()
        member_box.addWidget(self.group_members)
        body.addWidget(member_card, 1)
        ops, ops_box = card("群操作")
        form = QGridLayout()
        self.new_group_name = QLineEdit()
        self.new_group_name.setPlaceholderText("新群名称")
        self.group_notice = QTextEdit()
        self.group_notice.setPlaceholderText("群公告内容")
        self.group_notice.setMaximumHeight(110)
        self.group_nick = QLineEdit()
        self.group_nick.setPlaceholderText("我在本群的昵称")
        form.addWidget(label("修改群名", "muted"), 0, 0)
        form.addWidget(self.new_group_name, 0, 1)
        form.addWidget(button("保存", self._rename_group), 0, 2)
        form.addWidget(label("群内昵称", "muted"), 1, 0)
        form.addWidget(self.group_nick, 1, 1)
        form.addWidget(button("保存", self._rename_self), 1, 2)
        form.addWidget(label("群公告", "muted"), 2, 0)
        form.addWidget(self.group_notice, 2, 1, 1, 2)
        form.addWidget(button("发布公告", self._update_notice, True), 3, 1, 1, 2)
        form.addWidget(button("退出群聊", self._quit_group), 4, 1, 1, 2)
        ops_box.addLayout(form)
        extra = QHBoxLayout()
        self.group_members_input = QLineEdit()
        self.group_members_input.setPlaceholderText("成员昵称，多个用逗号分隔")
        extra.addWidget(self.group_members_input, 1)
        extra.addWidget(button("添加成员", self._add_group_members))
        extra.addWidget(button("移除成员", self._remove_group_members))
        extra.addWidget(button("邀请成员", self._invite_group_members))
        ops_box.addLayout(extra)
        self.group_result = label("选择一个群聊开始操作", "muted")
        ops_box.addWidget(self.group_result)
        body.addWidget(ops, 2)
        layout.addLayout(body, 1)
        return page

    def _load_groups(self) -> None:
        self.group_refresh_btn.setEnabled(False)

        def apply_groups(groups: Any) -> None:
            current = self._group_option()
            names = [str(name).strip() for name in (groups or []) if str(name).strip()]
            self.group_name.blockSignals(True)
            self.group_name.clear()
            self.group_name.addItems(names)
            self.group_name.setEditText(current if current else (names[0] if names else ""))
            self.group_name.blockSignals(False)
            self.group_refresh_btn.setEnabled(True)
            self.group_result.setText(f"已自动检索 {len(names)} 个群聊")

        self._call("GetAllChatGroups", "", apply_groups)

    def _group_option(self) -> str:
        return self.group_name.currentText().strip()

    def _load_group_members(self) -> None:
        self._call("GetChatGroupMemberList", self._group_option(), self._set_group_members)

    def _set_group_members(self, members: Any) -> None:
        self.group_members.clear()
        for name in members or []:
            self.group_members.addItem(str(name))
        self.group_result.setText(f"共 {len(members or [])} 位成员")

    def _get_group_owner(self) -> None:
        self._call("GetGroupOwner", self._group_option(), lambda value: self.group_result.setText(f"群主：{value}"))

    def _rename_group(self) -> None:
        self._call("ChangeOwnerChatGroupName", {"old_group_name": self._group_option(), "new_group_name": self.new_group_name.text().strip()})

    def _rename_self(self) -> None:
        self._call("ChangeChatGroupNickName", {"group_name": self._group_option(), "nick_name": self.group_nick.text().strip()})

    def _update_notice(self) -> None:
        self._call("UpdateGroupNotice", {"group_name": self._group_option(), "group_notice": self.group_notice.toPlainText()})

    def _member_options(self) -> list[str]:
        return [x.strip() for x in self.group_members_input.text().split(",") if x.strip()]

    def _add_group_members(self) -> None:
        members = self._member_options()
        if members:
            self._call("AddOwnerChatGroupMember", {"group_name": self._group_option(), "member_name": json.dumps(members, ensure_ascii=False)})

    def _remove_group_members(self) -> None:
        members = self._member_options()
        if members:
            self._call("RemoveOwnerChatGroupMember", {"group_name": self._group_option(), "member_name": json.dumps(members, ensure_ascii=False)})

    def _invite_group_members(self) -> None:
        members = self._member_options()
        if members:
            self._call("InviteChatGroupMember", {"group_name": self._group_option(), "members": json.dumps(members, ensure_ascii=False), "invite_reason_if_need": ""})

    def _quit_group(self) -> None:
        if self._group_option() and QMessageBox.question(self, "确认退出", f"确认退出「{self._group_option()}」？") == QMessageBox.Yes:
            self._call("QuitChatGroup", {"group_name": self._group_option(), "clear_history": True})

    def _moments_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(label("朋友圈", "pageTitle"))
        row.addWidget(label("发布和清理自己的朋友圈内容", "muted"), 0, Qt.AlignBottom)
        row.addStretch()
        row.addWidget(button("打开朋友圈", lambda: self._call("OpenMoments")))
        row.addWidget(button("关闭窗口", lambda: self._call("CloseMoments")))
        layout.addLayout(row)
        publish, publish_box = card("发布朋友圈")
        self.moment_content = QTextEdit()
        self.moment_content.setPlaceholderText("写下这一刻…")
        self.moment_content.setMaximumHeight(170)
        publish_box.addWidget(self.moment_content)
        image_row = QHBoxLayout()
        self.moment_images = QLineEdit()
        self.moment_images.setPlaceholderText("图片路径，多个路径用分号分隔")
        image_row.addWidget(self.moment_images, 1)
        image_row.addWidget(button("选择图片", self._choose_moment_images))
        image_row.addWidget(button("发布", self._publish_moment, True))
        publish_box.addLayout(image_row)
        layout.addWidget(publish)
        remove, remove_box = card("删除朋友圈")
        remove_row = QHBoxLayout()
        self.remove_moment_content = QLineEdit()
        self.remove_moment_content.setPlaceholderText("输入要删除的朋友圈文字内容")
        remove_row.addWidget(self.remove_moment_content, 1)
        remove_row.addWidget(button("删除", self._remove_moment))
        remove_box.addLayout(remove_row)
        layout.addWidget(remove)
        layout.addStretch()
        return page

    def _choose_moment_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择朋友圈图片", filter="Images (*.png *.jpg *.jpeg *.bmp)")
        if files:
            self.moment_images.setText(";".join(files))

    def _publish_moment(self) -> None:
        images = [x for x in self.moment_images.text().split(";") if x]
        try:
            uploads = {path: encode_upload(path) for path in images}
        except OSError as exc:
            return self._error(f"图片读取失败：{exc}")
        options = {"at_usrs": [], "labels": [], "is_close_moments": True}
        self._call("AddMoments", {"image_files": json.dumps(images, ensure_ascii=False), "content": self.moment_content.toPlainText(), "upload": json.dumps(uploads), "options": json.dumps(options)})

    def _remove_moment(self) -> None:
        if self.remove_moment_content.text().strip():
            self._call("RemoveMoments", self.remove_moment_content.text().strip())

    def _monitor_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(label("监听中心", "pageTitle"))
        row.addWidget(label("实时消息、群系统消息与好友申请", "muted"), 0, Qt.AlignBottom)
        row.addStretch()
        layout.addLayout(row)
        config, config_box = card("消息监听配置")
        form = QGridLayout()
        self.monitor_targets = QLineEdit()
        self.monitor_targets.setPlaceholderText("好友/群聊名称，多个用逗号分隔；留空表示开放式监听")
        self.monitor_interval = QSpinBox()
        self.monitor_interval.setRange(1, 3600)
        self.monitor_interval.setValue(5)
        self.monitor_open = QCheckBox("开放式监听")
        form.addWidget(label("监听对象", "muted"), 0, 0)
        form.addWidget(self.monitor_targets, 0, 1, 1, 3)
        form.addWidget(label("间隔（秒）", "muted"), 1, 0)
        form.addWidget(self.monitor_interval, 1, 1)
        form.addWidget(self.monitor_open, 1, 2)
        form.addWidget(button("启动消息监听", self._start_monitor, True), 1, 3)
        config_box.addLayout(form)
        layout.addWidget(config)
        system, system_box = card("好友申请与群系统")
        system_row = QHBoxLayout()
        system_row.addWidget(button("自动通过好友申请", self._start_friend_listener))
        system_row.addWidget(button("监听群系统消息", self._start_group_listener))
        system_row.addWidget(button("暂停监听", self._pause_monitor))
        system_row.addWidget(button("恢复监听", self._resume_monitor))
        system_box.addLayout(system_row)
        layout.addWidget(system)
        events, events_box = card("实时事件")
        self.monitor_events = QPlainTextEdit()
        self.monitor_events.setReadOnly(True)
        events_box.addWidget(self.monitor_events)
        layout.addWidget(events, 1)
        return page

    def _start_monitor(self) -> None:
        targets = [x.strip() for x in self.monitor_targets.text().split(",") if x.strip()]
        options = {"nick_names": json.dumps(targets, ensure_ascii=False), "is_open_monitor": self.monitor_open.isChecked(), "options": json.dumps({"fetch_friend_info": False, "fetch_image": False, "fetch_voice_chat": False, "click_red_envelope": False, "is_risk_prevention": True})}
        self._call("AddMessageListener", options, lambda _: self._append_event("消息监听已启动"))

    def _start_friend_listener(self) -> None:
        options = {"passed_delete": True, "keyword": [], "suffix": "", "label": ""}
        self._call("AddFriendRequestAutoAcceptListener", options, lambda _: self._append_event("好友申请监听已启动"))

    def _start_group_listener(self) -> None:
        targets = [x.strip() for x in self.monitor_targets.text().split(",") if x.strip()]
        self._call("AddGroupSystemMessageListener", json.dumps(targets, ensure_ascii=False), lambda _: self._append_event("群系统消息监听已启动"))

    def _pause_monitor(self) -> None:
        self._call("PauseMessageListener", "", lambda _: self._append_event("消息监听已暂停"))

    def _resume_monitor(self) -> None:
        self._call("ResumeMessageListener", "", lambda _: self._append_event("消息监听已恢复"))

    def _append_event(self, text: str) -> None:
        self.monitor_events.appendPlainText(text)
        self._log(text)

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)
        layout.addWidget(label("系统设置", "pageTitle"))
        connection, connection_box = card("WebSocket 连接")
        form = QGridLayout()
        settings_uri = QLineEdit(self.uri_input.text())
        settings_uri.textChanged.connect(self.uri_input.setText)
        self.uri_input.textChanged.connect(settings_uri.setText)
        form.addWidget(label("服务端地址", "muted"), 0, 0)
        form.addWidget(settings_uri, 0, 1)
        form.addWidget(label("状态", "muted"), 1, 0)
        form.addWidget(label("演示模式：无服务端也可预览全部界面", "muted"), 1, 1)
        connection_box.addLayout(form)
        layout.addWidget(connection)
        behavior, behavior_box = card("自动化参数")
        behavior_form = QGridLayout()
        self.setting_interval = QSpinBox()
        self.setting_interval.setRange(1, 120)
        self.setting_interval.setValue(5)
        self.setting_cache = QCheckBox("优先使用通讯录缓存")
        self.setting_cache.setChecked(True)
        self.setting_ocr = QCheckBox("启用 OCR 相关能力（由服务端提供）")
        self.setting_ocr.setChecked(True)
        behavior_form.addWidget(label("默认监听间隔", "muted"), 0, 0)
        behavior_form.addWidget(self.setting_interval, 0, 1)
        behavior_form.addWidget(self.setting_cache, 1, 0, 1, 2)
        behavior_form.addWidget(self.setting_ocr, 2, 0, 1, 2)
        behavior_box.addLayout(behavior_form)
        layout.addWidget(behavior)
        about, about_box = card("关于")
        about_box.addWidget(label("MyBot 2.0", "sectionTitle"))
        about_box.addWidget(label("PySide6 前端 · WeChatAuto4_X WebSocket 适配 · 演示模式可离线预览", "muted"))
        layout.addWidget(about)
        layout.addStretch()
        return page
