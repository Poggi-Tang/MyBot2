import unittest

from mybot_ui.app_v2 import DEFAULT_WINDOW_LAYOUT, normalize_window_layout


class WindowLayoutTests(unittest.TestCase):
    def test_defaults_match_recorded_window(self):
        self.assertEqual(DEFAULT_WINDOW_LAYOUT, normalize_window_layout({}))

    def test_configured_layout_is_normalized(self):
        layout = normalize_window_layout(
            {"window": {"x": "100", "y": -20, "width": 1200, "height": 800}}
        )

        self.assertEqual({"x": 100, "y": -20, "width": 1200, "height": 800}, layout)

    def test_invalid_and_too_small_values_fall_back_or_clamp(self):
        layout = normalize_window_layout(
            {"window": {"x": "invalid", "width": 1, "height": None}}
        )

        self.assertEqual(DEFAULT_WINDOW_LAYOUT["x"], layout["x"])
        self.assertEqual(1050, layout["width"])
        self.assertEqual(DEFAULT_WINDOW_LAYOUT["height"], layout["height"])


if __name__ == "__main__":
    unittest.main()
