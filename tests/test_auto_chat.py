import unittest
from unittest.mock import patch

from mybot_ui.auto_chat import (
    AUTO_REPLY_DELIMITER,
    ListenerMessageCursor,
    ReplyKind,
    group_reply_trigger,
    incoming_dedupe_feature,
    infer_sticker_query,
    model_reply_action,
    model_reply_mode_instruction,
    model_sticker_request,
    parse_auto_reply_segments,
    requested_action,
    sanitize_auto_reply_text,
    select_sticker_item,
    sticker_item_send_value,
)
from mybot_ui.catalog import TOOLS


class ListenerMessageCursorTests(unittest.TestCase):
    def test_repeated_callback_is_deduplicated_for_cross_source_delay(self):
        cursor = ListenerMessageCursor()
        with patch("mybot_ui.auto_chat.time.monotonic", side_effect=[10.0, 40.0, 611.0]):
            self.assertTrue(cursor.accept_incoming("会话", "same"))
            self.assertFalse(cursor.accept_incoming("会话", "same"))
            self.assertTrue(cursor.accept_incoming("会话", "same"))

    def test_every_sdk_function_has_a_supported_action_type(self):
        supported = {kind.value for kind in ReplyKind}
        self.assertTrue(TOOLS)
        for spec in TOOLS:
            self.assertIn(spec.action_type, supported, spec.function)

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

    def test_non_visual_creation_is_not_mistaken_for_image_generation(self):
        for text in (
            "做一首诗，关于上海8月份气候的",
            "帮我制作一份工作计划",
            "生成一段产品文案",
        ):
            with self.subTest(text=text):
                self.assertEqual(ReplyKind.TEXT, requested_action(text).kind)

        self.assertEqual(
            ReplyKind.IMAGE,
            requested_action("帮我制作一张上海夏天的海报").kind,
        )

    def test_voice_and_sticker_requests_are_selected(self):
        self.assertEqual(ReplyKind.VOICE, requested_action("用语音回复我").kind)
        for text in (
            "今天闵行区的天气，语音播报给我",
            "把结果读给我听",
            "念给我听",
            "查完说给我听",
        ):
            with self.subTest(text=text):
                self.assertEqual(ReplyKind.VOICE, requested_action(text).kind)
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

    def test_group_reply_trigger_accepts_wechat_mention_spacing(self):
        incoming = type("Message", (), {
            "content": "@圆子\u2005你怎么看",
            "message_type": 0,
            "is_reference": False,
        })()
        self.assertEqual(
            (True, "mentioned"),
            group_reply_trigger(incoming, ai_names=("圆子",)),
        )

    def test_group_reply_trigger_accepts_compact_preview_mention(self):
        incoming = type("Message", (), {
            "content": "@圆子说话",
            "message_type": 0,
            "is_reference": False,
        })()
        self.assertEqual(
            (True, "mentioned"),
            group_reply_trigger(incoming, ai_names=("圆子",)),
        )

    def test_group_reply_trigger_only_accepts_quotes_of_ai_messages(self):
        quoted_ai = type("Message", (), {
            "content": "这个呢",
            "message_type": 0,
            "is_reference": True,
            "referenced_who": "圆子",
            "referenced_message": "上一次回复",
        })()
        quoted_other = type("Message", (), {
            "content": "这个呢",
            "message_type": 0,
            "is_reference": True,
            "referenced_who": "群友甲",
            "referenced_message": "群友的消息",
        })()
        self.assertEqual(
            (True, "referenced_ai"),
            group_reply_trigger(quoted_ai, ai_names=("圆子",)),
        )
        self.assertEqual(
            (False, "referenced_other_member"),
            group_reply_trigger(
                quoted_other,
                ai_names=("圆子",),
                recent_assistant_messages=("上一次回复",),
            ),
        )

    def test_group_reply_trigger_matches_recent_reply_when_sender_is_missing(self):
        incoming = type("Message", (), {
            "content": "接着说",
            "message_type": 17,
            "referenced_who": "",
            "referenced_message": "上一次回复",
        })()
        self.assertEqual(
            (True, "referenced_recent_reply"),
            group_reply_trigger(
                incoming,
                ai_names=("圆子",),
                recent_assistant_messages=("上一次回复",),
            ),
        )

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
        self.assertEqual(("第一句\n第二句",), parse_auto_reply_segments("第一句。\n第二句~"))

    def test_long_coherent_reply_stays_in_one_bubble(self):
        reply = "这是一段需要保持完整语义的回复，" * 20
        self.assertEqual((reply,), parse_auto_reply_segments(reply))

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

    def test_model_can_choose_reply_transport_with_strict_markers(self):
        text_action, text = model_reply_action("我也觉得挺有意思")
        voice_action, voice = model_reply_action(
            "<MYBOT_VOICE>那我认真讲给你听</MYBOT_VOICE>"
        )
        sticker_action, sticker_text = model_reply_action("<MYBOT_STICKER:开心>")
        image_action, image_text = model_reply_action("<MYBOT_IMAGE:窗边晒太阳的猫>")

        self.assertEqual(ReplyKind.TEXT, text_action.kind)
        self.assertEqual("我也觉得挺有意思", text)
        self.assertEqual(ReplyKind.VOICE, voice_action.kind)
        self.assertEqual("那我认真讲给你听", voice)
        self.assertEqual(ReplyKind.STICKER, sticker_action.kind)
        self.assertEqual("开心", sticker_action.argument)
        self.assertEqual("", sticker_text)
        self.assertEqual(ReplyKind.IMAGE, image_action.kind)
        self.assertEqual("窗边晒太阳的猫", image_action.argument)
        self.assertEqual("", image_text)

    def test_explicit_reference_and_tap_requests_have_types(self):
        self.assertEqual(
            ReplyKind.REFERENCE,
            requested_action("引用我这条消息回复我").kind,
        )
        self.assertEqual(ReplyKind.TAP, requested_action("拍一拍我").kind)

    def test_structured_action_supports_every_typed_capability(self):
        for kind in (
            ReplyKind.TEXT,
            ReplyKind.REFERENCE,
            ReplyKind.IMAGE,
            ReplyKind.IMAGE_EDIT,
            ReplyKind.VOICE,
            ReplyKind.EMOJI,
            ReplyKind.STICKER,
            ReplyKind.FILE,
            ReplyKind.TAP,
            ReplyKind.SDK_TOOL,
            ReplyKind.MCP_TOOL,
            ReplyKind.SKILL_TASK,
            ReplyKind.CLI_TASK,
        ):
            payload = (
                '<MYBOT_ACTION>{"type":"' + kind.value + '",'
                '"content":"完成","argument":"参数","function":"GetTitle",'
                '"arguments":{"who":"芝士圆子"}}</MYBOT_ACTION>'
            )
            action, content = model_reply_action(payload)
            self.assertEqual(kind, action.kind)
            self.assertEqual("完成", content)
            self.assertEqual("参数", action.argument)
            self.assertEqual("GetTitle", action.function)
            self.assertEqual({"who": "芝士圆子"}, action.arguments)

    def test_invalid_structured_action_falls_back_to_plain_text(self):
        value = '<MYBOT_ACTION>{invalid json}</MYBOT_ACTION>'
        action, content = model_reply_action(value)
        self.assertEqual(ReplyKind.TEXT, action.kind)
        self.assertEqual(value, content)

    def test_reply_transport_markers_must_occupy_the_whole_reply(self):
        action, content = model_reply_action(
            "给你说一句 <MYBOT_VOICE>晚安</MYBOT_VOICE>"
        )
        self.assertEqual(ReplyKind.TEXT, action.kind)
        self.assertIn("晚安", content)

    def test_reply_mode_prompt_lists_capabilities_without_fixed_wording(self):
        prompt = model_reply_mode_instruction(voice_enabled=True, codex_enabled=True)
        self.assertIn("文字", prompt)
        self.assertIn("<MYBOT_STICKER", prompt)
        self.assertIn("<MYBOT_VOICE>", prompt)
        self.assertIn("<MYBOT_IMAGE:", prompt)
        self.assertIn('"type":"cli_task|mcp_tool|skill_task"', prompt)
        self.assertIn('"type":"reference"', prompt)
        self.assertIn("不是固定话术", prompt)

        disabled = model_reply_mode_instruction(voice_enabled=False, codex_enabled=False)
        self.assertIn("语音当前不可用", disabled)
        self.assertIn("CLI/MCP/Skill 工具当前不可用", disabled)

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

    def test_excess_model_segments_merge_into_the_last_bubble(self):
        reply = AUTO_REPLY_DELIMITER.join(("一", "二", "三", "四", "五"))
        self.assertEqual(("一", "二", "三", "四\n五"), parse_auto_reply_segments(reply))


if __name__ == "__main__":
    unittest.main()
