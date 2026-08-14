import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from mybot_ui.rapid_ocr import RapidOcrEngine


class RapidOcrEngineTests(unittest.TestCase):
    @patch("rapidocr.RapidOCR")
    def test_adapts_rapidocr_result_objects(self, rapid_ocr):
        engine = Mock()
        rapid_ocr.return_value = engine
        engine.side_effect = (
            SimpleNamespace(txts=("引用",), scores=(0.98,)),
            SimpleNamespace(txts=("复制",), scores=(0.95,)),
            SimpleNamespace(
                boxes=np.asarray((((1, 2), (3, 2), (3, 4), (1, 4)),)),
                txts=np.asarray(("引用",)),
                scores=np.asarray((0.98,)),
            ),
        )
        adapter = RapidOcrEngine()

        self.assertEqual(
            [("引用", 0.98), ("复制", 0.95)],
            adapter.recognize_lines([object(), object()]),
        )
        self.assertEqual("引用", adapter.recognize_full(object())[0][1])
        self.assertEqual(3, engine.call_count)
        self.assertEqual(False, engine.call_args_list[0].kwargs["use_det"])
        self.assertEqual(False, engine.call_args_list[1].kwargs["use_det"])
        self.assertEqual(True, engine.call_args_list[2].kwargs["use_det"])

    def test_real_engine_accepts_multiple_line_images(self):
        adapter = RapidOcrEngine()
        images = [
            np.full((32, 128, 3), 255, dtype=np.uint8),
            np.full((32, 128, 3), 255, dtype=np.uint8),
        ]

        result = adapter.recognize_lines(images)

        self.assertEqual(2, len(result))
        self.assertTrue(all(isinstance(text, str) for text, _score in result))


if __name__ == "__main__":
    unittest.main()
