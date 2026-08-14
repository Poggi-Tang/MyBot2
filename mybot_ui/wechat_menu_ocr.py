from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

from PIL import Image

from .rapid_ocr import RapidOcrEngine


MENU_NAME = "Weixin"
MENU_CLASS_NAME = "mmui::XMenu"
MENU_ITEM_CLASS_NAME = "mmui::XMenuView"
MENU_INSET = 24
MENU_OCR_LEFT_TRIM = 28
MIN_TEXT_CONFIDENCE = 0.50
BACKGROUND_THRESHOLD = 200
TEXT_CROP_PADDING = 3


def inset_rect(rect: tuple[int, int, int, int], inset: int = MENU_INSET):
    left, top, right, bottom = map(int, rect)
    result = left + inset, top + inset, right - inset, bottom - inset
    return result if result[2] > result[0] and result[3] > result[1] else None


def ocr_rect(rect: tuple[int, int, int, int], trim: int = MENU_OCR_LEFT_TRIM):
    left, top, right, bottom = map(int, rect)
    result = left + trim, top, right, bottom
    return result if result[2] > result[0] and result[3] > result[1] else None


def row_rects(
    source_rect: tuple[int, int, int, int],
    item_rects: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    left, top, right, bottom = source_rect
    rows = []
    for _item_left, item_top, _item_right, item_bottom in item_rects:
        row_top, row_bottom = max(top, item_top), min(bottom, item_bottom)
        if right - left >= 8 and row_bottom - row_top >= 8:
            rows.append((0, row_top - top, right - left, row_bottom - top))
    return sorted(set(rows), key=lambda value: value[1])


class MenuOcrAnalyzer:
    """DebugTool's fast per-row OCR path with a full-image fallback."""

    def __init__(self, min_confidence: float = MIN_TEXT_CONFIDENCE) -> None:
        self.min_confidence = float(min_confidence)
        self._fast_engine = None
        self._full_engine = None
        self._lock = threading.Lock()
        self._cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    @staticmethod
    def _cache_key(source: Image.Image, rows):
        dark = source.convert("L").point(
            lambda value: 255 if value < BACKGROUND_THRESHOLD else 0
        )
        return (
            source.size,
            tuple(rows),
            hashlib.blake2b(dark.tobytes(), digest_size=12).digest(),
        )

    def _engine(self, *, full: bool):
        attribute = "_full_engine" if full else "_fast_engine"
        engine = getattr(self, attribute)
        if engine is None:
            engine = RapidOcrEngine()
            setattr(self, attribute, engine)
        return engine

    def _recognize_rows(self, source: Image.Image, rows):
        import numpy as np

        source_array = np.asarray(source)
        crops, rectangles = [], []
        for left, top, right, bottom in rows:
            row = source_array[top:bottom, left:right]
            gray = np.asarray(Image.fromarray(row).convert("L"))
            dark_y, dark_x = np.where(gray < BACKGROUND_THRESHOLD)
            if not len(dark_x):
                return []
            crop_left = max(0, int(dark_x.min()) - TEXT_CROP_PADDING)
            crop_top = max(0, int(dark_y.min()) - TEXT_CROP_PADDING)
            crop_right = min(row.shape[1], int(dark_x.max()) + TEXT_CROP_PADDING + 1)
            crop_bottom = min(row.shape[0], int(dark_y.max()) + TEXT_CROP_PADDING + 1)
            crops.append(row[crop_top:crop_bottom, crop_left:crop_right])
            rectangles.append(
                (left + crop_left, top + crop_top, left + crop_right, top + crop_bottom)
            )
        recognized = self._engine(full=False).recognize_lines(crops)
        return [
            {"text": str(text or "").strip(), "confidence": float(confidence), "rect": rect}
            for rect, (text, confidence) in zip(rectangles, recognized)
            if str(text or "").strip() and float(confidence) >= self.min_confidence
        ]

    def _full_ocr(self, source: Image.Image):
        import numpy as np

        raw = self._engine(full=True).recognize_full(np.asarray(source))
        items = []
        for result in raw or []:
            if not isinstance(result, (tuple, list)) or len(result) < 3:
                continue
            polygon, text, confidence = result[:3]
            text, confidence = str(text or "").strip(), float(confidence)
            if not text or confidence < self.min_confidence:
                continue
            points = [(float(point[0]), float(point[1])) for point in polygon]
            items.append(
                {
                    "text": text,
                    "confidence": confidence,
                    "rect": (
                        int(min(point[0] for point in points)),
                        int(min(point[1] for point in points)),
                        int(max(point[0] for point in points) + 1),
                        int(max(point[1] for point in points) + 1),
                    ),
                }
            )
        return sorted(items, key=lambda item: (item["rect"][1], item["rect"][0]))

    def analyze(self, image: Image.Image, origin=(0, 0), rows=()) -> dict[str, Any]:
        source = image.convert("RGB")
        valid_rows = [
            tuple(map(int, row))
            for row in rows
            if len(row) == 4 and row[2] - row[0] >= 8 and row[3] - row[1] >= 8
        ]
        key = self._cache_key(source, valid_rows)
        started = time.perf_counter()
        try:
            with self._lock:
                cached = self._cache.get(key)
                cache_hit = cached is not None
                if cached is None:
                    items = self._recognize_rows(source, valid_rows) if valid_rows else []
                    path = "fast_rows"
                    if not valid_rows or len(items) != len(valid_rows):
                        items, path = self._full_ocr(source), "fallback"
                    cached = {"items": items, "path": path}
                    self._cache[key] = cached
            origin_x, origin_y = map(int, origin)
            return {
                "items": [
                    {
                        **item,
                        "rect": (
                            item["rect"][0] + origin_x,
                            item["rect"][1] + origin_y,
                            item["rect"][2] + origin_x,
                            item["rect"][3] + origin_y,
                        ),
                    }
                    for item in cached["items"]
                ],
                "path": "cache" if cache_hit else cached["path"],
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "error": "",
            }
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            return {
                "items": [],
                "path": "error",
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "error": str(exc),
            }


def find_text_item(items: list[dict[str, Any]], expected: str) -> dict[str, Any] | None:
    expected = str(expected or "").strip()
    return next(
        (
            item
            for item in items
            if str(item.get("text") or "").strip() == expected
            or expected in str(item.get("text") or "").strip()
        ),
        None,
    )
