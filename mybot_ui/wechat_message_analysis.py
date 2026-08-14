from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageChops, ImageFilter, ImageOps

from .rapid_ocr import RapidOcrEngine


MESSAGE_AUTOMATION_ID = (
    "chat_message_list.qt_scrollarea_viewport.chat_bubble_item_view"
)
MESSAGE_CLASSES = {
    "mmui::ChatTextItemView",
    "mmui::ChatBubbleItemView",
    "mmui::ChatBubbleReferItemView",
    "mmui::ChatVoiceItemView",
}
TITLE_AUTOMATION_ID = (
    "content_view.top_content_view.title_h_view.left_v_view."
    "left_content_v_view.left_ui_.big_title_line_h_view"
)
TITLE_CLASS_NAME = "mmui::XHBoxView"
GROUP_SUFFIX = re.compile(r"\((\d+)\)$")
QUOTE_PATTERN = re.compile(
    r"(?:^|\n)\s*引用\s+(?P<sender>.+?)\s+的消息\s*[:：]\s*(?P<quoted>.+)$",
    re.DOTALL,
)
MAX_AVATAR_DISTANCE = 5
MIN_OCR_CONFIDENCE = 0.60
MIN_ENROLL_CONFIDENCE = 0.85
MAX_AVATAR_SAMPLES = 5


@dataclass(frozen=True)
class ConversationContext:
    kind: str
    name: str = ""
    member_count: int | None = None
    raw_title: str = ""


@dataclass(frozen=True)
class IdentityResult:
    status: str
    name: str = ""
    confidence: float = 0.0
    avatar_hash: str = ""
    avatar_distance: int | None = None
    reason: str = ""


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float


class NicknameOcr(Protocol):
    def recognize(self, image: Image.Image) -> OcrResult: ...


def parse_conversation_title(value: str) -> ConversationContext:
    title = str(value or "").strip()
    if not title:
        return ConversationContext("unknown")
    match = GROUP_SUFFIX.search(title)
    if match:
        name = title[: match.start()].rstrip()
        if not name:
            return ConversationContext("unknown", raw_title=title)
        return ConversationContext("group", name, int(match.group(1)), title)
    return ConversationContext("private", title, raw_title=title)


def read_conversation_context(automation: Any) -> ConversationContext:
    try:
        title = automation.Control(
            AutomationId=TITLE_AUTOMATION_ID,
            ClassName=TITLE_CLASS_NAME,
        )
        return parse_conversation_title(getattr(title, "Name", ""))
    except LookupError:
        # WeChat briefly destroys the title subtree while switching chats.
        # Treat that transition as not ready so callers can retry safely.
        return ConversationContext("unknown")


def classify_message(metadata: dict[str, Any]) -> dict[str, Any]:
    result = {"type": "unknown", "meaning": "", "raw_name": "", "quote": None}
    if metadata.get("AutomationId") != MESSAGE_AUTOMATION_ID:
        return result
    name = str(metadata.get("Name") or "").strip()
    class_name = str(metadata.get("ClassName") or "")
    result["raw_name"] = name
    first_line = name.splitlines()[0].strip() if name else ""
    if class_name == "mmui::ChatTextItemView":
        quote = QUOTE_PATTERN.search(name)
        if quote:
            quoted = quote.group("quoted").strip()
            quoted_type = "text"
            if quoted.startswith("图片"):
                quoted_type = "image"
            elif quoted.startswith("动画表情"):
                quoted_type = "sticker"
            elif quoted.startswith("文件"):
                quoted_type = "file"
            result.update(
                type=f"quote_{quoted_type}",
                quote={
                    "sender": quote.group("sender").strip(),
                    "content": quoted,
                    "type": quoted_type,
                    "body": name[: quote.start()].strip(),
                },
            )
            return result
        result["type"] = "text"
        return result
    if class_name == "mmui::ChatVoiceItemView":
        result["type"] = "voice"
        return result
    if class_name == "mmui::ChatBubbleItemView" and first_line == "文件":
        result["type"] = "file"
        return result
    if class_name == "mmui::ChatBubbleItemView" and name.startswith("[链接]"):
        result["type"] = "public_account_link"
        return result
    if class_name != "mmui::ChatBubbleReferItemView":
        return result
    if name == "图片":
        result["type"] = "image"
    elif name.startswith("动画表情"):
        result["type"] = "sticker"
        suffix = name[len("动画表情") :].strip()
        if suffix.startswith("[") and suffix.endswith("]"):
            result["meaning"] = suffix[1:-1].strip()
    return result


