import json
import tempfile
import unittest
from pathlib import Path

from mybot_ui.chat_engine import ModelConfig
from mybot_ui.personal_memory import (
    PersonalMemoryLearner,
    PersonalMemoryStore,
    PersonalProfile,
    person_id,
)


class StubClient:
    def __init__(self, response):
        self.response = response
        self.messages = None

    def generate_with_fallback(self, primary, backup, messages):
        self.messages = messages
        return self.response


class PersonalMemoryTests(unittest.TestCase):
    def test_person_id_uses_contact_for_private_and_sender_for_group(self):
        self.assertEqual("芝士圆子", person_id("芝士圆子", "对方", False))
        self.assertEqual("芝士圆子", person_id("MyBot测试群2", "芝士圆子", True))

    def test_person_id_normalizes_configured_ocr_alias(self):
        aliases = {"Rosa蓉薇": "Rosa蔷薇"}
        self.assertEqual(
            "Rosa蔷薇",
            person_id("测试群", "Rosa蓉薇", True, aliases),
        )

    def test_store_migrates_alias_and_removes_ignored_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text(json.dumps({
                "Rosa蔷薇": {"facts": ["事实一"], "message_count": 1},
                "Rosa蓉薇": {"preferences": ["偏好一"], "message_count": 1},
                "收到，第29条按这个版本记录": {"summary": "错误档案"},
            }, ensure_ascii=False), encoding="utf-8")
            store = PersonalMemoryStore(
                path,
                aliases={"Rosa蓉薇": "Rosa蔷薇"},
                ignored_names={"收到，第29条按这个版本记录"},
            )
            profile = store.get("Rosa蔷薇")
            self.assertEqual(("事实一",), profile.facts)
            self.assertEqual(("偏好一",), profile.preferences)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(["Rosa蔷薇"], list(payload))

    def test_store_round_trip_and_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "personal-memory.json"
            store = PersonalMemoryStore(path)
            profile = PersonalProfile(
                preferred_name="芝士",
                preferences=("喜欢摄影",),
                communication_style="不喜欢太正式",
                message_count=2,
            )
            store.update("芝士圆子", profile)

            loaded = PersonalMemoryStore(path).get("芝士圆子")
            self.assertEqual(profile, loaded)
            self.assertIn("喜欢摄影", loaded.prompt("芝士圆子"))
            self.assertNotIn("message_count", loaded.prompt("芝士圆子"))

    def test_store_lists_reloads_and_deletes_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "personal-memory.json"
            store = PersonalMemoryStore(path)
            store.update("芝士圆子", PersonalProfile(summary="喜欢摄影"))
            store.update("群友甲", PersonalProfile(preferences=("喜欢跑步",)))

            self.assertEqual(["群友甲", "芝士圆子"], store.names())
            self.assertTrue(store.delete("群友甲"))
            self.assertFalse(store.delete("不存在"))
            self.assertEqual(["芝士圆子"], store.names())

            path.write_text(json.dumps({
                "外部更新": {"summary": "从磁盘重新加载"},
            }, ensure_ascii=False), encoding="utf-8")
            store.reload()
            self.assertEqual(["外部更新"], store.names())
            self.assertEqual("从磁盘重新加载", store.get("外部更新").summary)

    def test_profile_limits_and_deduplicates_model_output(self):
        profile = PersonalProfile.from_mapping({
            "preferred_name": "a" * 100,
            "facts": ["同一事实", "同一事实"] + [str(index) for index in range(20)],
        })
        self.assertEqual(60, len(profile.preferred_name))
        self.assertEqual(12, len(profile.facts))
        self.assertEqual(1, profile.facts.count("同一事实"))

    def test_prompt_prioritizes_items_relevant_to_current_message(self):
        profile = PersonalProfile(
            facts=("在广州工作", "养了一只猫", "周末练习摄影", "常喝冰美式", "喜欢悬疑电影", "最近换了键盘"),
        )

        prompt = profile.prompt("芝士圆子", "相机镜头该怎么选")

        self.assertIn("周末练习摄影", prompt)
        self.assertNotIn("在广州工作", prompt)

    def test_learner_updates_compact_profile_and_count(self):
        response = json.dumps({
            "preferred_name": "芝士",
            "summary": "正在学习摄影",
            "facts": [],
            "preferences": ["喜欢自然的聊天方式"],
            "communication_style": "口语化",
            "current_context": ["最近在学习摄影"],
            "avoid_topics": [],
        }, ensure_ascii=False)
        client = StubClient("```json\n" + response + "\n```")
        with tempfile.TemporaryDirectory() as directory:
            store = PersonalMemoryStore(Path(directory) / "memory.json")
            learner = PersonalMemoryLearner(client, store)
            learned = learner.learn(
                primary=ModelConfig(model="test"),
                backup=None,
                name="芝士圆子",
                user_message="叫我芝士就好，我最近在学摄影。",
                assistant_reply="好呀，芝士。",
            )

            self.assertEqual("芝士", learned.preferred_name)
            self.assertEqual(1, learned.message_count)
            self.assertEqual(learned, store.get("芝士圆子"))
            self.assertIn("existing_profile", client.messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
