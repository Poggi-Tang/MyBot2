import base64
import json
import tempfile
import unittest
from io import BytesIO
from datetime import datetime
from pathlib import Path

from PIL import Image

from mybot_ui.chat_engine import (
    ChatModelClient,
    ConversationMemory,
    ImageConfig,
    ModelConfig,
    parse_conversation_preview,
    parse_listener_event,
)


class StubClient(ChatModelClient):
    def __init__(self, responses):
        self.responses = iter(responses)

    def generate(self, config, messages, *, timeout=120):
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class ChatEngineTests(unittest.TestCase):
    def test_resolved_visual_replaces_base64_with_semantics_in_history(self):
        memory = ConversationMemory()
        memory.add_user("测试会话", "测试联系人", "[图片]", "aW1hZ2U=")
        before = memory.context("测试会话", "system")[-1]["content"]
        self.assertIsInstance(before, list)

        self.assertTrue(memory.resolve_latest_visual(
            "测试会话",
            "测试联系人",
            "[图片]",
            "image",
            "一张蓝色壁纸",
        ))

        after = memory.context("测试会话", "system")[-1]["content"]
        self.assertIsInstance(after, str)
        self.assertIn("一张蓝色壁纸", after)
        self.assertNotIn("aW1hZ2U=", after)

    def test_parse_listener_event_filters_own_and_system_messages(self):
        now = datetime(2026, 8, 6, 12, 3)
        payload = {
            "chat_title": "测试群",
            "new_message": json.dumps(
                [
                    {"who": "我", "message": "自己的消息", "send_date": "2026-08-06 12:00"},
                    {"who": "系统", "message": "系统消息", "send_date": "2026-08-06 12:01"},
                    {"who": "测试联系人", "message": "你好", "send_date": "2026-08-06 12:02"},
                ],
                ensure_ascii=False,
            ),
        }
        messages = parse_listener_event(json.dumps(payload, ensure_ascii=False), now=now)
        self.assertEqual(1, len(messages))
        self.assertEqual("测试群", messages[0].chat_title)
        self.assertEqual("测试联系人", messages[0].who)

    def test_parse_listener_event_uses_only_newest_fresh_credible_inbound(self):
        payload = {
            "chat_title": "AI",
            "new_message": json.dumps(
                [
                    {"who": "09", "message": "OCR garbage", "send_date": "2026-08-07T09:40:00"},
                    {"who": "圆子", "message": "bot reply", "send_date": "2026-08-07T09:40:00"},
                    {"who": "测试好友", "message": "old history", "send_date": "2026-08-07T08:00:00"},
                    {"who": "测试好友", "message": "第一句", "send_date": "2026-08-07T09:39:00"},
                    {"who": "测试好友", "message": "第二句", "send_date": "2026-08-07T09:40:00"},
                ],
                ensure_ascii=False,
            ),
        }
        messages = parse_listener_event(
            payload,
            self_names={"圆子"},
            now=datetime(2026, 8, 7, 9, 41),
        )
        self.assertEqual(1, len(messages))
        self.assertEqual("第二句", messages[0].content)

    def test_parse_listener_event_keeps_multiple_messages_in_latest_burst(self):
        payload = {
            "chat_title": "芝士圆子",
            "new_message": [
                {"who": "芝士圆子", "message": "问题一", "send_date": "2026-08-10T18:20:00"},
                {"who": "芝士圆子", "message": "问题二", "send_date": "2026-08-10T18:20:00"},
                {"who": "芝士圆子", "message": "问题三", "send_date": "2026-08-10T18:20:05"},
            ],
        }

        messages = parse_listener_event(payload, now=datetime(2026, 8, 10, 18, 20, 6))

        self.assertEqual(["问题一", "问题二", "问题三"], [item.content for item in messages])

    def test_parse_listener_event_rejects_unparseable_or_stale_dates(self):
        payload = {
            "chat_title": "AI",
            "new_message": [
                {"who": "测试好友", "message": "missing date"},
                {"who": "测试好友", "message": "stale", "send_date": "2026-08-07T09:00:00"},
            ],
        }
        self.assertEqual([], parse_listener_event(payload, now=datetime(2026, 8, 7, 9, 30)))

    def test_parse_listener_event_keeps_fresh_message_when_sdk_omits_sender(self):
        payload = {
            "chat_title": "MyBot测试群2",
            "new_message": [{
                "who": "",
                "message": "你把这个文档改一下，在里面加一首打油诗",
                "send_date": "2026-08-10T17:53:00",
                "message_type": 0,
            }],
        }

        message = parse_listener_event(payload, now=datetime(2026, 8, 10, 17, 53, 5))[0]

        self.assertEqual("对方", message.who)
        self.assertIn("打油诗", message.content)

    def test_parse_conversation_preview_extracts_group_sender(self):
        message = parse_conversation_preview(
            {
                "conversation_title": "测试群",
                "conversation_content": "测试好友: 你好",
                "time": "10:20",
                "not_read_numbr": 0,
            },
            now=datetime(2026, 8, 7, 10, 20),
        )
        self.assertIsNotNone(message)
        self.assertEqual("测试好友", message.who)
        self.assertEqual("你好", message.content)

    def test_parse_conversation_preview_does_not_treat_sentence_as_sender(self):
        message = parse_conversation_preview(
            {
                "conversation_title": "测试群",
                "conversation_content": "查了下，附近吃的比较一般，建议按距离选: 第一家餐厅",
                "time": "10:20",
                "not_read_numbr": 0,
            }
        )

        self.assertIsNotNone(message)
        self.assertEqual("对方", message.who)
        self.assertIn("建议按距离选", message.content)

    def test_parse_conversation_preview_ignores_unread_and_own_sender(self):
        unread = {
            "conversation_title": "测试群",
            "conversation_content": "测试好友: 你好",
            "not_read_numbr": 1,
        }
        own = {
            "conversation_title": "测试群",
            "conversation_content": "圆子: 已回复",
            "not_read_numbr": 0,
        }
        self.assertIsNone(parse_conversation_preview(unread))
        self.assertIsNone(parse_conversation_preview(own, self_names={"圆子"}))

    def test_primary_failure_uses_backup(self):
        client = StubClient([RuntimeError("primary failed"), "backup reply"])
        primary = ModelConfig(provider="openai", base_url="https://primary.example", model="primary")
        backup = ModelConfig(provider="openai", base_url="https://backup.example", model="backup")
        self.assertEqual("backup reply", client.generate_with_fallback(primary, backup, []))

    def test_fallback_passes_bounded_timeout_to_both_models(self):
        calls = []

        class TimeoutClient(ChatModelClient):
            def generate(self, config, messages, *, timeout=120):
                calls.append((config.model, timeout))
                if config.model == "primary":
                    raise TimeoutError("slow primary")
                return "backup reply"

        client = TimeoutClient()
        primary = ModelConfig(provider="openai", base_url="https://primary.example", model="primary")
        backup = ModelConfig(provider="openai", base_url="https://backup.example", model="backup")
        self.assertEqual("backup reply", client.generate_with_fallback(primary, backup, [], timeout=25))
        self.assertEqual([("primary", 25), ("backup", 25)], calls)

    def test_openai_endpoint_accepts_root_or_v1_url(self):
        self.assertEqual("https://example.com/v1/models", ChatModelClient._openai_endpoint("https://example.com", "/models"))
        self.assertEqual("https://example.com/v1/models", ChatModelClient._openai_endpoint("https://example.com/v1", "/models"))

    def test_generate_image_writes_returned_base64(self):
        client = ChatModelClient()
        buffer = BytesIO()
        Image.new("RGB", (1, 1), "red").save(buffer, format="PNG")
        raw = buffer.getvalue()
        client._request_json = lambda *args, **kwargs: {"data": [{"b64_json": base64.b64encode(raw).decode("ascii")}]}  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(client.generate_image(ImageConfig(model="gpt-image-1.5"), "test", directory))
            self.assertEqual(raw, path.read_bytes())

    def test_edit_image_uses_source_image_and_writes_result(self):
        client = ChatModelClient()
        buffer = BytesIO()
        Image.new("RGB", (1, 1), "blue").save(buffer, format="PNG")
        edited = buffer.getvalue()
        calls = []

        def request(url, fields, file_field, file_path, api_key, *, timeout):
            calls.append((url, fields, file_field, Path(file_path), api_key, timeout))
            return {"data": [{"b64_json": base64.b64encode(edited).decode("ascii")}]} 

        client._request_multipart_json = request  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            source.write_bytes(edited)
            output = Path(client.edit_image(
                ImageConfig(base_url="https://images.example/v1", model="gpt-image-1.5", api_key="secret"),
                "把招牌改成肯德基",
                source,
                directory,
            ))

            self.assertEqual(edited, output.read_bytes())
            self.assertIn("/images/edits", calls[0][0])
            self.assertEqual("把招牌改成肯德基", calls[0][1]["prompt"])
            self.assertEqual("image", calls[0][2])
            self.assertEqual(source, calls[0][3])
            self.assertEqual(180, calls[0][5])

    def test_listener_event_keeps_image_for_vision_context(self):
        payload = {
            "chat_title": "图片测试群",
            "new_message": [
                {
                    "who": "测试联系人",
                    "message": "图片",
                    "send_date": "2026-08-07T15:10:01",
                    "message_type": 1,
                    "image_base64_str": "aW1hZ2U=",
                }
            ],
        }
        messages = parse_listener_event(payload, now=datetime(2026, 8, 7, 15, 10, 2))
        self.assertEqual(1, len(messages))
        self.assertEqual("aW1hZ2U=", messages[0].image_base64)
        self.assertEqual(1, messages[0].message_type)

    def test_listener_event_keeps_received_file_attachment(self):
        payload = {
            "chat_title": "文件测试",
            "new_message": [{
                "who": "测试联系人",
                "message": "文件\n报告.docx\n18 KB",
                "send_date": "2026-08-07T15:10:01",
                "message_type": 7,
                "file_name": "报告.docx",
                "file_path": "C:/wechat/报告.docx",
            }],
        }
        message = parse_listener_event(payload, now=datetime(2026, 8, 7, 15, 10, 2))[0]
        self.assertEqual("报告.docx", message.attachments[0].name)
        self.assertEqual("C:/wechat/报告.docx", message.attachments[0].path)
        self.assertEqual("file", message.attachments[0].kind)

    def test_listener_event_accepts_file_callback_with_minimum_timestamp(self):
        payload = {
            "chat_title": "文件测试",
            "new_message": [{
                "who": "测试联系人",
                "message": "文件\n报告.docx\n18 KB\n微信电脑版",
                "send_date": "0001-01-01T00:00:00",
                "message_type": 4,
                "file_name": "报告.docx",
                "file_path": "C:/wechat/报告.docx",
            }],
        }

        message = parse_listener_event(payload, now=datetime(2026, 8, 10, 18, 5))[0]

        self.assertEqual("2026-08-10T18:05:00", message.send_date)
        self.assertEqual("报告.docx", message.attachments[0].name)

    def test_listener_event_reads_sdk_image_file_when_base64_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sticker.gif"
            path.write_bytes(b"GIF89a")
            payload = {
                "chat_title": "表情测试",
                "new_message": [{
                    "who": "测试联系人",
                    "message": "动画表情",
                    "send_date": "2026-08-07T15:10:01",
                    "message_type": 3,
                    "ImageFile": str(path),
                }],
            }
            message = parse_listener_event(payload, now=datetime(2026, 8, 7, 15, 10, 2))[0]
            self.assertEqual(base64.b64encode(b"GIF89a").decode("ascii"), message.image_base64)
            self.assertEqual("sticker", message.attachments[0].kind)

    def test_listener_event_rejects_weekday_ocr_as_sender(self):
        payload = {
            "chat_title": "测试群",
            "new_message": [
                {
                    "who": "星期",
                    "message": "不是发送者",
                    "send_date": "2026-08-07T15:10:01",
                }
            ],
        }
        self.assertEqual([], parse_listener_event(payload, now=datetime(2026, 8, 7, 15, 10, 2)))


if __name__ == "__main__":
    unittest.main()
