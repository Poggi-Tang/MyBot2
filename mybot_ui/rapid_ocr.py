from __future__ import annotations

from typing import Any


class RapidOcrEngine:
    """Small adapter around RapidOCR 3.x's result-object API."""

    def __init__(self) -> None:
        from rapidocr import RapidOCR

        self._engine = RapidOCR()

    def recognize_lines(self, images: list[Any]) -> list[tuple[str, float]]:
        values: list[tuple[str, float]] = []
        for image in images:
            result = self._engine(
                image,
                use_det=False,
                use_cls=False,
                use_rec=True,
            )
            texts = self._values(getattr(result, "txts", None))
            scores = self._values(getattr(result, "scores", None))
            values.append(
                (
                    str(texts[0] or "").strip() if texts else "",
                    float(scores[0] or 0.0) if scores else 0.0,
                )
            )
        return values

    def recognize_line(self, image: Any) -> tuple[str, float]:
        values = self.recognize_lines([image])
        return values[0] if values else ("", 0.0)

    def recognize_full(self, image: Any) -> list[tuple[Any, str, float]]:
        result = self._engine(
            image,
            use_det=True,
            use_cls=False,
            use_rec=True,
        )
        boxes = self._values(getattr(result, "boxes", None))
        texts = self._values(getattr(result, "txts", None))
        scores = self._values(getattr(result, "scores", None))
        return [
            (box, str(text or "").strip(), float(score or 0.0))
            for box, text, score in zip(boxes, texts, scores)
        ]

    @staticmethod
    def _values(value: Any) -> tuple[Any, ...]:
        return () if value is None else tuple(value)
