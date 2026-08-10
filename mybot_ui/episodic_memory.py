from __future__ import annotations

import json
import math
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .operation_log import operations
from .personal_memory import _canonical_name


_SENSITIVE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"(?:密码|口令|验证码|支付密码|银行卡|身份证|精确住址|病历|疾病|政治倾向)"),
    re.compile(r"(?:api[_ -]?key|access[_ -]?token|authorization)\s*[:=]", re.IGNORECASE),
)
_IMPORTANT_MARKERS = (
    "记住", "以后", "一直", "喜欢", "不喜欢", "讨厌", "偏好", "习惯",
    "叫我", "称呼", "生日", "工作", "正在", "最近", "重要", "别再",
)


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _contains_sensitive(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)


def _tokens(text: str) -> set[str]:
    lowered = text.casefold()
    words = set(re.findall(r"[a-z0-9_]{2,}", lowered))
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
    for run in chinese_runs:
        words.update(run)
        words.update(run[index : index + 2] for index in range(len(run) - 1))
    return words


def _relevance(query: str, candidate: str) -> float:
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = len(query_tokens & candidate_tokens)
    score = overlap / max(1, min(len(query_tokens), len(candidate_tokens)))
    if query.strip() and query.strip() in candidate:
        score = max(score, 0.95)
    return min(1.0, score)


def estimate_importance(user_message: str) -> int:
    text = user_message.strip()
    score = 1
    score += min(2, sum(marker in text for marker in _IMPORTANT_MARKERS))
    if any(mark in text for mark in ("!", "！", "?", "？")):
        score += 1
    if len(text) >= 80:
        score += 1
    return min(5, score)


@dataclass(frozen=True)
class Episode:
    user_message: str
    assistant_reply: str
    timestamp: str
    importance: int = 1

    @classmethod
    def from_mapping(cls, value: Any) -> "Episode | None":
        if not isinstance(value, Mapping):
            return None
        user_message = _clean(value.get("user_message"), 1000)
        assistant_reply = _clean(value.get("assistant_reply"), 1000)
        timestamp = _clean(value.get("timestamp"), 40)
        try:
            importance = max(1, min(5, int(value.get("importance", 1))))
        except (TypeError, ValueError):
            importance = 1
        if not user_message or not assistant_reply or not timestamp:
            return None
        if _contains_sensitive(user_message) or _contains_sensitive(assistant_reply):
            return None
        return cls(user_message, assistant_reply, timestamp, importance)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "user_message": self.user_message,
            "assistant_reply": self.assistant_reply,
            "timestamp": self.timestamp,
            "importance": self.importance,
        }


