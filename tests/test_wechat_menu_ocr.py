import unittest

from mybot_ui.wechat_menu_ocr import find_text_item, inset_rect, ocr_rect, row_rects


class WeChatMenuOcrTests(unittest.TestCase):
    def test_debugtool_menu_geometry_is_preserved(self):
        inner = inset_rect((100, 200, 500, 500))
        capture = ocr_rect(inner)
        rows = row_rects(capture, [(124, 224, 476, 270), (124, 270, 476, 316)])

        self.assertEqual((124, 224, 476, 476), inner)
        self.assertEqual((152, 224, 476, 476), capture)
        self.assertEqual([(0, 0, 324, 46), (0, 46, 324, 92)], rows)

    def test_quote_option_requires_ocr_text_match(self):
        items = [
            {"text": "复制", "rect": (1, 1, 20, 20)},
            {"text": "引用消息", "rect": (1, 30, 40, 50)},
        ]
        self.assertEqual(items[1], find_text_item(items, "引用"))
        self.assertIsNone(find_text_item(items, "删除"))


if __name__ == "__main__":
    unittest.main()