def normalize_name(value: str) -> str:
    value = "".join(character for character in str(value).strip() if character.isprintable())
    return re.sub(r"\s+", " ", value)


def avatar_dhash(image: Image.Image) -> str:
    rgb = image.convert("RGB").resize((16, 16), Image.Resampling.LANCZOS)
    gray = rgb.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(getattr(gray, "get_flattened_data", gray.getdata)())
    value = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            value = (value << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    rgb_pixels = list(getattr(rgb, "get_flattened_data", rgb.getdata)())
    count = len(rgb_pixels)
    average = tuple(sum(pixel[channel] for pixel in rgb_pixels) // count for channel in range(3))
    return f"{value:016x}{average[0]:02x}{average[1]:02x}{average[2]:02x}"


def hash_distance(left: str, right: str) -> int:
    structure = (int(left[:16], 16) ^ int(right[:16], 16)).bit_count()
    left_rgb = tuple(int(left[index : index + 2], 16) for index in range(16, 22, 2))
    right_rgb = tuple(int(right[index : index + 2], 16) for index in range(16, 22, 2))
    return structure + max(abs(a - b) for a, b in zip(left_rgb, right_rgb)) // 12


class RapidNicknameOcr:
    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()
        self._cache: dict[bytes, OcrResult] = {}

    @staticmethod
    def _prepare(image: Image.Image) -> Image.Image:
        gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
        scale = max(2, min(4, 64 // max(1, gray.height)))
        return gray.resize(
            (max(1, gray.width * scale), max(1, gray.height * scale)),
            Image.Resampling.LANCZOS,
        ).convert("RGB")

    def recognize(self, image: Image.Image) -> OcrResult:
        prepared = self._prepare(image)
        key = prepared.tobytes()
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            result = OcrResult("", 0.0)
            try:
                import numpy as np

                if self._engine is None:
                    self._engine = RapidOcrEngine()
                text, confidence = self._engine.recognize_line(np.asarray(prepared))
                if text:
                    result = OcrResult(normalize_name(text), float(confidence))
            except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                pass
            self._cache[key] = result
            return result


class IdentityStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.people: dict[str, list[str]] = {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            for name, samples in payload.get("people", {}).items():
                valid = [
                    value.lower()
                    for value in samples
                    if isinstance(value, str) and len(value) == 22
                ]
                if normalize_name(name) and valid:
                    self.people[normalize_name(name)] = valid[:MAX_AVATAR_SAMPLES]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.people = {}

    def enroll(self, name: str, value: str) -> None:
        samples = self.people.setdefault(name, [])
        if value in samples:
            return
        samples.append(value)
        del samples[:-MAX_AVATAR_SAMPLES]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"version": 1, "people": self.people}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


class MessageIdentityRecognizer:
    def __init__(self, store_path: Path, ocr: NicknameOcr | None = None) -> None:
        self.store = IdentityStore(store_path)
        self.ocr = ocr or RapidNicknameOcr()

    def identify(
        self,
        row: Image.Image,
        avatar_rect: tuple[int, int, int, int] | None,
        name_rect: tuple[int, int, int, int] | None,
        conversation: ConversationContext,
    ) -> IdentityResult:
        if avatar_rect is None:
            return IdentityResult("unknown", reason="no_avatar")
        fingerprint = avatar_dhash(row.crop(avatar_rect))
        if conversation.kind == "private":
            name, confidence = normalize_name(conversation.name), 1.0
        elif conversation.kind == "group" and name_rect is not None:
            recognized = self.ocr.recognize(row.crop(name_rect))
            name, confidence = normalize_name(recognized.text), recognized.confidence
        else:
            return IdentityResult("unknown", avatar_hash=fingerprint, reason="no_identity_region")
        if not name or confidence < MIN_OCR_CONFIDENCE:
            return IdentityResult("unknown", name, confidence, fingerprint, reason="ocr_low_confidence")
        distances = {
            candidate: min(hash_distance(fingerprint, sample) for sample in samples)
            for candidate, samples in self.store.people.items()
            if samples
        }
        same = distances.get(name)
        if same is not None and same <= MAX_AVATAR_DISTANCE:
            self.store.enroll(name, fingerprint)
            return IdentityResult("matched", name, confidence, fingerprint, same)
        if same is not None:
            return IdentityResult("unknown", name, confidence, fingerprint, same, "avatar_mismatch")
        if any(distance <= MAX_AVATAR_DISTANCE for candidate, distance in distances.items() if candidate != name):
            return IdentityResult("unknown", name, confidence, fingerprint, reason="avatar_name_conflict")
        if confidence < MIN_ENROLL_CONFIDENCE:
            return IdentityResult("unknown", name, confidence, fingerprint, reason="enrollment_requires_high_confidence")
        self.store.enroll(name, fingerprint)
        return IdentityResult("enrolled", name, confidence, fingerprint, 0)


def _edge_median(image: Image.Image) -> tuple[int, int, int]:
    values = []
    for x in range(0, image.width, max(1, image.width // 60)):
        values.extend((image.getpixel((x, 0)), image.getpixel((x, image.height - 1))))
    for y in range(0, image.height, max(1, image.height // 30)):
        values.extend((image.getpixel((0, y)), image.getpixel((image.width - 1, y))))
    channels = [sorted(color[index] for color in values) for index in range(3)]
    return tuple(channel[len(values) // 2] for channel in channels)


def _difference_mask(image: Image.Image, background: tuple[int, int, int], threshold: int) -> Image.Image:
    difference = ImageChops.difference(image.convert("RGB"), Image.new("RGB", image.size, background))
    red, green, blue = difference.split()
    return ImageChops.lighter(ImageChops.lighter(red, green), blue).point(
        lambda value: 255 if value >= threshold else 0
    )


def _component_bounds(mask: Image.Image) -> list[tuple[int, int, int, int]]:
    width, height = mask.size
    pixels, visited, components = mask.load(), set(), []
    for y in range(height):
        for x in range(width):
            if not pixels[x, y] or (x, y) in visited:
                continue
            stack, count = [(x, y)], 0
            visited.add((x, y))
            left = right = x
            top = bottom = y
            while stack:
                current_x, current_y = stack.pop()
                count += 1
                left, right = min(left, current_x), max(right, current_x)
                top, bottom = min(top, current_y), max(bottom, current_y)
                for offset_y in (-1, 0, 1):
                    for offset_x in (-1, 0, 1):
                        point = (current_x + offset_x, current_y + offset_y)
                        if (
                            point not in visited
                            and 0 <= point[0] < width
                            and 0 <= point[1] < height
                            and pixels[point[0], point[1]]
                        ):
                            visited.add(point)
                            stack.append(point)
            components.append((count, (left, top, right + 1, bottom + 1)))
    return [bounds for _count, bounds in sorted(components, reverse=True)]


def _left_avatar(image: Image.Image, background: tuple[int, int, int]):
    zone = image.crop((0, 0, min(64, image.width), min(64, image.height)))
    for left, top, right, bottom in _component_bounds(_difference_mask(zone, background, 20)):
        width, height = right - left, bottom - top
        if 20 <= width <= 54 and 20 <= height <= 54 and 0.65 <= width / height <= 1.55 and right < zone.width:
            return max(0, left - 2), max(0, top - 2), min(zone.width, right + 2), min(zone.height, bottom + 2)
    return None


def _detect_message_row(image: Image.Image, kind: str) -> dict[str, Any]:
    if image.width < 100 or image.height < 20:
        return {"direction": "unknown", "boxes": []}
    background = _edge_median(image)
    left_avatar = _left_avatar(image, background)
    mirrored = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    mirrored_right = _left_avatar(mirrored, background)
    right_avatar = (
        (image.width - mirrored_right[2], mirrored_right[1], image.width - mirrored_right[0], mirrored_right[3])
        if mirrored_right else None
    )
    direction = "incoming" if left_avatar and not right_avatar else "outgoing" if right_avatar and not left_avatar else "unknown"
    avatar = left_avatar if direction == "incoming" else right_avatar
    if avatar is None:
        return {"direction": direction, "boxes": []}
    nickname = None
    if direction == "incoming" and kind == "group":
        left, top = avatar[2] + 1, avatar[1]
        right, bottom = min(image.width, left + 180), min(image.height, avatar[1] + 22)
        if right - left >= 8 and bottom > top and _difference_mask(image.crop((left, top, right, bottom)), background, 20).getbbox():
            nickname = (left, top, right, bottom)
    bubble_left = avatar[2] + 1 if direction == "incoming" else 0
    bubble_right = image.width if direction == "incoming" else avatar[0] - 1
    bubble_top = avatar[1] + (23 if nickname else 2)
    bubble = None
    if bubble_right - bubble_left >= 8 and image.height - bubble_top >= 8:
        mask = _difference_mask(image.crop((bubble_left, bubble_top, bubble_right, image.height)), background, 5)
        bounds = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3)).getbbox()
        if bounds and bounds[2] - bounds[0] >= 8 and bounds[3] - bounds[1] >= 8:
            bubble = (
                bubble_left + bounds[0], bubble_top + bounds[1],
                bubble_left + bounds[2], bubble_top + bounds[3],
            )
    boxes = [{"kind": "avatar", "rect": avatar}]
    if nickname:
        boxes.append({"kind": "name", "rect": nickname})
    if bubble:
        boxes.append({"kind": "bubble", "rect": bubble})
    return {"direction": direction, "boxes": boxes}


class MessageAnalyzer:
    def __init__(self, identity_store_path: Path) -> None:
        self.identity = MessageIdentityRecognizer(identity_store_path)

    def analyze(
        self,
        image: Image.Image,
        metadata: dict[str, Any],
        conversation: ConversationContext,
        screen_origin: tuple[int, int] = (0, 0),
    ) -> dict[str, Any]:
        source = image.convert("RGB")
        detection = _detect_message_row(source, conversation.kind)
        local = {box["kind"]: box["rect"] for box in detection["boxes"]}
        direction = detection["direction"]
        if direction == "outgoing":
            sender = IdentityResult("self", "我", 1.0)
        elif direction == "incoming":
            sender = self.identity.identify(source, local.get("avatar"), local.get("name"), conversation)
        else:
            sender = IdentityResult("unknown", reason="direction_unknown")
        message = classify_message(metadata)
        quote = message.get("quote") or {}
        content = quote.get("body") if quote else message["raw_name"]
        if message["type"] == "image":
            content = "[图片]"
        elif message["type"] == "sticker":
            content = f"[动画表情{':' + message['meaning'] if message['meaning'] else ''}]"
        elif message["type"] == "voice":
            content = message["raw_name"] or "[语音]"
        elif message["type"] == "file" and not content:
            content = "[文件]"
        screen_regions = {
            key: (
                {
                    "left": rect[0] + screen_origin[0], "top": rect[1] + screen_origin[1],
                    "right": rect[2] + screen_origin[0], "bottom": rect[3] + screen_origin[1],
                }
                if (rect := local.get(key)) else None
            )
            for key in ("avatar", "name", "bubble")
        }
        return {
            "sender": asdict(sender),
            "direction": direction,
            "content": str(content or "").strip(),
            "message": message,
            "screen_regions": screen_regions,
            "conversation": asdict(conversation),
        }


def control_metadata(control: Any) -> dict[str, str]:
    control_type = getattr(control, "ControlTypeName", "")
    if callable(control_type):
        control_type = control_type()
    return {
        "AutomationId": str(getattr(control, "AutomationId", "") or ""),
        "Name": str(getattr(control, "Name", "") or ""),
        "ClassName": str(getattr(control, "ClassName", "") or ""),
        "ControlType": str(control_type or ""),
    }


def message_signature(analysis: dict[str, Any]) -> str:
    message = analysis.get("message", {})
    sender = analysis.get("sender", {})
    return "|".join(
        (
            str(analysis.get("direction", "")),
            str(sender.get("name", "")),
            str(message.get("type", "")),
            str(analysis.get("content", "")),
            str((message.get("quote") or {}).get("sender", "")),
            str((message.get("quote") or {}).get("content", "")),
        )
    )
