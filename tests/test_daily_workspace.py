import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mybot_ui.api import GatewayResult
from mybot_ui.app_v2 import MainWindow
from mybot_ui.auto_chat import ListenerMessageCursor
from mybot_ui.chat_engine import IncomingMessage
from mybot_ui.daily_workspace import DailyWorkspaceStore


class DailyWorkspaceTests(unittest.TestCase):
    def test_records_people_and_days_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DailyWorkspaceStore(Path(directory) / "people")
            store.record(
                "芝士圆子",
                direction="incoming",
                conversation="私聊",
                sender="芝士圆子",
                content="第一天",
                timestamp="2026-08-10T09:30:00+08:00",
            )
            store.record(
                "芝士圆子",
                direction="outgoing",
                conversation="私聊",
                sender="圆子",
                content="第二天回复",
                timestamp="2026-08-11T10:00:00+08:00",
            )
            store.record(
                "群友甲",
                direction="incoming",
                conversation="测试群",
                sender="群友甲",
                content="群消息",
                timestamp="2026-08-11T10:01:00+08:00",
            )

            self.assertEqual(["群友甲", "芝士圆子"], store.names())
            self.assertEqual(["2026-08-11", "2026-08-10"], store.dates("芝士圆子"))
            self.assertEqual("第一天", store.entries("芝士圆子", "2026-08-10")[0].content)
            self.assertEqual("群消息", store.entries("群友甲", "2026-08-11")[0].content)

    def test_copies_files_and_deduplicates_repeated_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "来源" / "报告.md"
            source.parent.mkdir()
            source.write_text("report", encoding="utf-8")
            attachment = SimpleNamespace(
                name="报告.md",
                path=str(source),
                kind="file",
                sha256="",
            )
            store = DailyWorkspaceStore(root / "people")
            kwargs = {
                "direction": "outgoing",
                "conversation": "测试群",
                "sender": "圆子",
                "content": "报告做好了",
                "timestamp": "2026-08-11T12:00:00+08:00",
                "files": (attachment,),
            }

            store.record("群友甲", **kwargs)
            store.record("群友甲", **kwargs)

            entries = store.entries("群友甲", "2026-08-11")
            self.assertEqual(1, len(entries))
            self.assertEqual(1, len(entries[0].files))
            archived = Path(entries[0].files[0].path)
            self.assertTrue(archived.is_file())
            self.assertEqual("report", archived.read_text(encoding="utf-8"))
            self.assertIn("群友甲", archived.parts)
            self.assertIn("2026-08-11", archived.parts)

    def test_aliases_share_one_person_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DailyWorkspaceStore(
                Path(directory) / "people",
                aliases={"小张": "张晓源"},
            )
            store.record(
                "小张",
                direction="incoming",
                conversation="群聊",
                sender="小张",
                content="你好",
                timestamp="2026-08-11T12:00:00+08:00",
            )

            self.assertEqual(["张晓源"], store.names())
            self.assertEqual(1, len(store.entries("张晓源", "2026-08-11")))


class DailyWorkspaceAppIntegrationTests(unittest.TestCase):
    @staticmethod
    def _window(store: DailyWorkspaceStore, *, groups=()):
        return SimpleNamespace(
            daily_workspace_store=store,
            personal_memory_aliases={},
            personal_memory_ignored_names=set(),
            _auto_chat_groups=set(groups),
            _reply_policy=SimpleNamespace(ai_name="圆子"),
            account="圆子",
        )

    def test_group_messages_are_archived_under_the_actual_sender(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DailyWorkspaceStore(Path(directory) / "people")
            window = self._window(store, groups={"项目群"})
            incoming = IncomingMessage(
                "项目群",
                "小张",
                "今天把方案定下来",
                "2026-08-11T09:30:00+08:00",
            )

            MainWindow._record_daily_workspace(
                window,
                incoming,
                direction="incoming",
                content=incoming.content,
            )

            self.assertEqual(["小张"], store.names())
            entry = store.entries("小张", "2026-08-11")[0]
            self.assertEqual("项目群", entry.conversation)
            self.assertEqual("小张", entry.sender)

    def test_generated_image_is_archived_when_wechat_send_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "generated.png"
            image.write_bytes(b"generated image")
            store = DailyWorkspaceStore(root / "people")
            window = self._window(store)
            window._auto_chat_session = 3
            window.auto_chat_running = True
            window.gateway = SimpleNamespace(
                call=lambda *_args, **_kwargs: GatewayResult(False, error="send failed")
            )
            window._run_future = lambda value, callback: callback(value)
            window._append_chat = lambda *_args: None
            window._finish_auto_message = lambda *_args, **_kwargs: None
            window._suppress_outgoing_media_preview = lambda *_args: None
            window._message_cursor = ListenerMessageCursor()
            incoming = IncomingMessage(
                "小张",
                "小张",
                "画一张图",
                "2026-08-11T09:30:00+08:00",
            )
            future = Future()
            future.set_result(str(image))

            with patch("mybot_ui.app_v2.datetime") as clock:
                clock.now.return_value.astimezone.return_value.isoformat.return_value = (
                    "2026-08-11T09:31:00+08:00"
                )
                MainWindow._finish_auto_image(window, future, incoming, 3)

            entries = store.entries("小张", "2026-08-11")
            self.assertEqual(1, len(entries))
            self.assertEqual("work", entries[0].direction)
            self.assertEqual("[已生成图片]", entries[0].content)
            self.assertEqual(1, len(entries[0].files))
            archived = Path(entries[0].files[0].path)
            self.assertTrue(archived.is_file())
            self.assertEqual(b"generated image", archived.read_bytes())


if __name__ == "__main__":
    unittest.main()
