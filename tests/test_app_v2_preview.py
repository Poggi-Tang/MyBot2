import unittest
from collections import deque
from concurrent.futures import Future
from datetime import datetime
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mybot_ui.api import GatewayResult
from mybot_ui.app_v2 import MainWindow
from mybot_ui.attachments import ConversationAttachmentStore, IncomingAttachment
from mybot_ui.auto_chat import ListenerMessageCursor, ReplyAction, ReplyKind
from mybot_ui.chat_engine import IncomingMessage, ModelConfig
from mybot_ui.codex_runner import CodexResult


class AutoChatPreviewPollingTests(unittest.TestCase):
    def test_preview_polling_pauses_while_a_reply_is_active(self):
        calls = []
        window = SimpleNamespace(
            auto_chat_running=True,
            _preview_poll_pending=False,
            _auto_chat_pending={"contact": 1},
            gateway=SimpleNamespace(connected=True, call=lambda *args: calls.append(args)),
        )

        MainWindow._poll_auto_chat_previews(window)

        self.assertEqual([], calls)

    def test_failed_preview_poll_enters_backoff(self):
        window = SimpleNamespace(
            auto_chat_running=True,
            _preview_poll_pending=False,
            _preview_backoff_until=0.0,
            _preview_timeout_count=0,
            _auto_chat_pending={},
            gateway=SimpleNamespace(
                connected=True,
                call=lambda *_args: GatewayResult(False, error="TimeoutError"),
            ),
            account="account",
            _run_future=lambda value, callback: callback(value),
        )

        with patch("mybot_ui.app_v2.time.monotonic", side_effect=[100.0, 101.0]), patch(
            "mybot_ui.app_v2.operations.event"
        ) as event:
            MainWindow._poll_auto_chat_previews(window)

        self.assertEqual(111.0, window._preview_backoff_until)
        self.assertEqual(1, window._preview_timeout_count)
        event.assert_called_once_with(
            "workflow",
            "preview_poll_backoff",
            {"seconds": 10, "error": "TimeoutError"},
        )

    def test_second_preview_timeout_recovers_stalled_server(self):
        recovered = []
        window = SimpleNamespace(
            auto_chat_running=True,
            _preview_poll_pending=False,
            _preview_backoff_until=0.0,
            _preview_timeout_count=1,
            _auto_chat_pending={},
            gateway=SimpleNamespace(
                connected=True,
                call=lambda *_args: GatewayResult(False, error="TimeoutError"),
            ),
            account="account",
            _recover_stalled_server=recovered.append,
            _run_future=lambda value, callback: callback(value),
        )

        with patch("mybot_ui.app_v2.time.monotonic", side_effect=[100.0, 101.0]):
            MainWindow._poll_auto_chat_previews(window)

        self.assertEqual(2, window._preview_timeout_count)
        self.assertEqual(["TimeoutError"], recovered)

    def test_image_preview_fetches_original_instead_of_waiting_forever(self):
        fetched = []
        result = GatewayResult(True, [{
            "conversation_title": "测试联系人甲",
            "conversation_content": "[图片]",
            "time": "16:55",
        }])
        window = SimpleNamespace(
            auto_chat_running=True,
            _preview_poll_pending=False,
            gateway=SimpleNamespace(connected=True, call=lambda *_args: result),
            account="圆子",
            _preview_snapshots={"测试联系人甲": "旧消息|16:54"},
            _auto_chat_sent_contents={},
            _preview_suppressed_until={},
            _auto_chat_groups=set(),
            _selected_auto_chat_targets=lambda: {"测试联系人甲"},
            _message_cursor=ListenerMessageCursor(),
            _fetch_preview_image=lambda title, stamp, fingerprint="": fetched.append(
                (title, stamp, fingerprint)
            ),
            _accept_auto_message=lambda _incoming: None,
            _run_future=lambda value, callback: callback(value),
        )

        MainWindow._poll_auto_chat_previews(window)

        self.assertEqual([("测试联系人甲", "16:55", "[图片]|16:55")], fetched)

    def test_preview_original_is_converted_to_visual_incoming_message(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "original.png"
            image_path.write_bytes(b"test-image-bytes")
            accepted = []
            calls = []
            payload = {
                "who": "对方",
                "message": "[图片]",
                "send_date": datetime.now().isoformat(timespec="seconds"),
                "message_type": 1,
                "ImageFile": str(image_path),
            }
            window = SimpleNamespace(
                _preview_image_fetches=set(),
                _preview_image_retries={},
                _preview_image_completed={},
                auto_chat_running=True,
                gateway=SimpleNamespace(
                    connected=True,
                    call=lambda account, function, options: (
                        calls.append((account, function, options))
                        or GatewayResult(True, payload)
                    ),
                ),
                account="圆子",
                _append_chat=lambda *_args: None,
                _accept_auto_message=accepted.append,
                _run_future=lambda value, callback: callback(value),
            )

            with patch("mybot_ui.app_v2.operations.start", return_value="span"), patch(
                "mybot_ui.app_v2.operations.finish"
            ), patch("mybot_ui.app_v2.operations.event"):
                MainWindow._fetch_preview_image(window, "测试联系人甲", "16:55")

            self.assertEqual("GetLatestOriginalImage", calls[0][1])
            self.assertEqual({"who": "测试联系人甲"}, calls[0][2])
            self.assertEqual(1, len(accepted))
            self.assertTrue(accepted[0].image_base64)
            self.assertEqual("original.png", accepted[0].attachments[0].name)

    def test_failed_image_preview_is_retried_without_a_new_fingerprint(self):
        fetched = []
        result = GatewayResult(True, [{
            "conversation_title": "测试联系人甲",
            "conversation_content": "[图片]",
            "time": "18:27",
        }])
        window = SimpleNamespace(
            auto_chat_running=True,
            _preview_poll_pending=False,
            gateway=SimpleNamespace(connected=True, call=lambda *_args: result),
            account="圆子",
            _preview_snapshots={"测试联系人甲": "[图片]|18:27"},
            _preview_image_retries={"测试联系人甲": ("[图片]|18:27", 1, 99.0)},
            _preview_image_completed={},
            _latest_incoming_media={},
            _auto_chat_sent_contents={},
            _preview_suppressed_until={},
            _auto_chat_groups=set(),
            _selected_auto_chat_targets=lambda: {"测试联系人甲"},
            _message_cursor=ListenerMessageCursor(),
            _fetch_preview_image=lambda title, stamp, fingerprint="": fetched.append(
                (title, stamp, fingerprint)
            ),
            _accept_auto_message=lambda _incoming: None,
            _run_future=lambda value, callback: callback(value),
        )

        with patch("mybot_ui.app_v2.time.monotonic", return_value=100.0):
            MainWindow._poll_auto_chat_previews(window)

        self.assertEqual([("测试联系人甲", "18:27", "[图片]|18:27")], fetched)

    def test_real_image_is_not_dropped_by_an_older_outgoing_image_marker(self):
        accepted = []
        logs = []
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_media("测试联系人甲", "[图片]")
        incoming = IncomingMessage(
            chat_title="测试联系人甲",
            who="对方",
            content="[图片]",
            send_date="2026-08-09T16:36:04",
            message_type=1,
            image_base64="aW1hZ2U=",
        )
        window = SimpleNamespace(
            _selected_auto_chat_targets=lambda: {"测试联系人甲"},
            reply_keyword=SimpleNamespace(text=lambda: ""),
            _message_cursor=cursor,
            attachment_store=None,
            _append_chat=lambda *args: logs.append(args),
            _auto_chat_queues={"测试联系人甲": deque()},
            _process_next_auto_message=lambda title: accepted.append(title),
        )

        MainWindow._accept_auto_message(window, incoming)

        self.assertEqual(["测试联系人甲"], accepted)
        self.assertEqual(1, len(window._auto_chat_queues["测试联系人甲"]))
        self.assertTrue(any("含图片" in message for _kind, message in logs))

    def test_reconnect_resumes_without_invalidating_active_tasks(self):
        starts = []
        window = SimpleNamespace(
            _connect_in_progress=True,
            connect_button=SimpleNamespace(setEnabled=lambda _value: None),
            account_combo=SimpleNamespace(
                blockSignals=lambda _value: None,
                clear=lambda: None,
                addItems=lambda _items: None,
            ),
            gateway=SimpleNamespace(
                clients=["圆子"],
                uri="ws://127.0.0.1:5177/ws",
                call=lambda *_args: GatewayResult(True, True),
            ),
            account="",
            auto_chat_running=True,
            _listener_targets={"测试联系人甲"},
            _set_connection=lambda *_args: None,
            _append_chat=lambda *_args: None,
            _refresh_auto_chat_targets=lambda: None,
            _start_auto_chat=lambda **kwargs: starts.append(kwargs),
            _run_future=lambda value, callback: callback(value),
        )

        MainWindow._connection_result(window, GatewayResult(True, ["圆子"]))

        self.assertTrue(window.auto_chat_running)
        self.assertEqual([{"preserve_session": True}], starts)

    def test_listener_and_preview_surfaces_dedupe_same_bubble(self):
        window = SimpleNamespace(
            _selected_auto_chat_targets=lambda: {"人工智能自动化技术讨论群"},
            reply_keyword=SimpleNamespace(text=lambda: ""),
            _message_cursor=ListenerMessageCursor(),
            _append_chat=lambda *_args: None,
            _auto_chat_queues={"人工智能自动化技术讨论群": deque()},
            _process_next_auto_message=lambda _title: None,
        )
        first = SimpleNamespace(
            chat_title="人工智能自动化技术讨论群",
            who="测试联系人甲",
            content="发个可爱联盟的",
            feature="listener-timestamp",
            send_date="2026-08-10T09:21:23",
            image_base64="",
        )
        second = SimpleNamespace(
            chat_title=first.chat_title,
            who=first.who,
            content=first.content,
            feature="preview-now|15:37",
            send_date="2026-08-10T09:21:51|09:21",
            image_base64="",
        )
        with patch("mybot_ui.auto_chat.time.monotonic", side_effect=[10.0, 40.0]):
            MainWindow._accept_auto_message(window, first)
            MainWindow._accept_auto_message(window, second)

        self.assertEqual(1, len(window._auto_chat_queues[first.chat_title]))

    def test_pascal_case_unread_preview_is_accepted(self):
        accepted = []
        result = GatewayResult(
            True,
            [
                {
                    "ConversationTitle": "测试群聊",
                    "ConversationContent": "测试联系人甲: 新消息",
                    "NotReadNumbr": 1,
                    "Time": "18:20",
                }
            ],
        )
        gateway = SimpleNamespace(connected=True, call=lambda *_args: result)
        window = SimpleNamespace(
            auto_chat_running=True,
            _preview_poll_pending=False,
            gateway=gateway,
            account="圆子",
            _preview_snapshots={"测试群聊": "旧消息|18:19"},
            _auto_chat_sent_contents={},
            _auto_chat_groups={"测试群聊"},
            _selected_auto_chat_targets=lambda: {"测试群聊"},
            _accept_auto_message=accepted.append,
            _run_future=lambda value, callback: callback(value),
        )

        MainWindow._poll_auto_chat_previews(window)

        self.assertFalse(window._preview_poll_pending)
        self.assertEqual(1, len(accepted))
        self.assertEqual("测试联系人甲", accepted[0].who)
        self.assertEqual("新消息", accepted[0].content)

    def test_outgoing_media_preview_is_not_treated_as_incoming(self):
        accepted = []
        result = GatewayResult(True, [{
            "conversation_title": "测试联系人甲",
            "conversation_content": "[文件] result.txt",
            "time": "18:20",
        }])
        window = SimpleNamespace(
            auto_chat_running=True,
            _preview_poll_pending=False,
            gateway=SimpleNamespace(connected=True, call=lambda *_args: result),
            account="圆子",
            _preview_snapshots={"测试联系人甲": "旧消息|18:19"},
            _auto_chat_sent_contents={},
            _preview_suppressed_until={"测试联系人甲": 110.0},
            _auto_chat_groups=set(),
            _selected_auto_chat_targets=lambda: {"测试联系人甲"},
            _accept_auto_message=accepted.append,
            _run_future=lambda value, callback: callback(value),
        )

        with patch("mybot_ui.app_v2.time.monotonic", return_value=100.0):
            MainWindow._poll_auto_chat_previews(window)

        self.assertEqual([], accepted)
        self.assertEqual("[文件] result.txt|18:20", window._preview_snapshots["测试联系人甲"])

    def test_codex_output_file_is_sent_to_originating_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.txt"
            output.write_text("done", encoding="utf-8")
            calls = []
            completed = []
            suppressed = []
            gateway = SimpleNamespace(call=lambda account, function, options: (
                calls.append((account, function, options)) or GatewayResult(True, True)
            ))
            window = SimpleNamespace(
                _auto_chat_session=3,
                auto_chat_running=True,
                gateway=gateway,
                account="圆子",
                _append_chat=lambda *_args: None,
                _run_future=lambda value, callback: callback(value),
                _suppress_outgoing_media_preview=suppressed.append,
                _message_cursor=ListenerMessageCursor(),
                _finish_auto_message=lambda *_args, **_kwargs: None,
            )
            result = CodexResult("完成", "thread", "task", output_files=(str(output),))

            with patch("mybot_ui.app_v2.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
                MainWindow._send_codex_output_files(
                    window,
                    SimpleNamespace(chat_title="测试联系人甲"),
                    3,
                    result,
                    after_sent=lambda sent, failed: completed.append((sent, failed)),
                )

            self.assertEqual("SendFile", calls[0][1])
            self.assertEqual("测试联系人甲", calls[0][2]["who"])
            self.assertEqual(["测试联系人甲"], suppressed)
            self.assertEqual([(("result.txt",), ())], completed)

    def test_codex_file_completion_is_one_safe_message(self):
        replies = []
        window = SimpleNamespace(
            _send_auto_text_segments=lambda incoming, session, segments, full_reply, after_sent=None: (
                replies.append((segments, full_reply)),
                after_sent() if after_sent else None,
            ),
        )
        finished = []

        MainWindow._send_codex_delivery_completion(
            window,
            SimpleNamespace(chat_title="测试联系人甲"),
            3,
            ("MyBot功能列表.md",),
            (),
            after_sent=lambda: finished.append(True),
        )

        self.assertEqual(1, len(replies))
        self.assertEqual(("MyBot功能列表.md 做好了，已经发给你了",), replies[0][0])
        self.assertNotIn(":\\", replies[0][1])
        self.assertNotIn("登记", replies[0][1])
        self.assertEqual([True], finished)


class AutoChatStartupTests(unittest.TestCase):
    def test_configured_contact_is_consumed_once_when_available(self):
        window = SimpleNamespace(
            settings={"chat": {
                "auto_start_enabled": True,
                "auto_start_targets": ["测试联系人甲"],
            }},
            _auto_start_attempted=False,
        )

        selected = MainWindow._consume_auto_start_targets(window, {"测试联系人甲", "其他会话"})
        repeated = MainWindow._consume_auto_start_targets(window, {"测试联系人甲"})

        self.assertEqual({"测试联系人甲"}, selected)
        self.assertEqual(set(), repeated)

    def test_missing_or_disabled_contact_does_not_start(self):
        missing = SimpleNamespace(
            settings={"chat": {"auto_start_enabled": True, "auto_start_targets": ["测试联系人甲"]}},
            _auto_start_attempted=False,
        )
        disabled = SimpleNamespace(
            settings={"chat": {"auto_start_enabled": False, "auto_start_targets": ["测试联系人甲"]}},
            _auto_start_attempted=False,
        )

        self.assertEqual(set(), MainWindow._consume_auto_start_targets(missing, {"其他会话"}))
        self.assertEqual(set(), MainWindow._consume_auto_start_targets(disabled, {"测试联系人甲"}))

    def test_disabled_auto_start_still_restores_last_selection(self):
        window = SimpleNamespace(
            settings={"chat": {"auto_start_enabled": False, "auto_start_targets": ["测试联系人甲"]}},
        )

        self.assertEqual(
            {"测试联系人甲"},
            MainWindow._configured_auto_chat_targets(window, {"测试联系人甲", "其他会话"}),
        )

    def test_last_selection_is_written_without_losing_other_chat_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps({"chat": {"auto_start_enabled": True, "cooldown_seconds": 2}}),
                encoding="utf-8",
            )
            window = SimpleNamespace(
                config_path=config_path,
                settings={"chat": {"auto_start_enabled": True, "cooldown_seconds": 2}},
                _selected_auto_chat_targets=lambda: {"测试联系人甲", "测试群"},
            )

            MainWindow._persist_auto_chat_selection(window)

            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(["测试群", "测试联系人甲"], saved["chat"]["auto_start_targets"])
            self.assertEqual(2, saved["chat"]["cooldown_seconds"])


class AutoChatModelRoutingTests(unittest.TestCase):
    @staticmethod
    def _image_edit_window(incoming, *, pending=None):
        submitted = []
        finished = []
        remembered = []
        window = SimpleNamespace(
            _auto_chat_queues={incoming.chat_title: deque([incoming])},
            auto_chat_running=True,
            _auto_chat_pending={},
            reply_cooldown=SimpleNamespace(value=lambda: 0),
            _auto_chat_last_reply={},
            _selected_auto_chat_targets=lambda: {incoming.chat_title},
            _auto_chat_session=7,
            _auto_reply_spans={},
            _pending_image_edits=pending or {},
            account="圆子",
            memory=SimpleNamespace(add_user=lambda *args: remembered.append(args)),
            model_executor=SimpleNamespace(
                submit=lambda function, *args: submitted.append((function, args)) or "future"
            ),
            _fetch_latest_original_and_edit=lambda *_args: "edited.png",
            _finish_auto_image=lambda future, message, session, mode: finished.append(
                (future, message, session, mode)
            ),
        )
        return window, submitted, finished, remembered

    def test_typo_image_edit_request_routes_directly_to_image_editor(self):
        incoming = IncomingMessage(
            "测试联系人甲",
            "对方",
            "我在等你吧必胜客改成肯德基",
        )
        window, submitted, finished, remembered = self._image_edit_window(incoming)

        with patch("mybot_ui.app_v2.operations.start", return_value="span"), patch(
            "mybot_ui.app_v2.operations.event"
        ) as event:
            MainWindow._process_next_auto_message(window, "测试联系人甲")

        self.assertEqual((incoming, incoming.content), submitted[0][1])
        self.assertEqual("edited", finished[0][3])
        self.assertEqual(incoming.content, window._pending_image_edits["测试联系人甲"][0])
        self.assertEqual(1, len(remembered))
        event.assert_called_once_with(
            "workflow",
            "image_edit_route",
            {"chat_title": "测试联系人甲", "source": "explicit"},
        )

    def test_followup_resumes_pending_image_edit_request(self):
        request = "把必胜客改成肯德基"
        incoming = IncomingMessage("测试联系人甲", "对方", "我上面不是发了吗")
        window, submitted, finished, _remembered = self._image_edit_window(
            incoming,
            pending={"测试联系人甲": (request, 100.0)},
        )

        with patch("mybot_ui.app_v2.time.monotonic", return_value=120.0), patch(
            "mybot_ui.app_v2.operations.start", return_value="span"
        ), patch("mybot_ui.app_v2.operations.event") as event:
            MainWindow._process_next_auto_message(window, "测试联系人甲")

        self.assertEqual((incoming, request), submitted[0][1])
        self.assertEqual("edited", finished[0][3])
        event.assert_called_once_with(
            "workflow",
            "image_edit_route",
            {"chat_title": "测试联系人甲", "source": "pending_followup"},
        )

    def test_image_edit_uses_private_saved_image_when_sdk_fetch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "wechat" / "9a05bda4f7a445cd96706382531e2201.png"
            source_path.parent.mkdir()
            source_path.write_bytes(b"\x89PNG\r\n\x1a\nrestaurant")
            store = ConversationAttachmentStore(root / "attachments")
            remembered = store.remember(
                "测试联系人甲",
                (IncomingAttachment(source_path.name, str(source_path), "image"),),
            )
            edit_calls = []
            gateway = SimpleNamespace(call=lambda *_args: SimpleNamespace(
                result=lambda timeout: GatewayResult(False, error="SDK original unavailable")
            ))
            window = SimpleNamespace(
                gateway=gateway,
                account="圆子",
                attachment_store=store,
                model_client=SimpleNamespace(
                    edit_image=lambda config, prompt, image_path: edit_calls.append(
                        (config, prompt, image_path)
                    ) or "edited.png"
                ),
                _image_config=lambda: "image-config",
            )
            incoming = IncomingMessage(
                "测试联系人甲",
                "对方",
                "我上面不是发了吗",
                send_date="2026-08-09T15:31:34+08:00",
            )

            with patch("mybot_ui.app_v2.operations.event") as event:
                result = MainWindow._fetch_latest_original_and_edit(
                    window,
                    incoming,
                    "把必胜客改成肯德基",
                )

            self.assertEqual("edited.png", result)
            self.assertEqual(remembered[0].path, edit_calls[0][2])
            self.assertIn("把必胜客改成肯德基", edit_calls[0][1])
            self.assertEqual("private_attachment_store", event.call_args.args[2]["source"])

    def test_codex_transition_prompt_uses_persona_examples_and_ranked_memory(self):
        incoming = SimpleNamespace(
            chat_title="人工智能自动化技术讨论群",
            who="测试联系人甲",
            content="帮我把这个功能实现了",
        )
        window = SimpleNamespace(
            _auto_chat_groups={"人工智能自动化技术讨论群"},
            _resolved_persona_messages=lambda _incoming: (
                [
                    "你的名字是圆子\n示例对话：对方：帮我查一下\n圆子：行，我去看看",
                    "与当前话题相关的个人偏好",
                    "与当前话题最相关的过往互动",
                ],
                ["identity:圆子", "learned:测试联系人甲", "episodes:测试联系人甲"],
                "测试联系人甲",
            ),
            _model_config=lambda: ModelConfig(system_prompt="基础提示"),
            memory=SimpleNamespace(transcript=lambda *_args, **_kwargs: "测试联系人甲: 上次也做过类似功能"),
        )

        with patch("mybot_ui.app_v2.operations.event") as event:
            messages = MainWindow._persona_task_messages(window, incoming, purpose="ack")

        joined = "\n".join(item["content"] for item in messages)
        self.assertIn("示例对话", joined)
        self.assertIn("个人偏好", joined)
        self.assertIn("过往互动", joined)
        self.assertIn("像熟人聊天", joined)
        event.assert_called_once()

    def test_codex_result_prompt_preserves_facts_while_humanizing(self):
        incoming = SimpleNamespace(chat_title="测试联系人甲", who="对方", content="修一下")
        window = SimpleNamespace(
            _auto_chat_groups=set(),
            _resolved_persona_messages=lambda _incoming: (["圆子人格"], ["identity:圆子"], "测试联系人甲"),
            _model_config=lambda: ModelConfig(system_prompt="基础提示"),
            memory=SimpleNamespace(transcript=lambda *_args, **_kwargs: ""),
        )

        with patch("mybot_ui.app_v2.operations.event"):
            messages = MainWindow._persona_task_messages(
                window,
                incoming,
                purpose="result",
                task_result="已修改 app.py，87 项测试通过",
            )

        joined = "\n".join(item["content"] for item in messages)
        self.assertIn("不得遗漏关键数字、路径", joined)
        self.assertIn("必须逐字保留的事实锁", joined)
        self.assertIn("87 项", joined)
        self.assertIn("测试通过", joined)
        self.assertIn("87 项测试通过", joined)

    def test_codex_persona_ack_validation_rejects_robotic_or_false_status(self):
        self.assertTrue(MainWindow._valid_codex_acknowledgement("行，我去看看，等我一下"))
        self.assertFalse(MainWindow._valid_codex_acknowledgement(
            "这个任务需要一些时间，我处理完成后把结果发给你"
        ))
        self.assertFalse(MainWindow._valid_codex_acknowledgement("后台已经处理好了"))

    def test_codex_start_sends_router_ack_without_calling_ack_model(self):
        codex_future = Future()
        runner = object()
        started = []
        incoming = SimpleNamespace(
            chat_title="测试联系人甲",
            who="测试联系人甲",
            content="写个功能列表到md文件发给我",
            send_date="2026-08-09T20:53:59",
        )
        window = SimpleNamespace(
            _auto_chat_groups=set(),
            _codex_runner=lambda: runner,
            memory=SimpleNamespace(transcript=lambda *_args, **_kwargs: ""),
            codex_executor=SimpleNamespace(submit=lambda _callable: codex_future),
            _finish_auto_codex_ack=lambda *args: started.append(args),
        )

        with patch("mybot_ui.app_v2.operations.event"):
            MainWindow._start_auto_codex(window, incoming, 7, route_source="router")

        self.assertEqual(1, len(started))
        self.assertIs(codex_future, started[0][0])
        self.assertIs(runner, started[0][1])
        self.assertTrue(started[0][-1])
        self.assertNotEqual(
            "这个任务需要一些时间，我处理完成后把结果发给你",
            started[0][-1],
        )

    def test_codex_result_fact_lock_rejects_changed_test_count_meaning(self):
        raw = "已修改 mybot_ui/app_v2.py，完整测试 90 项全部通过，需要重启后生效"
        self.assertTrue(MainWindow._codex_result_preserves_facts(
            raw,
            "弄好了，mybot_ui/app_v2.py 已修改，90 项全部通过，需要重启后生效",
        ))
        self.assertFalse(MainWindow._codex_result_preserves_facts(
            raw,
            "mybot_ui/app_v2.py 第 90 行附近处理了，还得再确认",
        ))

    def test_named_sticker_collection_resolves_catalog_category(self):
        incoming = SimpleNamespace(chat_title="人工智能自动化技术讨论群")
        window = SimpleNamespace(
            gateway=SimpleNamespace(call=lambda *_args: "scan-future"),
            account="圆子",
            _run_future=lambda future, callback: callback(
                SimpleNamespace(
                    ok=True,
                    value={"Items": [{"Category": "可爱联盟14", "Name": "融化"}],
                },
            ),
            ),
            _send_auto_sticker_request=lambda *args: setattr(window, "resolved", args),
        )

        MainWindow._send_auto_sticker(window, incoming, 3, "可爱联盟")

        self.assertEqual("可爱联盟14", window.resolved[2])
        self.assertEqual("融化", window.resolved[3])

    def test_auto_emoji_path_never_calls_send_emoji(self):
        incoming = SimpleNamespace(chat_title="人工智能自动化技术讨论群")
        routed = []
        window = SimpleNamespace(
            _send_auto_sticker=lambda message, session, query: routed.append(
                (message, session, query)
            )
        )

        MainWindow._send_auto_emoji(window, incoming, 4, "捂脸")

        self.assertEqual([(incoming, 4, "捂脸")], routed)

    def test_model_sticker_choice_maps_index_to_exact_catalog_item(self):
        future = Future()
        future.set_result("1")
        incoming = SimpleNamespace(chat_title="人工智能自动化技术讨论群")
        candidates = [
            {"Category": "这狗13", "Name": "开心", "Mode": "semantic"},
            {"Category": "这狗13", "Name": "吃瓜", "Mode": "semantic"},
        ]
        sent = []
        window = SimpleNamespace(
            _auto_chat_session=5,
            auto_chat_running=True,
            _sticker_selection_offsets={},
            _send_auto_sticker_request=lambda *args: sent.append(args),
            _finish_auto_message=lambda *_args, **_kwargs: None,
        )

        with patch("mybot_ui.app_v2.operations.event"):
            MainWindow._finish_auto_sticker_choice(
                window, future, incoming, 5, "这狗", candidates
            )

        self.assertEqual("这狗13", sent[0][2])
        self.assertEqual("吃瓜", sent[0][3])
        self.assertIn("AI 根据对话", sent[0][5])

    def test_sticker_inflight_and_cooldown_suppress_concurrent_duplicates(self):
        finished = []
        incoming = SimpleNamespace(chat_title="测试联系人甲", who="测试联系人甲")
        window = SimpleNamespace(
            _sticker_in_flight={},
            _sticker_last_sent={},
            _finish_auto_message=lambda *args, **kwargs: finished.append((args, kwargs)),
        )

        with patch("mybot_ui.app_v2.time.monotonic", side_effect=[100.0, 101.0, 102.0, 120.0]), patch(
            "mybot_ui.app_v2.operations.event"
        ) as event:
            self.assertTrue(MainWindow._reserve_auto_sticker(window, incoming))
            self.assertFalse(MainWindow._reserve_auto_sticker(window, incoming))
            MainWindow._release_auto_sticker(window, "测试联系人甲", sent=True)
            self.assertFalse(MainWindow._reserve_auto_sticker(window, incoming))

        self.assertEqual(2, len(finished))
        self.assertEqual("in_flight", finished[0][1]["result"]["reason"])
        self.assertEqual("cooldown", finished[1][1]["result"]["reason"])
        self.assertEqual(2, event.call_count)

    def test_realtime_weather_bypasses_model_and_codex(self):
        incoming = SimpleNamespace(
            chat_title="测试联系人甲",
            who="对方",
            content="上海徐汇今天天气怎么样",
            image_base64="",
        )
        submitted = []
        finished = []
        remembered = []
        window = SimpleNamespace(
            _auto_chat_queues={"测试联系人甲": deque([incoming])},
            auto_chat_running=True,
            _auto_chat_pending=set(),
            reply_cooldown=SimpleNamespace(value=lambda: 0),
            _auto_chat_last_reply={},
            _selected_auto_chat_targets=lambda: {"测试联系人甲"},
            _auto_chat_session=7,
            _auto_reply_spans={},
            account="圆子",
            memory=SimpleNamespace(
                transcript=lambda _title: "",
                add_user=lambda *args: remembered.append(args),
            ),
            codex_enabled=SimpleNamespace(isChecked=lambda: True),
            realtime_tool_executor=SimpleNamespace(execute=lambda request: request),
            model_executor=SimpleNamespace(
                submit=lambda function, request: submitted.append((function, request)) or "future"
            ),
            _start_auto_realtime_tool=lambda future, message, session: finished.append(
                (future, message, session)
            ),
            _start_auto_codex=lambda *_args, **_kwargs: self.fail("weather should not use Codex"),
        )

        with patch("mybot_ui.app_v2.operations.start", return_value="span"), patch(
            "mybot_ui.app_v2.operations.event"
        ) as event:
            MainWindow._process_next_auto_message(window, "测试联系人甲")

        self.assertEqual("weather", submitted[0][1].kind)
        self.assertEqual("上海徐汇今天天气怎么样", submitted[0][1].query)
        self.assertEqual([("future", incoming, 7)], finished)
        self.assertEqual(1, len(remembered))
        event.assert_called_once_with(
            "tool",
            "realtime_tool_route",
            {"chat_title": "测试联系人甲", "kind": "weather"},
        )

    def test_realtime_tool_ack_is_immediate_and_natural(self):
        calls = []
        continued = []
        remembered = []
        incoming = SimpleNamespace(chat_title="测试群聊", who="测试联系人甲")
        window = SimpleNamespace(
            account="圆子",
            gateway=SimpleNamespace(call=lambda account, function, options: (
                calls.append((account, function, options)) or GatewayResult(True, True)
            )),
            _message_cursor=ListenerMessageCursor(),
            _auto_reply_reference=lambda _incoming: (None, "direct_reply"),
            _run_future=lambda value, callback: callback(value),
            memory=SimpleNamespace(add_assistant=lambda *args: remembered.append(args)),
            _auto_chat_sent_contents={},
            _append_chat=lambda *_args: None,
            _finish_auto_realtime_tool=lambda *args: continued.append(args),
        )

        with patch("mybot_ui.app_v2.operations.event"):
            MainWindow._start_auto_realtime_tool(window, "future", incoming, 7)

        self.assertEqual("SendMessage", calls[0][1])
        self.assertEqual("稍等，我去看一下", calls[0][2]["message"])
        self.assertEqual([("future", incoming, 7)], continued)
        self.assertEqual([("测试群聊", "稍等，我去看一下")], remembered)

    def test_model_delegate_marker_hands_original_message_to_codex(self):
        delegated = []
        future = Future()
        future.set_result("<MYBOT_DELEGATE_CODEX>")
        incoming = SimpleNamespace(chat_title="测试联系人甲", content="帮我核实这个最新消息")
        window = SimpleNamespace(
            _auto_chat_session=3,
            auto_chat_running=True,
            codex_enabled=SimpleNamespace(isChecked=lambda: True),
            _start_auto_codex=lambda message, session, route_source: delegated.append(
                (message, session, route_source)
            ),
        )

        MainWindow._finish_auto_reply(
            window,
            future,
            incoming,
            3,
            ReplyAction(ReplyKind.TEXT),
        )

        self.assertEqual([(incoming, 3, "model")], delegated)


if __name__ == "__main__":
    unittest.main()
