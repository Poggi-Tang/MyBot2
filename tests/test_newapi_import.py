import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

from mybot_ui.app_v2 import MainWindow
from mybot_ui.chat_engine import ChatModelClient, ModelConfig
from mybot_ui.newapi_import import parse_newapi_connection


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()


class NewApiImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_parse_applies_requested_defaults(self):
        connection = parse_newapi_connection({
            "_type": "newapi_channel_conn",
            "key": "sk-test-secret",
            "url": "https://u32ai.com/",
        })

        self.assertEqual("https://u32ai.com", connection.base_url)
        self.assertEqual("https://u32ai.com/v1", connection.codex_base_url)
        self.assertEqual("gpt-5.6-sol", connection.chat_model)
        self.assertEqual("gpt-image-2", connection.image_model)
        self.assertEqual("high", connection.reasoning_effort)

    def test_existing_v1_is_not_duplicated(self):
        connection = parse_newapi_connection({
            "_type": "newapi_channel_conn",
            "key": "sk-test-secret",
            "url": "https://u32ai.com/v1",
        })
        self.assertEqual("https://u32ai.com/v1", connection.codex_base_url)

    def test_rejects_invalid_type_and_unsafe_url(self):
        with self.assertRaisesRegex(ValueError, "不支持的连接类型"):
            parse_newapi_connection({"_type": "other", "key": "x", "url": "https://a.test"})
        with self.assertRaisesRegex(ValueError, "不能包含"):
            parse_newapi_connection({
                "_type": "newapi_channel_conn",
                "key": "x",
                "url": "https://user:pass@a.test?token=x",
            })

    def test_apply_updates_every_model_except_tts(self):
        window = SimpleNamespace()
        window.model_provider = QComboBox()
        window.model_provider.addItems(["OpenAI", "Ollama"])
        window.model_provider.setCurrentIndex(1)
        window.model_base_url = QLineEdit()
        window.model_name = QComboBox()
        window.model_name.setEditable(True)
        window.model_api_key = QLineEdit()
        window.model_reasoning_effort = self._reasoning_combo()
        window.model_backup_url = QLineEdit()
        window.model_backup_name = QLineEdit()
        window.model_backup_key = QLineEdit()
        window.image_base_url = QLineEdit()
        window.image_model_name = QLineEdit()
        window.image_api_key = QLineEdit()
        window.codex_api_url = QLineEdit()
        window.codex_model_name = QLineEdit()
        window.codex_api_key = QLineEdit()
        window.codex_reasoning_effort = self._reasoning_combo()
        window.voice_api_url = QLineEdit("https://tts.example/v1")
        window.voice_api_model = QLineEdit("tts-model")
        window.voice_api_key = QLineEdit("tts-secret")

        connection = parse_newapi_connection({
            "_type": "newapi_channel_conn",
            "key": "sk-imported",
            "url": "https://u32ai.com",
        })
        with patch("mybot_ui.app_v2.operations.event"):
            MainWindow._apply_newapi_connection(window, connection)

        self.assertEqual(0, window.model_provider.currentIndex())
        self.assertEqual("https://u32ai.com", window.model_base_url.text())
        self.assertEqual("gpt-5.6-sol", window.model_name.currentText())
        self.assertEqual("gpt-5.6-sol", window.model_backup_name.text())
        self.assertEqual("gpt-image-2", window.image_model_name.text())
        self.assertEqual("https://u32ai.com/v1", window.codex_api_url.text())
        self.assertEqual("high", window.model_reasoning_effort.currentData())
        self.assertEqual("high", window.codex_reasoning_effort.currentData())
        self.assertEqual("sk-imported", window.codex_api_key.text())
        self.assertEqual("https://tts.example/v1", window.voice_api_url.text())
        self.assertEqual("tts-model", window.voice_api_model.text())
        self.assertEqual("tts-secret", window.voice_api_key.text())

    def test_chat_request_includes_reasoning_effort(self):
        captured = {}

        def urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response()

        with patch("mybot_ui.chat_engine.urllib.request.urlopen", side_effect=urlopen):
            result = ChatModelClient().generate(
                ModelConfig(
                    provider="openai",
                    base_url="https://u32ai.com",
                    model="gpt-5.6-sol",
                    api_key="sk-secret",
                    reasoning_effort="high",
                ),
                [{"role": "user", "content": "test"}],
            )

        self.assertEqual("ok", result)
        self.assertEqual("https://u32ai.com/v1/chat/completions", captured["url"])
        self.assertEqual("high", captured["payload"]["reasoning_effort"])
        self.assertNotIn("temperature", captured["payload"])

    @staticmethod
    def _reasoning_combo():
        combo = QComboBox()
        for value in ("minimal", "low", "medium", "high"):
            combo.addItem(value, value)
        return combo


if __name__ == "__main__":
    unittest.main()
