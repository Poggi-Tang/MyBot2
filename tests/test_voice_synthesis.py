from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mybot_ui.app_v2 import NAVIGATION_TITLES
from mybot_ui.catalog import build_options
from mybot_ui.voice_synthesis import (
    VoiceApiConfig,
    boson_voice_list_endpoint,
    list_boson_voices,
    local_voice_stream_endpoint,
    synthesize_voice_file,
    voice_api_endpoint,
)


class _Response:
    def __init__(self, body: bytes, content_type: str = "audio/wav") -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


class VoiceSynthesisTests(unittest.TestCase):
    def test_navigation_order_matches_product_structure(self):
        self.assertEqual(
            (
                "对话配置",
                "记忆管理",
                "功能列表",
                "快捷能力",
                "测试模块",
                "系统配置",
            ),
            NAVIGATION_TITLES,
        )

    def test_voice_api_endpoint_accepts_root_v1_and_full_endpoint(self):
        self.assertEqual(
            "https://example.com/v1/audio/speech",
            voice_api_endpoint("https://example.com"),
        )
        self.assertEqual(
            "https://example.com/v1/audio/speech",
            voice_api_endpoint("https://example.com/v1"),
        )
        self.assertEqual(
            "https://example.com/v1/audio/speech",
            voice_api_endpoint("https://example.com/v1/audio/speech"),
        )

    def test_local_voice_endpoint_rejects_remote_hosts(self):
        self.assertEqual(
            "http://127.0.0.1:50001/v1/audio/speech/stream",
            local_voice_stream_endpoint("http://127.0.0.1:50001"),
        )
        with self.assertRaisesRegex(ValueError, "回环地址"):
            local_voice_stream_endpoint("https://example.com")

    def test_boson_voice_list_uses_returned_voice_ids(self):
        response = _Response(json.dumps({
            "object": "list",
            "data": [
                {"voice": "voice_nora", "description": "Nora"},
                {"voice": "voice_nora", "description": "duplicate"},
                {"voice_id": "voice_serena"},
            ],
        }).encode("utf-8"), "application/json")
        with patch(
            "mybot_ui.voice_synthesis.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            voices = list_boson_voices("https://api.boson.ai/v1", "secret")

        request = urlopen.call_args.args[0]
        self.assertEqual(
            "https://api.boson.ai/v1/audio/voices",
            boson_voice_list_endpoint("https://api.boson.ai/v1/audio/speech"),
        )
        self.assertEqual("GET", request.method)
        self.assertEqual(("voice_nora", "voice_serena"), voices)

    def test_api_synthesis_sends_selected_model_voice_and_style(self):
        response = _Response(b"RIFFtest-audio")
        with tempfile.TemporaryDirectory() as directory, patch(
            "mybot_ui.voice_synthesis.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            path = synthesize_voice_file(
                VoiceApiConfig(
                    base_url="https://example.com/v1",
                    model="qwen3-tts-flash",
                    api_key="secret",
                    voice="Cherry",
                    speed=1.2,
                    instructions="自然聊天",
                ),
                "你好",
                Path(directory),
            )
            request = urlopen.call_args.args[0]
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual("https://example.com/v1/audio/speech", request.full_url)
            self.assertEqual("qwen3-tts-flash", payload["model"])
            self.assertEqual("Cherry", payload["voice"])
            self.assertEqual("自然聊天", payload["instructions"])
            self.assertEqual(b"RIFFtest-audio", path.read_bytes())

    def test_boson_synthesis_uses_supported_request_fields_only(self):
        response = _Response(b"RIFFboson-audio")
        with tempfile.TemporaryDirectory() as directory, patch(
            "mybot_ui.voice_synthesis.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            synthesize_voice_file(
                VoiceApiConfig(
                    base_url="https://api.boson.ai/v1",
                    model="higgs-tts-3",
                    api_key="secret",
                    voice="default",
                    provider="boson",
                    speed=1.5,
                    instructions="不会发送给 Boson",
                ),
                "你好",
                Path(directory),
            )
            payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
            self.assertEqual(
                {
                    "model": "higgs-tts-3",
                    "input": "你好",
                    "voice": "default",
                    "response_format": "wav",
                    "stream": False,
                },
                payload,
            )

    def test_streaming_gateway_options_include_local_endpoint(self):
        options = build_options("SendStreamingVoiceMessage", {
            "who": "测试会话",
            "request": {"input": "你好"},
            "endpoint": "http://127.0.0.1:50001/v1/audio/speech/stream",
        })
        self.assertEqual(
            "http://127.0.0.1:50001/v1/audio/speech/stream",
            options["endpoint"],
        )


if __name__ == "__main__":
    unittest.main()
