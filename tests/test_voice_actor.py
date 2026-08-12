from __future__ import annotations

import json
import unittest

from mybot_ui.chat_engine import ModelConfig
from mybot_ui.voice_actor import (
    HiggsVoiceActor,
    VoicePerformanceError,
    fallback_voice_performance,
    parse_voice_performance,
)


class _Client:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    def generate_with_fallback(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class VoiceActorTests(unittest.TestCase):
    def test_plan_preserves_text_and_renders_higgs_tags(self):
        reply = "你居然现在才发现？不过没关系，我一直都在。"
        response = json.dumps({"segments": [
            {
                "text": "你居然现在才发现？",
                "emotion": "amusement",
                "style": "",
                "speed": "fast",
                "pitch": "high",
                "expressiveness": "high",
                "pause_after": "long_pause",
                "sfx": "",
            },
            {
                "text": "不过没关系，我一直都在。",
                "emotion": "affection",
                "style": "whispering",
                "speed": "slow",
                "pitch": "normal",
                "expressiveness": "normal",
                "pause_after": "none",
                "sfx": "",
            },
        ]}, ensure_ascii=False)
        client = _Client(response)
        actor = HiggsVoiceActor(client)

        plan = actor.plan(
            ModelConfig(model="test"),
            None,
            user_message="你是不是才知道？",
            reply_text=reply,
            direction="像朋友聊天",
            intensity="dramatic",
        )

        self.assertEqual(reply, "".join(segment.text for segment in plan.segments))
        self.assertEqual(0.2, client.calls[0][0][0].temperature)
        self.assertEqual(
            (
                "<|emotion:amusement|><|prosody:speed_fast|>"
                "<|prosody:pitch_high|><|prosody:expressive_high|>"
                "你居然现在才发现？<|prosody:long_pause|>",
                "<|emotion:affection|><|style:whispering|>"
                "<|prosody:speed_slow|>不过没关系，我一直都在。",
            ),
            plan.higgs_inputs(),
        )

    def test_parser_rejects_rewritten_reply(self):
        response = json.dumps({"segments": [{"text": "被改写的回复"}]}, ensure_ascii=False)
        with self.assertRaisesRegex(VoicePerformanceError, "改写"):
            parse_voice_performance(response, "原回复")

    def test_parser_accepts_punctuation_only_change_and_restores_original(self):
        response = json.dumps({"segments": [
            {"text": "宝宝，", "emotion": "affection"},
            {"text": "我不能瞎报给你呀。", "emotion": "helplessness"},
        ]}, ensure_ascii=False)

        plan = parse_voice_performance(response, "宝宝，我不能瞎报给你呀")

        self.assertEqual("宝宝，我不能瞎报给你呀", "".join(
            segment.text for segment in plan.segments
        ))
        self.assertEqual("宝宝，", plan.segments[0].text)
        self.assertEqual("我不能瞎报给你呀", plan.segments[1].text)

    def test_parser_removes_unlicensed_sfx_and_unknown_tags(self):
        response = json.dumps({"segments": [{
            "text": "我知道了。",
            "emotion": "not-real",
            "style": "robot",
            "speed": "warp",
            "pitch": "normal",
            "expressiveness": "normal",
            "pause_after": "none",
            "sfx": "laughter",
        }]}, ensure_ascii=False)

        segment = parse_voice_performance(response, "我知道了。").segments[0]

        self.assertEqual("", segment.emotion)
        self.assertEqual("", segment.style)
        self.assertEqual("normal", segment.speed)
        self.assertEqual("", segment.sfx)
        self.assertEqual("我知道了。", segment.higgs_input())

    def test_fallback_uses_safe_single_segment(self):
        plan = fallback_voice_performance(
            "哈哈，原来是这样！",
            intensity="dramatic",
            base_speed=1.2,
        )

        self.assertEqual(1, len(plan.segments))
        self.assertEqual("amusement", plan.segments[0].emotion)
        self.assertEqual("fast", plan.segments[0].speed)
        self.assertEqual("high", plan.segments[0].expressiveness)


if __name__ == "__main__":
    unittest.main()
