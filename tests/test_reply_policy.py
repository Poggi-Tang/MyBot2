import unittest

from mybot_ui.chat_engine import ConversationMemory
from mybot_ui.reply_policy import ReplyPolicy


class ReplyPolicyTests(unittest.TestCase):
    def test_defaults_distinguish_boundaries_style_and_refusal(self):
        policy = ReplyPolicy.from_mapping({})
        messages, matched = policy.system_messages(
            chat_title="测试联系人甲",
            sender="测试联系人甲",
            is_group=False,
        )

        self.assertIn("你的名字是“圆子”", messages[0])
        self.assertIn("当前消息发送者的名称是“测试联系人甲”", messages[0])
        self.assertIn("不要输出不在对话中的编号、哈希", messages[0])
        self.assertIn("回复边界优先级最高", messages[1])
        self.assertIn("对外只以圆子的身份说话", messages[1])
        self.assertIn("不附数据源", messages[2])
        self.assertTrue(messages[2].startswith("通用回复方式："))
        self.assertTrue(messages[3].startswith("无法回复时的处理方式："))
        self.assertTrue(messages[4].startswith("私聊规则："))
        self.assertEqual(["identity:圆子", "global", "private"], matched)
        self.assertGreaterEqual(len(policy.example_dialogues), 4)

    def test_identity_and_examples_round_trip_as_style_references(self):
        policy = ReplyPolicy.from_mapping({
            "ai_name": "小圆",
            "ai_identity": "有耐心的聊天伙伴",
            "persona_traits": "说话轻松",
            "example_dialogues": "对方：累了\n小圆：歇会儿\n\n对方：早\n小圆：早呀",
        })
        restored = ReplyPolicy.from_mapping(policy.to_mapping())
        messages, matched = restored.system_messages(
            chat_title="测试联系人甲", sender="测试联系人甲", is_group=False
        )

        self.assertEqual("小圆", restored.ai_name)
        self.assertEqual(2, len(restored.example_dialogues))
        self.assertIn("不是当前对话、真实经历", messages[0])
        self.assertIn("对方：累了", messages[0])
        self.assertEqual("identity:小圆", matched[0])

    def test_contact_and_conversation_profiles_are_applied_after_common_rules(self):
        policy = ReplyPolicy.from_mapping({
            "contact_profiles": {
                "测试联系人甲": {
                    "relationship": "熟悉的测试联系人",
                    "style": "更口语化",
                    "instructions": "称呼对方为圆子",
                }
            },
            "conversation_profiles": {
                "测试群聊": {
                    "style": "群里保持简短",
                }
            },
        })
        messages, matched = policy.system_messages(
            chat_title="测试群聊",
            sender="测试联系人甲",
            is_group=True,
        )

        self.assertTrue(messages[4].startswith("群聊规则："))
        self.assertIn("熟悉的测试联系人", messages[5])
        self.assertIn("群里保持简短", messages[6])
        self.assertEqual(
            ["identity:圆子", "global", "group", "contact:测试联系人甲", "conversation:测试群聊"],
            matched,
        )

    def test_empty_profile_does_not_match_or_persist(self):
        policy = ReplyPolicy.from_mapping({"contact_profiles": {"空配置": {}}})
        self.assertEqual({}, policy.contact_profiles)
        self.assertEqual({}, policy.to_mapping()["contact_profiles"])

    def test_conversation_memory_keeps_policy_before_behavior_and_history(self):
        memory = ConversationMemory()
        memory.add_user("测试", "联系人", "你好")
        context = memory.context("测试", "身份", ["边界", "风格"])

        self.assertEqual(["身份", "边界", "风格"], [item["content"] for item in context[:3]])
        self.assertEqual("user", context[-1]["role"])


if __name__ == "__main__":
    unittest.main()
