from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .operation_log import operations


MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024
_SIZE_LINE = re.compile(r"^\s*[\d.]+\s*(?:B|KB|MB|GB|字节)\s*$", re.IGNORECASE)
_IMAGE_EDIT_EXCLUSIONS = re.compile(
    r"代码|脚本|程序|配置|数据库|仓库|项目|文档|表格|PDF|Word|Excel|PPT|朋友圈",
    re.IGNORECASE,
)
_IMAGE_EDIT_REFERENCE = re.compile(
    r"(?:图片|照片|截图|原图|这张|那张|上面(?:那张)?|刚才(?:那张)?|招牌|水印|背景)"
    r".{0,20}(?:改|修改|替换|换成|变成|去掉|删除|调整|编辑|修复|润色|抠图)",
    re.IGNORECASE,
)
_IMAGE_EDIT_REPLACEMENT = re.compile(
    r"(?:把|吧).{1,40}?(?:修改|改|替换|换|变)成.{1,40}?(?:发给我|给我|$)",
    re.IGNORECASE,
)
_IMAGE_EDIT_FOLLOW_UP = re.compile(
    r"(?:上面|刚才|之前|前面|那张|这张).{0,24}(?:发过|发了|发的|不是发|图片|照片|原图)"
    r"|(?:再试|重试|重新试|继续改|接着改|就用上面|就用刚才|收到图了)",
    re.IGNORECASE,
)


def is_image_edit_request(content: str) -> bool:
    """Recognize an edit instruction that can use the latest conversation image."""
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    if not text or _IMAGE_EDIT_EXCLUSIONS.search(text):
        return False
    return bool(
        re.search(r"修图|改图|P图", text, re.IGNORECASE)
        or _IMAGE_EDIT_REFERENCE.search(text)
        or _IMAGE_EDIT_REPLACEMENT.search(text)
    )


def is_image_edit_followup(content: str) -> bool:
    """Recognize a follow-up that should resume a pending image edit."""
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    return bool(text and _IMAGE_EDIT_FOLLOW_UP.search(text))


@dataclass(frozen=True)
class IncomingAttachment:
    name: str
    path: str = ""
    kind: str = "file"
    size: int = 0
    sha256: str = ""
    mime_type: str = ""
    received_at: str = ""
    conversation: str = ""


