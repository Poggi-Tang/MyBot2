import unittest

from mybot_ui.docking import (
    DockRect,
    dock_context_is_foreground,
    toolbar_rect,
    tool_rect,
)


class DockingTests(unittest.TestCase):
    def setUp(self):
        self.work = DockRect(0, 0, 1920, 1040)

    def test_toolbar_uses_bottom_center_when_space_is_available(self):
        wechat = DockRect(300, 100, 1000, 800)
        result = toolbar_rect(wechat, self.work, 530, 48)
        self.assertEqual(535, result.x)
        self.assertEqual(wechat.bottom, result.y)

    def test_toolbar_moves_to_top_when_bottom_space_is_insufficient(self):
        wechat = DockRect(300, 120, 1000, 900)
        result = toolbar_rect(wechat, self.work, 530, 48)
        self.assertEqual(wechat.y, result.bottom)

    def test_tool_prefers_right_side(self):
        wechat = DockRect(100, 100, 900, 800)
        result, side = tool_rect(wechat, self.work, 700, 800)
        self.assertEqual("right", side)
        self.assertEqual(wechat.right, result.x)
        self.assertEqual(wechat.y, result.y)
        self.assertEqual(wechat.height, result.height)

    def test_tool_falls_back_left_when_right_side_is_too_narrow(self):
        wechat = DockRect(800, 80, 1000, 850)
        result, side = tool_rect(wechat, self.work, 700, 850)
        self.assertEqual("left", side)
        self.assertEqual(wechat.x, result.right)

    def test_tool_keeps_exact_wechat_height_below_old_minimum(self):
        wechat = DockRect(100, 240, 900, 480)
        result, _side = tool_rect(
            wechat,
            self.work,
            preferred_width=700,
            preferred_height=wechat.height,
        )
        self.assertEqual(wechat.y, result.y)
        self.assertEqual(wechat.height, result.height)

    def test_dock_is_visible_while_wechat_is_foreground(self):
        self.assertTrue(
            dock_context_is_foreground(
                100,
                200,
                foreground_handle=100,
                foreground_process_id=300,
            )
        )

    def test_dock_stays_visible_while_its_own_window_is_foreground(self):
        self.assertTrue(
            dock_context_is_foreground(
                100,
                200,
                foreground_handle=101,
                foreground_process_id=200,
            )
        )

    def test_dock_stays_visible_for_another_wechat_window(self):
        from unittest.mock import patch

        with patch("mybot_ui.docking._window_process_id", return_value=300):
            self.assertTrue(
                dock_context_is_foreground(
                    100,
                    200,
                    foreground_handle=101,
                    foreground_process_id=300,
                )
            )

    def test_dock_hides_for_an_unrelated_foreground_window(self):
        self.assertFalse(
            dock_context_is_foreground(
                100,
                200,
                foreground_handle=101,
                foreground_process_id=300,
            )
        )


if __name__ == "__main__":
    unittest.main()
