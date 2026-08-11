import json
import unittest

from mybot_ui.catalog import build_options


class ListenerOptionsTests(unittest.TestCase):
    def test_read_conversation_monitoring_can_be_enabled(self) -> None:
        payload = build_options(
            "AddMessageListener",
            {
                "targets": ["芝士圆子"],
                "open": False,
                "monitor_read_conversations": True,
                "file_save_directory": "F:/MyBot/data/attachments",
            },
        )

        options = json.loads(payload["options"])
        self.assertTrue(options["monitor_read_conversations"])
        self.assertTrue(options["fetch_image"])
        self.assertTrue(options["fetch_file"])
        self.assertEqual("F:/MyBot/data/attachments", options["file_save_directory"])

    def test_read_conversation_monitoring_is_off_by_default(self) -> None:
        payload = build_options("AddMessageListener", {"targets": ["芝士圆子"]})

        options = json.loads(payload["options"])
        self.assertFalse(options["monitor_read_conversations"])


if __name__ == "__main__":
    unittest.main()
