import json
import unittest
from collections import deque
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from mybot_ui.app_v2 import MainWindow
from mybot_ui.catalog import build_message_reference, build_options
from mybot_ui.chat_engine import IncomingMessage


class MessageReferenceTests(unittest.TestCase):
    def test_send_message_serializes_sdk_chat_reference(self):
        reference = build_message_reference(
            "测试联系人甲",
            "你看这个问题",
            "2026-08-09T14:05:00",
        )

        options = build_options(
            "SendMessage",
            {"who": "测试联系人甲", "message": "我看到了", "refer": reference},
        )

        payload = json.loads(options["refer"])
        self.assertEqual("2026-08-09", payload["date"])
        self.assertEqual("测试联系人甲", payload["message"]["who"])
        self.assertEqual("你看这个问题", payload["message"]["message"])
        self.assertEqual("2026年8月9日 14:05", payload["message"]["send_date_time"])

    def test_smart_reference_quotes_groups_and_parallel_private_messages(self):
        incoming = IncomingMessage(
            "人工智能自动化技术讨论群",
            "测试联系人甲",
            "这个怎么处理",
            datetime.now().isoformat(timespec="seconds"),
        )
        group_window = SimpleNamespace(
            _auto_chat_groups={incoming.chat_title},
            _auto_chat_pending={incoming.chat_title: 1},
        )

        reference, reason = MainWindow._auto_reply_reference(group_window, incoming)

        self.assertIsNotNone(reference)
        self.assertEqual("group_context", reason)

        private = IncomingMessage(
            "测试联系人甲",
            "测试联系人甲",
            "第二个问题",
            datetime.now().isoformat(timespec="seconds"),
        )
        private_window = SimpleNamespace(
            _auto_chat_groups=set(),
            _auto_chat_pending={private.chat_title: 2},
        )

        reference, reason = MainWindow._auto_reply_reference(private_window, private)

        self.assertIsNotNone(reference)
        self.assertEqual("parallel_messages", reason)

    def test_smart_reference_skips_immediate_private_reply_but_quotes_delayed_reply(self):
        current = IncomingMessage(
            "测试联系人甲",
            "测试联系人甲",
            "在吗",
            datetime.now().isoformat(timespec="seconds"),
        )
        window = SimpleNamespace(_auto_chat_groups=set(), _auto_chat_pending={current.chat_title: 1})

        reference, reason = MainWindow._auto_reply_reference(window, current)

        self.assertIsNone(reference)
        self.assertEqual("direct_reply", reason)

        delayed = IncomingMessage(
            current.chat_title,
            current.who,
            current.content,
            (datetime.now() - timedelta(seconds=90)).isoformat(timespec="seconds"),
        )
        reference, reason = MainWindow._auto_reply_reference(window, delayed)
        self.assertIsNotNone(reference)
        self.assertEqual("delayed_reply", reason)

    def test_smart_reference_quotes_immediate_private_media(self):
        incoming = IncomingMessage(
            "media-chat",
            "media-sender",
            "[image]",
            datetime.now().isoformat(timespec="seconds"),
            image_base64="aW1hZ2U=",
        )
        window = SimpleNamespace(
            _auto_chat_groups=set(),
            _auto_chat_pending={incoming.chat_title: 1},
        )

        reference, reason = MainWindow._auto_reply_reference(window, incoming)

        self.assertIsNotNone(reference)
        self.assertEqual("media_reply", reason)

    def test_explicit_image_quote_targets_latest_incoming_image(self):
        image = IncomingMessage(
            "测试联系人甲",
            "对方",
            "[图片]",
            "2026-08-09T18:27:24",
            image_base64="aW1hZ2U=",
        )
        request = IncomingMessage(
            "测试联系人甲",
            "对方",
            "引用我发的图片回复",
            "2026-08-09T18:28:00",
        )
        window = SimpleNamespace(
            _auto_chat_groups=set(),
            _auto_chat_pending={request.chat_title: 1},
            _latest_incoming_media={request.chat_title: image},
        )

        reference, reason = MainWindow._auto_reply_reference(window, request)

        self.assertEqual("explicit_incoming_image", reason)
        self.assertEqual("对方", reference["message"]["who"])
        self.assertEqual("[图片]", reference["message"]["message"])
        self.assertEqual("2026-08-09T18:27:24", reference["message"]["date_time"])


class SameConversationConcurrencyTests(unittest.TestCase):
    def test_two_messages_from_same_conversation_start_without_waiting(self):
        title = "测试联系人甲"
        messages = deque([
            IncomingMessage(title, "测试联系人甲", "上海今天天气怎么样", "2026-08-09T12:00:00"),
            IncomingMessage(title, "测试联系人甲", "北京今天天气怎么样", "2026-08-09T12:00:01"),
        ])
        submitted = []
        finished = []
        window = SimpleNamespace(
            _auto_chat_queues={title: messages},
            auto_chat_running=True,
            _auto_chat_pending={},
            _auto_chat_active_tasks=set(),
            chat_concurrency=SimpleNamespace(value=lambda: 2),
            reply_cooldown=SimpleNamespace(value=lambda: 0),
            _auto_chat_last_reply={},
            _selected_auto_chat_targets=lambda: {title},
            _auto_chat_session=7,
            _auto_reply_spans={},
            account="圆子",
            memory=SimpleNamespace(
                transcript=lambda _title: "",
                add_user=lambda *_args: None,
            ),
            codex_enabled=SimpleNamespace(isChecked=lambda: True),
            realtime_tool_executor=SimpleNamespace(execute=lambda request: request),
            model_executor=SimpleNamespace(
                submit=lambda function, request: submitted.append((function, request)) or object()
            ),
            _start_auto_realtime_tool=lambda future, incoming, session: finished.append(
                (future, incoming, session)
            ),
        )

        with patch("mybot_ui.app_v2.QTimer.singleShot"), patch(
            "mybot_ui.app_v2.operations.start", side_effect=["span-1", "span-2"]
        ), patch("mybot_ui.app_v2.operations.event"):
            MainWindow._process_next_auto_message(window, title)
            MainWindow._process_next_auto_message(window, title)

        self.assertEqual(2, len(submitted))
        self.assertEqual(2, len(finished))
        self.assertEqual(2, window._auto_chat_pending[title])
        self.assertEqual(2, len(window._auto_chat_active_tasks))
        self.assertEqual(0, len(messages))


if __name__ == "__main__":
    unittest.main()
