import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mybot_ui.episodic_memory import Episode, EpisodicMemoryStore


class EpisodicMemoryTests(unittest.TestCase):
    def test_store_migrates_person_alias_and_deduplicates_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episodes.json"
            episode = {
                "user_message": "同一条消息",
                "assistant_reply": "同一条回复",
                "timestamp": "2026-08-09T10:00:00+08:00",
                "importance": 2,
            }
            path.write_text(json.dumps({
                "Rosa蔷薇": [episode],
                "Rosa蓉薇": [episode],
            }, ensure_ascii=False), encoding="utf-8")
            store = EpisodicMemoryStore(path, aliases={"Rosa蓉薇": "Rosa蔷薇"})
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(["Rosa蔷薇"], list(payload))
            self.assertEqual(1, len(store.retrieve("Rosa蓉薇", "消息")))

    def test_store_round_trip_and_person_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episodes.json"
            store = EpisodicMemoryStore(path)
            self.assertTrue(store.add("芝士圆子", "我最近在学摄影", "你拍什么题材比较多"))
            self.assertTrue(store.add("群友甲", "我喜欢跑步", "最近跑了多远"))

            loaded = EpisodicMemoryStore(path)
            prompt = loaded.prompt("芝士圆子", "相机怎么选")
            self.assertIn("摄影", prompt)
            self.assertNotIn("跑步", prompt)

    def test_store_lists_counts_reloads_and_deletes_recent_episodes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episodes.json"
            store = EpisodicMemoryStore(path)
            store.add("芝士圆子", "第一条", "第一条回复")
            store.add("芝士圆子", "第二条", "第二条回复")
            store.add("群友甲", "群消息", "群回复")

            self.assertEqual(["群友甲", "芝士圆子"], store.names())
            self.assertEqual(3, store.count())
            self.assertEqual(2, store.count("芝士圆子"))
            self.assertEqual("第二条", store.recent("芝士圆子", limit=1)[0].user_message)
            self.assertTrue(store.delete_person("群友甲"))
            self.assertFalse(store.delete_person("不存在"))
            self.assertEqual(2, store.count())

            path.write_text(json.dumps({
                "外部更新": [Episode(
                    "外部消息",
                    "外部回复",
                    "2026-08-09T15:00:00+08:00",
                    3,
                ).to_mapping()],
            }, ensure_ascii=False), encoding="utf-8")
            store.reload()
            self.assertEqual(["外部更新"], store.names())
            self.assertEqual(1, store.count())

    def test_relevance_can_outrank_newer_unrelated_episode(self):
        now = datetime.now(timezone.utc)
        data = {
            "芝士圆子": [
                Episode(
                    "我周末喜欢拍照，最近在看相机",
                    "可以先确定常拍的题材",
                    (now - timedelta(days=5)).isoformat(),
                    4,
                ).to_mapping(),
                Episode(
                    "今天中午吃了面",
                    "味道怎么样",
                    now.isoformat(),
                    2,
                ).to_mapping(),
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episodes.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            store = EpisodicMemoryStore(path)

            result = store.retrieve("芝士圆子", "想买相机拍照", limit=1)

            self.assertIn("相机", result[0].user_message)

    def test_sensitive_or_duplicate_content_is_not_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episodes.json"
            store = EpisodicMemoryStore(path)
            self.assertFalse(store.add("芝士圆子", "我的密码是 abc123", "知道了"))
            self.assertTrue(store.add("芝士圆子", "我喜欢摄影", "记住啦"))
            self.assertFalse(store.add("芝士圆子", "我喜欢摄影", "记住啦"))

            content = path.read_text(encoding="utf-8")
            self.assertNotIn("abc123", content)
            self.assertEqual(1, len(json.loads(content)["芝士圆子"]))


if __name__ == "__main__":
    unittest.main()