class EpisodicMemoryStore:
    def __init__(
        self,
        path: str | Path,
        *,
        max_per_person: int = 200,
        aliases: Mapping[str, str] | None = None,
        ignored_names: set[str] | tuple[str, ...] | list[str] = (),
    ) -> None:
        self.path = Path(path)
        self.max_per_person = max(10, max_per_person)
        self.aliases = {
            str(source).strip(): str(target).strip()
            for source, target in (aliases or {}).items()
            if str(source).strip() and str(target).strip()
        }
        self.ignored_names = {str(name).strip() for name in ignored_names if str(name).strip()}
        self._lock = threading.RLock()
        self._episodes: dict[str, list[Episode]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, Mapping):
                return
            episodes: dict[str, list[Episode]] = {}
            changed = False
            for raw_person, raw_items in data.items():
                person = _clean(raw_person, 100)
                if not person or person in self.ignored_names or not isinstance(raw_items, list):
                    changed = changed or bool(person)
                    continue
                canonical = _canonical_name(person, self.aliases)
                if not canonical or canonical in self.ignored_names:
                    changed = True
                    continue
                items = [Episode.from_mapping(item) for item in raw_items]
                current = episodes.setdefault(canonical, [])
                for item in (item for item in items if item is not None):
                    if not any(
                        existing.user_message == item.user_message
                        and existing.assistant_reply == item.assistant_reply
                        for existing in current
                    ):
                        current.append(item)
                del current[:-self.max_per_person]
                changed = changed or canonical != person
            self._episodes = episodes
            if changed:
                self._write()
        except (OSError, ValueError, TypeError):
            self._episodes = {}

    def add(self, person: str, user_message: str, assistant_reply: str) -> bool:
        span = operations.start("workflow", "episodic_memory_record", details={"person": person})
        person = _canonical_name(_clean(person, 100), self.aliases)
        user_message = _clean(user_message, 1000)
        assistant_reply = _clean(assistant_reply, 1000)
        if (
            not person
            or not user_message
            or not assistant_reply
            or person in self.ignored_names
            or _contains_sensitive(user_message)
            or _contains_sensitive(assistant_reply)
        ):
            operations.finish(span, success=True, result={"stored": False, "reason": "empty_or_sensitive"})
            return False
        episode = Episode(
            user_message=user_message,
            assistant_reply=assistant_reply,
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            importance=estimate_importance(user_message),
        )
        try:
            with self._lock:
                items = self._episodes.setdefault(person, [])
                if items and (
                    items[-1].user_message == episode.user_message
                    and items[-1].assistant_reply == episode.assistant_reply
                ):
                    operations.finish(span, success=True, result={"stored": False, "reason": "duplicate"})
                    return False
                items.append(episode)
                del items[:-self.max_per_person]
                self._write()
            operations.finish(span, success=True, result={"stored": True, "importance": episode.importance})
            return True
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def names(self) -> list[str]:
        with self._lock:
            return sorted(person for person, items in self._episodes.items() if items)

    def count(self, person: str = "") -> int:
        with self._lock:
            if not person.strip():
                return sum(len(items) for items in self._episodes.values())
            canonical = _canonical_name(person.strip(), self.aliases)
            return len(self._episodes.get(canonical, ()))

    def recent(self, person: str, *, limit: int = 50) -> list[Episode]:
        with self._lock:
            canonical = _canonical_name(person.strip(), self.aliases)
            items = self._episodes.get(canonical, ())
            return list(reversed(items[-max(0, limit) :]))

    def reload(self) -> None:
        with self._lock:
            self._episodes = {}
            self._load()

    def delete_person(self, person: str) -> bool:
        canonical = _canonical_name(person.strip(), self.aliases)
        if not canonical:
            return False
        with self._lock:
            removed = self._episodes.pop(canonical, None) is not None
            if removed:
                self._write()
            return removed

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    person: [episode.to_mapping() for episode in items]
                    for person, items in sorted(self._episodes.items())
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def retrieve(self, person: str, current_message: str, *, limit: int = 3) -> list[Episode]:
        span = operations.start("workflow", "episodic_memory_retrieve", details={
            "person": person,
            "query_length": len(current_message),
            "limit": limit,
        })
        try:
            now = datetime.now(timezone.utc)
            with self._lock:
                canonical = _canonical_name(person.strip(), self.aliases)
                items = list(self._episodes.get(canonical, ()))

            def scored(index_and_episode: tuple[int, Episode]) -> tuple[float, int]:
                index, episode = index_and_episode
                try:
                    timestamp = datetime.fromisoformat(episode.timestamp)
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    age_days = max(
                        0.0,
                        (now - timestamp.astimezone(timezone.utc)).total_seconds() / 86400,
                    )
                    recency = math.exp(-age_days / 30.0)
                except ValueError:
                    recency = 0.0
                relevance = _relevance(
                    current_message,
                    episode.user_message + " " + episode.assistant_reply,
                )
                importance = episode.importance / 5.0
                return (0.60 * relevance + 0.25 * recency + 0.15 * importance, index)

            ranked = sorted(enumerate(items), key=scored, reverse=True)
            result = [episode for _index, episode in ranked[: max(0, min(limit, 5))]]
            operations.finish(span, success=True, result={
                "candidate_count": len(items),
                "retrieved_count": len(result),
            })
            return result
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def prompt(self, person: str, current_message: str, *, limit: int = 3) -> str:
        episodes = self.retrieve(person, current_message, limit=limit)
        if not episodes:
            return ""
        lines = [
            f"以下是与“{person}”当前话题最相关的过往互动片段。",
            "只把它们当作延续上下文的参考，不要说自己查了记忆，不要逐字复述；当前消息与旧内容冲突时以当前消息为准。",
        ]
        for episode in episodes:
            lines.append(f"- 对方曾说：{episode.user_message}；你当时回应：{episode.assistant_reply}")
        return "\n".join(lines)