def attachment_name_from_message(content: str) -> str:
    lines = [line.strip() for line in re.split(r"[\r\n]+", content) if line.strip()]
    for line in lines:
        value = re.sub(r"^(?:\[?文件\]?|文件[:：])\s*", "", line).strip()
        value = re.sub(
            r"\s+[\d.]+\s*(?:B|KB|MB|GB|字节)\s*$",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip()
        if not value or value == "文件" or _SIZE_LINE.fullmatch(value):
            continue
        name = Path(value.replace("\\", "/")).name.strip()
        if name and name not in {".", ".."}:
            return name
    match = re.search(r"(?:文件[:：]?\s*)?([^/\\\r\n:*?\"<>|]+\.[A-Za-z0-9]{1,16})", content)
    return Path(match.group(1)).name.strip() if match else ""


def attachment_type_label(attachment: IncomingAttachment) -> str:
    suffix = Path(attachment.name).suffix.lower()
    labels = {
        ".zip": "ZIP 压缩包",
        ".rar": "RAR 压缩包",
        ".7z": "7Z 压缩包",
        ".pdf": "PDF 文档",
        ".doc": "Word 文档",
        ".docx": "Word 文档",
        ".xls": "Excel 表格",
        ".xlsx": "Excel 表格",
        ".ppt": "PowerPoint 演示文稿",
        ".pptx": "PowerPoint 演示文稿",
        ".png": "PNG 图片",
        ".jpg": "JPEG 图片",
        ".jpeg": "JPEG 图片",
        ".gif": "GIF 图片",
        ".webp": "WebP 图片",
        ".txt": "文本文件",
    }
    return labels.get(suffix, attachment.mime_type or _mime_type(attachment.name))


class WeChatAttachmentResolver:
    def __init__(self, roots: Iterable[str | Path] = (), *, max_bytes: int = MAX_ATTACHMENT_BYTES) -> None:
        self.configured_roots = tuple(Path(root) for root in roots if str(root).strip())
        self.max_bytes = max(1, int(max_bytes))

    def resolve(self, attachment: IncomingAttachment, *, received_at: str = "") -> IncomingAttachment:
        span = operations.start("attachment", "resolve_incoming_file", details={
            "name": attachment.name,
            "kind": attachment.kind,
            "has_sdk_path": bool(attachment.path),
        })
        try:
            candidates: list[Path] = []
            if attachment.path:
                candidates.append(Path(attachment.path))
            candidates.extend(self._find_by_name(attachment.name, received_at=received_at))
            for candidate in candidates:
                try:
                    resolved = candidate.resolve(strict=True)
                    size = resolved.stat().st_size
                except OSError:
                    continue
                if not resolved.is_file() or size <= 0 or size > self.max_bytes:
                    continue
                digest = _file_sha256(resolved)
                result = replace(
                    attachment,
                    name=attachment.name or resolved.name,
                    path=str(resolved),
                    size=size,
                    sha256=digest,
                    mime_type=attachment.mime_type or _mime_type(resolved.name),
                    received_at=attachment.received_at or received_at,
                )
                operations.finish(span, success=True, result={
                    "name": result.name,
                    "size": result.size,
                    "sha256": result.sha256[:16],
                })
                return result
            raise FileNotFoundError(f"未找到已下载的微信文件：{attachment.name or '[未知文件名]'}")
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def discover_near(self, *, received_at: str = "", max_delta: timedelta = timedelta(minutes=5)) -> IncomingAttachment | None:
        target = _parse_received_at(received_at)
        candidates: list[tuple[float, float, Path]] = []
        for root in self._roots():
            if not root.is_dir():
                continue
            try:
                paths = root.rglob("*")
                for path in paths:
                    try:
                        if not path.is_file():
                            continue
                        stat = path.stat()
                        if stat.st_size <= 0 or stat.st_size > self.max_bytes:
                            continue
                        modified = datetime.fromtimestamp(stat.st_mtime)
                        delta = abs((modified - target).total_seconds())
                        if delta <= max_delta.total_seconds():
                            candidates.append((delta, -stat.st_mtime, path))
                    except OSError:
                        continue
            except OSError:
                continue
        if not candidates:
            return None
        path = min(candidates, key=lambda item: (item[0], item[1]))[2]
        return self.resolve(
            IncomingAttachment(path.name, str(path), "file", received_at=received_at),
            received_at=received_at,
        )

    def _find_by_name(self, name: str, *, received_at: str) -> list[Path]:
        safe_name = Path(name).name.strip()
        if not safe_name:
            return []
        cutoff = _parse_received_at(received_at) - timedelta(days=2)
        candidates: list[Path] = []
        for root in self._roots():
            if not root.is_dir():
                continue
            try:
                matches = root.rglob(safe_name)
                for path in matches:
                    try:
                        if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime) >= cutoff:
                            candidates.append(path)
                    except OSError:
                        continue
            except OSError:
                continue
        candidates.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
        return candidates

    def _roots(self) -> tuple[Path, ...]:
        roots = list(self.configured_roots)
        home = Path.home()
        xwechat = home / "xwechat_files"
        if xwechat.is_dir():
            roots.extend(path / "msg" / "file" for path in xwechat.iterdir() if path.is_dir())
        legacy = home / "Documents" / "WeChat Files"
        if legacy.is_dir():
            roots.extend(path / "FileStorage" / "File" for path in legacy.iterdir() if path.is_dir())
        unique: dict[str, Path] = {}
        for root in roots:
            try:
                unique[str(root.resolve())] = root
            except OSError:
                unique[str(root)] = root
        return tuple(unique.values())


