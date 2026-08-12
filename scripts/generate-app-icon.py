from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


SIZES = (16, 24, 32, 48, 64, 128, 256)


def generate(svg_path: Path, ico_path: Path) -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise ValueError(f"invalid SVG: {svg_path}")
    rendered: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="mybot-icon-") as directory:
        temporary_root = Path(directory)
        for size in SIZES:
            image = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            renderer.render(painter, QRectF(0, 0, size, size))
            painter.end()
            png_path = temporary_root / f"{size}.png"
            if not image.save(str(png_path), "PNG"):
                raise OSError(f"could not render icon size {size}")
            with Image.open(png_path) as frame:
                rendered.append(frame.convert("RGBA"))
        ico_path.parent.mkdir(parents=True, exist_ok=True)
        rendered[-1].save(ico_path, format="ICO", append_images=rendered[:-1], sizes=[(s, s) for s in SIZES])
    del app


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: generate-app-icon.py input.svg output.ico")
    generate(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
