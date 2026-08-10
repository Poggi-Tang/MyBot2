import unittest
from unittest.mock import MagicMock

from mybot_ui.api import command_timeout
from mybot_ui.app_v2 import MainWindow
from mybot_ui.catalog import TOOL_MAP, build_options


class StickerCatalogToolTests(unittest.TestCase):
    def test_scan_tool_has_no_payload(self):
        self.assertIn("ScanAllStickers", TOOL_MAP)
        self.assertEqual("", build_options("ScanAllStickers", {}))

    def test_send_sticker_payload_preserves_category_and_identifier(self):
        payload = build_options(
            "SendSticker",
            {"who": "测试联系人甲", "category": "自定义表情", "sticker": "A1B2C3"},
        )
        self.assertEqual("测试联系人甲", payload["who"])
        self.assertEqual("自定义表情", payload["category"])
        self.assertEqual("A1B2C3", payload["sticker"])

    def test_scan_button_runs_only_sticker_scan(self):
        window = MagicMock()

        MainWindow._scan_all_stickers(window)

        window._start_tests.assert_called_once_with([("ScanAllStickers", {})])

    def test_sticker_scan_has_extended_timeout(self):
        self.assertEqual(180, command_timeout("ScanAllStickers"))
        self.assertEqual(30, command_timeout("SendSticker"))


if __name__ == "__main__":
    unittest.main()