class ConversationAttachmentStore:
    def __init__(
        self,
        root: str | Path,
        resolver: WeChatAttachmentResolver | None = None,
        *,
        max_age: timedelta = timedelta(hours=24),
        max_per_conversation: int = 8,
    ) -> None:
        self.root = Path(root)
        self.resolver = resolver or WeChatAttachmentResolver()
        self.max_age = max_age
        self.max_per_conversation = max(1, int(max_per_conversation))
        self._lock = threading.RLock()
        self._items: dict[str, list[tuple[datetime, IncomingAttachment, str]]] = {}
        self._index_path = self.root / "index.json"
        self._load_index()

    def remember(
        self,
        conversation: str,
        attachments: Iterable[IncomingAttachment],
        *,
        received_at: str = "",
        image_base64: str = "",
        message_kind: str = "image",
    ) -> tuple[IncomingAttachment, ...]:
        values = list(attachments)
        if image_base64 and not any(item.kind in {"image", "sticker"} for item in values):
            try:
                values.append(self._materialize_image(conversation, image_base64, message_kind))
            except (ValueError, OSError) as exc:
                operations.event("attachment", "incoming_image_materialize_failed", {
                    "conversation": conversation,
                    "error": f"{type(exc).__name__}: {exc}",
                })
        materialized: list[IncomingAttachment] = []
        for item in values:
            try:
                if item.kind in {"image", "sticker"} and item.path:
                    resolved = self.resolver.resolve(item, received_at=received_at)
                    materialized.append(self._import_file(conversation, resolved, received_at=received_at))
                elif item.kind not in {"image", "sticker"}:
                    resolved = self.resolver.resolve(item, received_at=received_at)
                    materialized.append(self._import_file(conversation, resolved, received_at=received_at))
                else:
                    materialized.append(item)
            except (FileNotFoundError, OSError) as exc:
                operations.event("attachment", "incoming_file_materialize_failed", {
                    "conversation": conversation,
                    "name": item.name,
                    "error": f"{type(exc).__name__}: {exc}",
                })
        values = materialized
        now = datetime.now()
        with self._lock:
            current = self._items.setdefault(conversation, [])
            for item in values:
                key = item.sha256 or item.path or item.name
                if key and any((existing.sha256 or existing.path or existing.name) == key for _, existing, _ in current):
                    continue
                current.append((now, item, received_at))
            self._items[conversation] = current[-self.max_per_conversation :]
            self._persist_index()
        return tuple(values)

    def recent(
        self,
        conversation: str,
        *,
        kinds: set[str] | None = None,
        max_age: timedelta | None = None,
    ) -> tuple[IncomingAttachment, ...]:
        threshold = datetime.now() - (max_age or self.max_age)
        resolved: list[IncomingAttachment] = []
        with self._lock:
            current = [item for item in self._items.get(conversation, []) if item[0] >= threshold]
            self._items[conversation] = current
        for _recorded, item, received_at in current:
            if kinds is not None and item.kind not in kinds:
                continue
            try:
                resolved.append(self.resolver.resolve(item, received_at=received_at))
            except (FileNotFoundError, OSError):
                continue
        return tuple(resolved)

    def for_request(self, conversation: str, request: str, *, received_at: str = "") -> tuple[IncomingAttachment, ...]:
        wants_file = bool(re.search(
            r"文件|附件|压缩包|解压|文档|表格|PDF|Word|Excel|PPT|zip|rar|7z",
            request,
            re.IGNORECASE,
        ))
        wants_image = bool(
            re.search(r"图片|照片|截图|原图|壁纸|修图|改图|P图", request, re.IGNORECASE)
            or is_image_edit_request(request)
        )
        if wants_file:
            files = self.recent(conversation, kinds={"file"}, max_age=timedelta(minutes=15))
            if files:
                return files[-1:]
            discovered = self.resolver.discover_near(received_at=received_at)
            if discovered is not None:
                remembered = self.remember(conversation, (discovered,), received_at=received_at)
                return tuple(item for item in remembered if item.kind == "file")[-1:]
            if not wants_image:
                return ()
        if wants_image:
            images = self.recent(conversation, kinds={"image", "sticker"}, max_age=timedelta(hours=6))
            return images[-1:]
        return ()

    def all(self, conversation: str) -> tuple[IncomingAttachment, ...]:
        with self._lock:
            values = list(self._items.get(conversation, []))
        return tuple(item for _recorded, item, _received_at in values if Path(item.path).is_file())

    def _materialize_image(self, conversation: str, encoded: str, kind: str) -> IncomingAttachment:
        raw = base64.b64decode(_raw_base64(encoded), validate=False)
        if not raw or len(raw) > 20 * 1024 * 1024:
            raise ValueError("incoming image size is invalid")
        digest = hashlib.sha256(raw).hexdigest()
        suffix = _image_suffix(encoded, raw)
        directory = self._private_directory(conversation)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{kind}-{digest[:20]}{suffix}"
        if not path.exists():
            path.write_bytes(raw)
        return IncomingAttachment(
            path.name,
            str(path.resolve()),
            kind,
            len(raw),
            digest,
            _mime_type(path.name),
            datetime.now().isoformat(),
            conversation,
        )

    def _import_file(self, conversation: str, attachment: IncomingAttachment, *, received_at: str) -> IncomingAttachment:
        source = Path(attachment.path).resolve(strict=True)
        directory = self._private_directory(conversation)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / _safe_filename(attachment.name or source.name)
        source_digest = attachment.sha256 or _file_sha256(source)
        if destination.exists() and destination.resolve() != source:
            if _file_sha256(destination) != source_digest:
                stamp = _parse_received_at(received_at).strftime("%Y%m%d-%H%M%S")
                destination = directory / f"{destination.stem}-{stamp}{destination.suffix}"
        if destination.resolve() != source and not destination.exists():
            shutil.copy2(source, destination)
        return replace(
            attachment,
            name=destination.name,
            path=str(destination.resolve()),
            size=destination.stat().st_size,
            sha256=source_digest,
            mime_type=attachment.mime_type or _mime_type(destination.name),
            received_at=attachment.received_at or received_at or datetime.now().isoformat(),
            conversation=conversation,
        )

    def _private_directory(self, conversation: str) -> Path:
        digest = hashlib.sha256(conversation.encode("utf-8")).hexdigest()[:16]
        return self.root / digest / "inbox"

    def _load_index(self) -> None:
        if not self._index_path.is_file():
            return
        try:
            payload = json.loads(self._index_path.read_text(encoding="utf-8"))
            for record in payload.get("attachments", []):
                if not isinstance(record, dict):
                    continue
                conversation = str(record.get("conversation", "")).strip()
                path = str(record.get("path", "")).strip()
                if not conversation or not path or not Path(path).is_file():
                    continue
                recorded_at = _parse_received_at(str(record.get("recorded_at", "")))
                item = IncomingAttachment(
                    name=str(record.get("name", Path(path).name)),
                    path=path,
                    kind=str(record.get("kind", "file")),
                    size=int(record.get("size", 0) or 0),
                    sha256=str(record.get("sha256", "")),
                    mime_type=str(record.get("mime_type", "")),
                    received_at=str(record.get("received_at", "")),
                    conversation=conversation,
                )
                self._items.setdefault(conversation, []).append((recorded_at, item, item.received_at))
        except (OSError, ValueError, TypeError):
            return

    def _persist_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        records = []
        for conversation, values in self._items.items():
            for recorded_at, item, received_at in values:
                records.append({
                    "conversation": conversation,
                    "recorded_at": recorded_at.isoformat(),
                    "received_at": item.received_at or received_at,
                    "name": item.name,
                    "path": item.path,
                    "kind": item.kind,
                    "mime_type": item.mime_type or _mime_type(item.name),
                    "size": item.size,
                    "sha256": item.sha256,
                })
        temporary = self._index_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 1, "attachments": records}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._index_path)


