import unittest
from unittest.mock import patch

from mybot_ui.auto_chat import (
    AUTO_REPLY_DELIMITER,
    ListenerMessageCursor,
    ReplyKind,
    incoming_dedupe_feature,
    infer_sticker_query,
    model_sticker_request,
    parse_auto_reply_segments,
    requested_action,
    sanitize_auto_reply_text,
    select_sticker_item,
    sticker_item_send_value,
)


class ListenerMessageCursorTests(unittest.TestCase):
    def test_repeated_callback_is_deduplicated_for_cross_source_delay(self):
        cursor = ListenerMessageCursor()
        with patch("mybot_ui.auto_chat.time.monotonic", side_effect=[10.0, 40.0, 611.0]):
            self.assertTrue(cursor.accept_incoming("会话", "same"))
            self.assertFalse(cursor.accept_incoming("会话", "same"))
            self.assertTrue(cursor.accept_incoming("会话", "same"))

    def test_listener_and_preview_identity_share_message_minute(self):
        listener = type("Message", (), {
            "who": "contact",
            "content": "same message",
            "send_date": "2026-08-10T09:21:23",
            "image_base64": "",
            "attachments": (),
        })()
        preview = type("Message", (), {
            "who": "other party",
            "content": "same message",
            "send_date": "2026-08-10T09:21:51|09:21",
            "image_base64": "",
            "attachments": (),
        })()

        self.assertEqual(
            incoming_dedupe_feature(listener, include_sender=False),
            incoming_dedupe_feature(preview, include_sender=False),
        )

    def test_identical_messages_in_different_minutes_have_distinct_identity(self):
        first = type("Message", (), {
            "who": "contact",
            "content": "same message",
            "send_date": "2026-08-10T09:21:59",
            "image_base64": "",
            "attachments": (),
        })()
        second = type("Message", (), {
            "who": "contact",
            "content": "same message",
            "send_date": "2026-08-10T09:22:01",
            "image_base64": "",
            "attachments": (),
        })()

        self.assertNotEqual(incoming_dedupe_feature(first), incoming_dedupe_feature(second))

    def test_outgoing_echo_is_remembered(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing("会话", "AI 回复")
        self.assertTrue(cursor.is_outgoing_echo("会话", "  ai   回复 "))

    def test_truncated_outgoing_preview_is_suppressed(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing("会话", "你说得对，能联网的话确实可以查。但我会先核对可靠来源再回复你。")
        self.assertTrue(cursor.is_outgoing_echo("会话", "你说得对，能联网的话确实可以查。但我会先…"))
        self.assertFalse(cursor.is_outgoing_echo("会话", "你说得对…"))
        self.assertFalse(cursor.is_outgoing_echo("会话", "你说得对，能联网的话确实可以查"))

    def test_outgoing_voice_suppresses_two_placeholder_surfaces(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_voice("会话", "这是语音内容")
        self.assertTrue(cursor.is_outgoing_echo("会话", "这是语音内容"))
        self.assertTrue(cursor.is_outgoing_voice_echo("会话", '[语音] 6"'))
        self.assertTrue(cursor.is_outgoing_voice_echo("会话", '语音6"秒'))
        self.assertFalse(cursor.is_outgoing_voice_echo("会话", "语音7秒"))

    def test_unrelated_text_does_not_consume_voice_echo(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_voice("会话", "这是语音内容")
        self.assertFalse(cursor.is_outgoing_voice_echo("会话", "你好"))
        self.assertTrue(cursor.is_outgoing_voice_echo("会话", "语音"))

    def test_failed_voice_send_can_roll_back_echo_markers(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_voice("会话", "没有发出去")
        cursor.cancel_outgoing_voice("会话", "没有发出去")
        self.assertFalse(cursor.is_outgoing_echo("会话", "没有发出去"))
        self.assertFalse(cursor.is_outgoing_voice_echo("会话", "语音6秒"))

    def test_outgoing_image_echo_is_consumed_only_once(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_media("会话", "[图片]")

        self.assertTrue(cursor.is_outgoing_media_echo("会话", "[图片]"))
        self.assertFalse(cursor.is_outgoing_media_echo("会话", "[图片]"))

    def test_user_image_after_sent_image_is_not_suppressed_as_text_echo(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_media("会话", "[图片]")
        self.assertFalse(cursor.is_outgoing_echo("会话", "[图片]"))
        self.assertTrue(cursor.is_outgoing_media_echo("会话", "[图片]"))

        self.assertFalse(cursor.is_outgoing_media_echo("会话", "[图片]"))

    def test_failed_image_send_can_roll_back_echo_marker(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_media("会话", "[图片]")
        cursor.cancel_outgoing_media("会话", "[图片]")

        self.assertFalse(cursor.is_outgoing_media_echo("会话", "[图片]"))

    def test_outgoing_file_echo_matches_listener_and_preview_formats(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_file("会话", "MyBot功能列表.md")

        self.assertTrue(cursor.is_outgoing_file_echo("会话", "[文件] MyBot功能列表.md"))
        self.assertTrue(cursor.is_outgoing_file_echo("会话", "文件\nMyBot功能列表.md"))
        self.assertFalse(cursor.is_outgoing_file_echo("会话", "[文件] MyBot功能列表.md"))

    def test_failed_file_send_can_roll_back_echo_markers(self):
        cursor = ListenerMessageCursor()
        cursor.record_outgoing_file("会话", "result.txt")
        cursor.cancel_outgoing_file("会话", "result.txt")

        self.assertFalse(cursor.is_outgoing_file_echo("会话", "[文件] result.txt"))


class ReplyPlanningTests(unittest.TestCase):
    def test_explicit_image_request_selects_image(self):
        action = requested_action("生成图片 一只戴眼镜的猫")
        self.assertEqual(ReplyKind.IMAGE, action.kind)
        self.assertEqual("一只戴眼镜的猫", action.argument)

    def test_natural_image_requests_are_selected(self):
        action = requested_action("你画一只鹦鹉的图片给我")
        self.assertEqual(ReplyKind.IMAGE, action.kind)
        self.assertEqual("一只鹦鹉", action.argument)
        self.assertEqual(
            ReplyKind.IMAGE,
            requested_action("帮我生成一张窗边的猫照片").kind,
        )

    def test_image_discussion_is_not_mistaken_for_generation(self):
        self.assertEqual(ReplyKind.TEXT, requested_action("你能看懂这张图片吗").kind)

    def test_voice_and_sticker_requests_are_selected(self):
        self.assertEqual(ReplyKind.VOICE, requested_action("用语音回复我").kind)
        sticker = requested_action("发一个捂脸表情")
        self.assertEqual(ReplyKind.STICKER, sticker.kind)
        self.assertEqual("捂脸", sticker.argument)

    def test_sticker_pack_requests_use_catalog_path(self):
        sticker = requested_action("发一个捂脸表情包")
        self.assertEqual(ReplyKind.STICKER, sticker.kind)
        self.assertEqual("捂脸", sticker.argument)

    def test_named_sticker_collection_requests_use_catalog_path(self):
        for text in ("发个可爱联盟的", "来个可爱联盟"):
            action = requested_action(text)
            self.assertEqual(ReplyKind.STICKER, action.kind)
            self.assertEqual("可爱联盟", action.argument)

    def test_group_mentions_and_sticker_styles_are_parsed(self):
        cases = {
            "@圆子呃再发一个表情包": "",
            "发这狗的表情包@圆子": "这狗",
            "发个蠢狗的表情包": "蠢狗",
            "你发默认表情干嘛，发点可爱的行不行": "可爱",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                action = requested_action(text)
                self.assertEqual(ReplyKind.STICKER, action.kind)
                self.assertEqual(expected, action.argument)

    def test_sticker_explanation_follow_up_is_text(self):
        self.assertEqual(
            ReplyKind.TEXT,
            requested_action("发完告诉我你为什么选这个").kind,
        )
        self.assertEqual(
            ReplyKind.TEXT,
            requested_action("你再发默认表情包我就给你斩token").kind,
        )

    def test_reply_output_removes_forbidden_punctuation(self):
        self.assertEqual("好呀明白了", sanitize_auto_reply_text("好呀~明白了。"))
        self.assertEqual(("第一句", "第二句"), parse_auto_reply_segments("第一句。\n第二句~"))

    def test_reply_output_removes_trailing_model_trace_artifact(self):
        self.assertEqual(
            "你说得对，我刚才称呼弄混了，抱歉",
            sanitize_auto_reply_text("你说得对，我刚才称呼弄混了，抱歉 bd6923"),
        )
        self.assertEqual("验证码是 123456", sanitize_auto_reply_text("验证码是 123456"))

    def test_reply_output_removes_internal_and_machine_traces(self):
        self.assertEqual(
            "我是圆子，刚才在忙",
            sanitize_auto_reply_text("我是AI，刚才在忙。"),
        )
        self.assertEqual(
            "结果已经弄好了",
            sanitize_auto_reply_text("结果已经弄好了。数据源：wttr.in"),
        )
        self.assertEqual("", sanitize_auto_reply_text("<MYBOT_STICKER:开心>"))
        self.assertNotIn(
            "后台",
            sanitize_auto_reply_text("我已经通过后台 Codex 完成了这个任务"),
        )

    def test_model_can_request_contextual_sticker_without_text(self):
        self.assertEqual("", model_sticker_request("<MYBOT_STICKER>"))
        self.assertEqual("这狗", model_sticker_request("<MYBOT_STICKER:这狗>"))
        self.assertIsNone(model_sticker_request("给你一个 <MYBOT_STICKER>"))

    def test_unspecified_sticker_uses_recent_conversation_semantics(self):
        self.assertEqual(
            "舔狗",
            infer_sticker_query("", "芝士圆子: 这次来个舔狗风格的"),
        )
        self.assertEqual(
            "可爱联盟",
            infer_sticker_query("可爱联盟", "之前聊过狗狗"),
        )

    def test_sticker_selection_excludes_default_and_resolves_alias(self):
        items = [
            {"Category": "默认表情", "Name": "微笑", "Mode": "semantic"},
            {"Category": "可爱联盟14", "Name": "爱心", "Mode": "semantic"},
            {"Category": "这狗13", "Name": "吃瓜", "Mode": "semantic"},
            {"Category": "自定义表情", "Name": "", "Hash": "ABCDEF0123456789", "Mode": "visual"},
        ]
        cute, _reason = select_sticker_item(items, "可爱")
        dog, _reason = select_sticker_item(items, "蠢狗")
        custom, _reason = select_sticker_item(items, "", selection_index=2)
        self.assertEqual("可爱联盟14", cute["Category"])
        self.assertEqual("这狗13", dog["Category"])
        self.assertNotEqual("默认表情", custom["Category"])
        if custom["Mode"] == "visual":
            self.assertEqual(custom["Hash"], sticker_item_send_value(custom))

    def test_model_delimiter_creates_multiple_bubbles(self):
        segments = parse_auto_reply_segments(f"第一句{AUTO_REPLY_DELIMITER}第二句")
        self.assertEqual(("第一句", "第二句"), segments)


if __name__ == "__main__":
    unittest.main()
