import base64
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from mybot_ui.image_understanding import (
    ImageUnderstanding,
    ImageUnderstandingCache,
    extract_image_understanding,
)


def encoded_image(*, changed_pixel: bool = False) -> str:
    image = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 55, 55), fill="black")
    if changed_pixel:
        image.putpixel((63, 63), (240, 240, 240))
    stream = BytesIO()
    image.save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode("ascii")


class ImageUnderstandingTests(unittest.TestCase):
    def test_extracts_and_removes_internal_metadata(self):
        reply, item = extract_image_understanding(
            '这个表情是在表示无语'
            '<MYBOT_IMAGE_META>{"kind":"sticker","description":"无语地看着对方"}</MYBOT_IMAGE_META>'
        )
        self.assertEqual("这个表情是在表示无语", reply)
        self.assertIsNotNone(item)
        self.assertEqual("sticker", item.kind)
        self.assertEqual("无语地看着对方", item.description)

    def test_invalid_internal_metadata_is_still_removed(self):
        reply, item = extract_image_understanding(
            "正常回复<MYBOT_IMAGE_META>not-json</MYBOT_IMAGE_META>"
        )
        self.assertEqual("正常回复", reply)
        self.assertIsNone(item)

    def test_screenshot_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            cache = ImageUnderstandingCache(path)
            stored = cache.remember(
                encoded_image(),
                ImageUnderstanding("screenshot", "微信聊天截图"),
            )
            self.assertFalse(stored)
            self.assertFalse(path.exists())
            self.assertEqual((), cache.all())

    def test_exact_image_match_persists_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            encoded = encoded_image()
            cache = ImageUnderstandingCache(path)
            self.assertTrue(cache.remember(
                encoded,
                ImageUnderstanding("image", "黑色方块图片"),
                source_conversation="测试会话",
            ))
            match = ImageUnderstandingCache(path).lookup(encoded)
            self.assertIsNotNone(match)
            self.assertEqual("image", match.kind)
            self.assertEqual("黑色方块图片", match.description)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["images"][0]["hits"])

    def test_perceptually_identical_encoding_reuses_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ImageUnderstandingCache(Path(directory) / "cache.json")
            cache.remember(encoded_image(), ImageUnderstanding("sticker", "沉默"))
            match = cache.lookup(encoded_image(changed_pixel=True))
            self.assertIsNotNone(match)
            self.assertEqual("沉默", match.description)


if __name__ == "__main__":
    unittest.main()
