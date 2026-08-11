from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .personal_memory import _canonical_name


_DATE_DIRECTORY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class WorkspaceFile:
    name: str
    path: str
    kind: str = "file"
    size: int = 0
    sha256: str = ""

    @classmethod
    def from_mapping(cls, value: Any) -> "WorkspaceFile | None":
        if not isinstance(value, Mapping):
            return None
        name = str(value.get("name", "")).strip()
        path = str(value.get("path", "")).strip()
        if not name or not path:
            return None
        return cls(
            name=name,
            path=path,
            kind=str(value.get("kind", "file") or "file"),
            size=max(0, int(value.get("size", 0) or 0)),
            sha256=str(value.get("sha256", "") or ""),
        )

    def to_mapping(self, workspace: Path) -> dict[str, Any]:
        path = Path(self.path)
        try:
            stored_path = str(path.resolve().relative_to(workspace.resolve()))
        except (OSError, ValueError):
            stored_path = str(path)
        return {
            "name": self.name,
            "path": stored_path,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class DailyEntry:
    event_id: str
    timestamp: str
    direction: str
    conversation: str
    sender: str
    content: str
    files: tuple[WorkspaceFile, ...] = ()


class DailyWorkspaceStore:
    """Append-only per-person, per-day conversation and file archive."""

    def __init__(
        self,
        root: str | Path,
        *,
        aliases: Mapping[str, str] | None = None,
        ignored_names: Iterable[str] = (),
    ) -> None:
        self.root = Path(root)
        self.aliases = {
            str(source).strip(): str(target).strip()
            for source, target in (aliases or {}).items()
            if str(source).strip() and str(target).strip()
        }
        self.ignored_names = {str(name).strip() for name in ignored_names if str(name).strip()}
        self._lock = threading.RLock()
        self._seen: dict[Path, set[str]] = {}

    def record(
        self,
        person: str,
        *,
        direction: str,
        conversation: str,
        sender: str,
        content: str,
        timestamp: str = "",
        files: Iterable[Any] = (),
    ) -> DailyEntry | None:
        canonical = _canonical_name(str(person).strip(), self.aliases)
        direction = str(direction).strip().lower()
        if not canonical or canonical in self.ignored_names or direction not in {
            "incoming", "outgoing", "work",
        }:
            return None
        occurred_at = _parse_timestamp(timestamp)
        normalized_timestamp = occurred_at.astimezone().isoformat(timespec="seconds")
        day = occurred_at.astimezone().date().isoformat()
        content = str(content or "").strip()
        conversation = str(conversation or "").strip()
        sender = str(sender or "").strip()

        with self._lock:
            workspace = self._workspace(canonical, day, create=True)
            archived = tuple(
                item
                for source in files
                if (item := self._archive_file(workspace, source)) is not None
            )
            if not content and not archived:
                return None
            identity = json.dumps(
                {
                    "person": canonical,
                    "timestamp": normalized_timestamp,
                    "direction": direction,
                    "conversation": conversation,
                    "sender": sender,
                    "content": content,
                    "files": [item.sha256 or item.name for item in archived],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            journal = workspace / "journal.jsonl"
            seen = self._seen_ids(journal)
            entry = DailyEntry(
                event_id=event_id,
                timestamp=normalized_timestamp,
                direction=direction,
                conversation=conversation,
                sender=sender,
                content=content,
                files=archived,
            )
            if event_id in seen:
                return entry
            payload = {
                "event_id": event_id,
                "timestamp": normalized_timestamp,
                "direction": direction,
                "conversation": conversation,
                "sender": sender,
                "content": content,
                "files": [item.to_mapping(workspace) for item in archived],
            }
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
            seen.add(event_id)
            return entry

    def names(self) -> list[str]:
        if not self.root.is_dir():
            return []
        names: set[str] = set()
        for directory in self.root.iterdir():
            metadata = directory / "person.json"
            if not directory.is_dir() or not metadata.is_file():
                continue
            try:
                value = json.loads(metadata.read_text(encoding="utf-8"))
                person = str(value.get("person", "")).strip() if isinstance(value, dict) else ""
                if person:
                    names.add(person)
            except (OSError, ValueError, TypeError):
                continue
        return sorted(names)

    def dates(self, person: str) -> list[str]:
        directory = self._person_directory(str(person).strip(), create=False)
        if directory is None or not directory.is_dir():
            return []
        return sorted(
            (
                child.name
                for child in directory.iterdir()
                if child.is_dir() and _DATE_DIRECTORY.fullmatch(child.name)
            ),
            reverse=True,
        )

    def entries(self, person: str, day: str) -> list[DailyEntry]:
        workspace = self._workspace(str(person).strip(), day, create=False)
        journal = workspace / "journal.jsonl" if workspace is not None else None
        if journal is None or not journal.is_file():
            return []
        entries: list[DailyEntry] = []
        try:
            for line in journal.read_text(encoding="utf-8").splitlines():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(value, dict):
                    continue
                files = tuple(
                    item
                    for raw in value.get("files", [])
                    if (item := self._file_from_mapping(workspace, raw)) is not None
                )
                entries.append(DailyEntry(
                    event_id=str(value.get("event_id", "")),
                    timestamp=str(value.get("timestamp", "")),
                    direction=str(value.get("direction", "")),
                    conversation=str(value.get("conversation", "")),
                    sender=str(value.get("sender", "")),
                    content=str(value.get("content", "")),
                    files=files,
                ))
        except OSError:
            return []
        return entries

    def files(self, person: str, day: str) -> list[WorkspaceFile]:
        unique: dict[str, WorkspaceFile] = {}
        for entry in self.entries(person, day):
            for item in entry.files:
                unique[item.sha256 or item.path] = item
        return sorted(unique.values(), key=lambda item: item.name.casefold())

    def workspace_path(self, person: str, day: str, *, create: bool = False) -> Path | None:
        return self._workspace(str(person).strip(), day, create=create)

    def _workspace(self, person: str, day: str, *, create: bool) -> Path | None:
        canonical = _canonical_name(str(person).strip(), self.aliases)
        if not canonical or not _DATE_DIRECTORY.fullmatch(str(day)):
            return None
        directory = self._person_directory(canonical, create=create)
        if directory is None:
            return None
        workspace = directory / str(day)
        if create:
            (workspace / "files").mkdir(parents=True, exist_ok=True)
        return workspace

    def _person_directory(self, person: str, *, create: bool) -> Path | None:
        canonical = _canonical_name(str(person).strip(), self.aliases)
        if not canonical:
            return None
        safe = _safe_segment(canonical)
        directory = self.root / safe
        metadata = directory / "person.json"
        if directory.exists():
            existing = _metadata_person(metadata)
            if existing and existing != canonical:
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]
                directory = self.root / f"{safe}-{digest}"
                metadata = directory / "person.json"
        if create:
            directory.mkdir(parents=True, exist_ok=True)
            if not metadata.exists():
                temporary = metadata.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps({"person": canonical}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary, metadata)
        return directory

    def _archive_file(self, workspace: Path, source: Any) -> WorkspaceFile | None:
        raw_path = getattr(source, "path", source)
        try:
            path = Path(str(raw_path)).resolve(strict=True)
        except (OSError, ValueError):
            return None
        if not path.is_file():
            return None
        name = _safe_filename(str(getattr(source, "name", "") or path.name))
        kind = str(getattr(source, "kind", "file") or "file")
        digest = str(getattr(source, "sha256", "") or "") or _file_sha256(path)
        destination = workspace / "files" / name
        if destination.exists() and _file_sha256(destination) != digest:
            destination = destination.with_name(f"{destination.stem}-{digest[:8]}{destination.suffix}")
        if path != destination.resolve() and not destination.exists():
            shutil.copy2(path, destination)
        return WorkspaceFile(
            name=destination.name,
            path=str(destination.resolve()),
            kind=kind,
            size=destination.stat().st_size,
            sha256=digest,
        )

    def _seen_ids(self, journal: Path) -> set[str]:
        cached = self._seen.get(journal)
        if cached is not None:
            return cached
        values: set[str] = set()
        if journal.is_file():
            try:
                for line in journal.read_text(encoding="utf-8").splitlines():
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    event_id = str(payload.get("event_id", "")) if isinstance(payload, dict) else ""
                    if event_id:
                        values.add(event_id)
            except OSError:
                pass
        self._seen[journal] = values
        return values

    @staticmethod
    def _file_from_mapping(workspace: Path, value: Any) -> WorkspaceFile | None:
        item = WorkspaceFile.from_mapping(value)
        if item is None:
            return None
        path = Path(item.path)
        if not path.is_absolute():
            path = workspace / path
        return WorkspaceFile(item.name, str(path.resolve()), item.kind, item.size, item.sha256)


def _parse_timestamp(value: str) -> datetime:
    text = str(value or "").strip()
    match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?", text)
    if match:
        candidate = match.group(0).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.astimezone()
            return parsed
        except ValueError:
            pass
    return datetime.now().astimezone()


def _safe_segment(value: str) -> str:
    cleaned = _INVALID_PATH_CHARS.sub("_", value).strip(" .")[:80] or "未命名"
    if cleaned.casefold() in _WINDOWS_RESERVED:
        cleaned = "_" + cleaned
    return cleaned


def _safe_filename(value: str) -> str:
    name = Path(str(value).replace("\\", "/")).name
    return _safe_segment(name)


def _metadata_person(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return str(value.get("person", "")).strip() if isinstance(value, dict) else ""
    except (OSError, ValueError, TypeError):
        return ""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
