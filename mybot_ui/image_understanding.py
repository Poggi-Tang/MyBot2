from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .operation_log import operations


IMAGE_META_PATTERN = re.compile(
    r"<MYBOT_IMAGE_META>\s*(.*?)\s*</MYBOT_IMAGE_META>",
    re.IGNORECASE | re.DOTALL,
)
VISUAL_KINDS = frozenset({"screenshot", "image", "sticker"})
CACHEABLE_VISUAL_KINDS = frozenset({"image", "sticker"})


@dataclass(frozen=True)
class ImageUnderstanding:
    kind: str
    description: str
    sha256: str = ""
    perceptual_hash: str = ""
    source_conversation: str = ""
    created_at: str = ""
    last_used_at: str = ""
    hits: int = 0


def extract_image_understanding(text: str) -> tuple[str, ImageUnderstanding | None]:
    matches = list(IMAGE_META_PATTERN.finditer(str(text)))
    cleaned = IMAGE_META_PATTERN.sub("", str(text)).strip()
    if not matches:
        return cleaned, None
    try:
        payload = json.loads(matches[-1].group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return cleaned, None
    if not isinstance(payload, dict):
        return cleaned, None
    kind = _normalize_kind(payload.get("kind", ""))
    description = re.sub(r"\s+", " ", str(payload.get("description", ""))).strip()[:1000]
    if kind not in VISUAL_KINDS or not description:
        return cleaned, None
    return cleaned, ImageUnderstanding(kind=kind, description=description)


class ImageUnderstandingCache:
    def __init__(self, path: str | Path, *, perceptual_threshold: int = 4) -> None:
        self.path = Path(path)
        self.perceptual_threshold = max(0, min(64, int(perceptual_threshold)))
        self._lock = threading.RLock()
        self._items: dict[str, ImageUnderstanding] = {}
        self._load()

    def lookup(self, encoded: str) -> ImageUnderstanding | None:
        span = operations.start("vision_cache", "lookup", details={"has_image": bool(encoded)})
        try:
            sha256, perceptual_hash = image_hashes(encoded)
            match_type = ""
            matched: ImageUnderstanding | None = None
            matched_key = ""
            with self._lock:
                matched = self._items.get(sha256)
                if matched is not None:
                    matched_key = sha256
                    match_type = "exact"
                elif perceptual_hash:
                    candidates: list[tuple[int, str, ImageUnderstanding]] = []
                    for key, item in self._items.items():
                        if not item.perceptual_hash:
                            continue
                        distance = _hamming_distance(perceptual_hash, item.perceptual_hash)
                        if distance <= self.perceptual_threshold:
                            candidates.append((distance, key, item))
                    if candidates:
                        candidates.sort(key=lambda value: (value[0], -value[2].hits))
                        distance, matched_key, matched = candidates[0]
                        match_type = f"perceptual:{distance}"
                if matched is not None:
                    now = datetime.now().astimezone().isoformat(timespec="seconds")
                    matched = ImageUnderstanding(
                        **{
                            **asdict(matched),
                            "last_used_at": now,
                            "hits": matched.hits + 1,
                        }
                    )
                    self._items[matched_key] = matched
                    self._persist()
            operations.finish(span, success=True, result={
                "outcome": f"{match_type}_hit" if matched else "miss",
                "sha256": sha256[:16],
                "kind": matched.kind if matched else "",
            })
            return matched
        except (ValueError, OSError, UnidentifiedImageError) as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            return None

    def remember(
        self,
        encoded: str,
        understanding: ImageUnderstanding,
        *,
        source_conversation: str = "",
    ) -> bool:
        if understanding.kind == "screenshot":
            operations.event("vision_cache", "skipped_screenshot", {
                "conversation": source_conversation,
                "description": understanding.description,
            })
            return False
        if understanding.kind not in CACHEABLE_VISUAL_KINDS or not understanding.description.strip():
            operations.event("vision_cache", "skipped_invalid_classification", {
                "conversation": source_conversation,
                "kind": understanding.kind,
            })
            return False
        span = operations.start("vision_cache", "store", details={
            "conversation": source_conversation,
            "kind": understanding.kind,
        })
        try:
            sha256, perceptual_hash = image_hashes(encoded)
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            with self._lock:
                previous = self._items.get(sha256)
                item = ImageUnderstanding(
                    kind=understanding.kind,
                    description=understanding.description.strip()[:1000],
                    sha256=sha256,
                    perceptual_hash=perceptual_hash,
                    source_conversation=source_conversation,
                    created_at=previous.created_at if previous else now,
                    last_used_at=now,
                    hits=previous.hits if previous else 0,
                )
                self._items[sha256] = item
                self._persist()
            operations.finish(span, success=True, result={
                "sha256": sha256[:16],
                "perceptual_hash": perceptual_hash,
                "kind": item.kind,
            })
            return True
        except (ValueError, OSError, UnidentifiedImageError) as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            return False

    def all(self) -> tuple[ImageUnderstanding, ...]:
        with self._lock:
            return tuple(self._items.values())

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = payload.get("images", []) if isinstance(payload, dict) else []
            for record in records:
                if not isinstance(record, dict):
                    continue
                item = ImageUnderstanding(
                    kind=_normalize_kind(record.get("kind", "")),
                    description=str(record.get("description", "")).strip(),
                    sha256=str(record.get("sha256", "")).strip(),
                    perceptual_hash=str(record.get("perceptual_hash", "")).strip(),
                    source_conversation=str(record.get("source_conversation", "")),
                    created_at=str(record.get("created_at", "")),
                    last_used_at=str(record.get("last_used_at", "")),
                    hits=int(record.get("hits", 0) or 0),
                )
                if item.kind in CACHEABLE_VISUAL_KINDS and item.description and item.sha256:
                    self._items[item.sha256] = item
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        records = [asdict(item) for item in self._items.values()]
        temporary.write_text(
            json.dumps({"version": 1, "images": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def image_hashes(encoded: str) -> tuple[str, str]:
    raw = base64.b64decode(_raw_base64(encoded), validate=False)
    if not raw:
        raise ValueError("image data is empty")
    sha256 = hashlib.sha256(raw).hexdigest()
    with Image.open(io.BytesIO(raw)) as source:
        source.seek(0)
        normalized = ImageOps.exif_transpose(source).convert("RGB")
        width, height = normalized.size
        averages = tuple(
            round(channel / max(1, width * height))
            for channel in (
                sum(normalized.getchannel("R").tobytes()),
                sum(normalized.getchannel("G").tobytes()),
                sum(normalized.getchannel("B").tobytes()),
            )
        )
        image = normalized.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(image.tobytes())
    bits = 0
    for row in range(8):
        for column in range(8):
            bits = (bits << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    aspect_bucket = min(255, round(128 * width / max(1, height)))
    return sha256, f"{bits:016x}:{averages[0]:02x}{averages[1]:02x}{averages[2]:02x}:{aspect_bucket:02x}"


def _normalize_kind(value: object) -> str:
    normalized = str(value).strip().casefold()
    aliases = {
        "截图": "screenshot",
        "截屏": "screenshot",
        "照片": "image",
        "图片": "image",
        "图像": "image",
        "表情": "sticker",
        "表情包": "sticker",
    }
    return aliases.get(normalized, normalized)


def _hamming_distance(first: str, second: str) -> int:
    try:
        first_shape, first_color, first_aspect = first.split(":")
        second_shape, second_color, second_aspect = second.split(":")
        first_channels = tuple(int(first_color[index:index + 2], 16) for index in range(0, 6, 2))
        second_channels = tuple(int(second_color[index:index + 2], 16) for index in range(0, 6, 2))
        if max(abs(left - right) for left, right in zip(first_channels, second_channels)) > 12:
            return 65
        if abs(int(first_aspect, 16) - int(second_aspect, 16)) > 2:
            return 65
        return (int(first_shape, 16) ^ int(second_shape, 16)).bit_count()
    except (AttributeError, ValueError):
        return 65


def _raw_base64(value: str) -> str:
    return value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