def stage_task_inputs(
    task_root: str | Path,
    attachments: Iterable[IncomingAttachment],
) -> tuple[IncomingAttachment, ...]:
    input_dir = Path(task_root) / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    staged: list[IncomingAttachment] = []
    for index, attachment in enumerate(attachments, start=1):
        source = Path(attachment.path).resolve(strict=True)
        if not source.is_file():
            continue
        name = _safe_filename(attachment.name or source.name)
        destination = input_dir / name
        if destination.exists() and _file_sha256(destination) != _file_sha256(source):
            destination = input_dir / f"{index}-{name}"
        if source != destination.resolve():
            shutil.copy2(source, destination)
        staged.append(replace(
            attachment,
            name=destination.name,
            path=str(destination.resolve()),
            size=destination.stat().st_size,
            sha256=attachment.sha256 or _file_sha256(destination),
        ))
    return tuple(staged)


def _parse_received_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.split("|", 1)[0])
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        return datetime.now()


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")
    return name[:180] or "attachment.bin"


def _raw_base64(value: str) -> str:
    return value.split(",", 1)[1] if value.startswith("data:") and "," in value else value


def _image_suffix(encoded: str, raw: bytes) -> str:
    header = encoded[:64].lower()
    if "image/jpeg" in header or raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if "image/gif" in header or raw.startswith(b"GIF8"):
        return ".gif"
    if "image/webp" in header or raw[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mime_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"
