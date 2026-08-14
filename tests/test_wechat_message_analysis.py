import unittest

from mybot_ui.wechat_message_analysis import (
    MESSAGE_AUTOMATION_ID,
    classify_message,
    parse_conversation_title,
    read_conversation_context,
)


class WeChatMessageAnalysisTests(unittest.TestCase):
    def test_conversation_title_distinguishes_group_and_private(self):
        group = parse_conversation_title("研发群(12)")
        private = parse_conversation_title("芝士圆子")

        self.assertEqual(("group", "研发群", 12), (group.kind, group.name, group.member_count))
        self.assertEqual(("private", "芝士圆子", None), (private.kind, private.name, private.member_count))

    def test_missing_title_control_is_treated_as_not_ready(self):
        class MissingTitleAutomation:
            @staticmethod
            def Control(**_kwargs):
                raise LookupError("title is rebuilding")

        context = read_conversation_context(MissingTitleAutomation())

        self.assertEqual(("unknown", ""), (context.kind, context.name))

    def test_supported_message_metadata_is_classified(self):
        cases = (
            ("你好", "mmui::ChatTextItemView", "text"),
            ("图片", "mmui::ChatBubbleReferItemView", "image"),
            ("动画表情[开心]", "mmui::ChatBubbleReferItemView", "sticker"),
            ("文件", "mmui::ChatBubbleItemView", "file"),
            ("12''", "mmui::ChatVoiceItemView", "voice"),
        )
        for name, class_name, expected in cases:
            with self.subTest(expected=expected):
                result = classify_message({
                    "AutomationId": MESSAGE_AUTOMATION_ID,
                    "Name": name,
                    "ClassName": class_name,
                })
                self.assertEqual(expected, result["type"])

    def test_quote_metadata_preserves_body_sender_and_content(self):
        result = classify_message({
            "AutomationId": MESSAGE_AUTOMATION_ID,
            "Name": "收到\n引用 Alice 的消息：原始内容",
            "ClassName": "mmui::ChatTextItemView",
        })

        self.assertEqual("quote_text", result["type"])
        self.assertEqual(
            {"sender": "Alice", "content": "原始内容", "type": "text", "body": "收到"},
            result["quote"],
        )


if __name__ == "__main__":
    unittest.main()
