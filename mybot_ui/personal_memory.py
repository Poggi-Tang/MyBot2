from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .chat_engine import ChatModelClient, ModelConfig
from .operation_log import operations


LEARNING_PROMPT = """你负责维护微信联系人的长期个人记忆。根据已有档案和一轮新对话，返回更新后的 JSON 对象。
规则：
1. 只记录对方明确表达、对以后聊天有帮助的信息，不猜测或脑补。
2. 不推断或记录密码、财务账号、精确住址、证件、政治倾向、疾病等敏感属性。
3. 助手回复只用于理解上下文，不能当作对方的事实。
4. 当前信息与旧信息冲突时，以当前明确表达为准；没有新信息时保留旧档案。
5. 内容要短、具体、可用于自然交流，不要保存完整原句或聊天流水。
6. 只输出 JSON，不要 Markdown。字段必须为：preferred_name, summary, facts, preferences, communication_style, current_context, avoid_topics。
facts、preferences、current_context、avoid_topics 必须是字符串数组，其余字段是字符串。"""


def person_id(
    chat_title: str,
    sender: str,
    is_group: bool,
    aliases: Mapping[str, str] | None = None,
) -> str:
    name = (sender if is_group else chat_title).strip()
    return _canonical_name(name, aliases or {})


def _canonical_name(name: str, aliases: Mapping[str, str]) -> str:
    current = name.strip()
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        replacement = str(aliases.get(current, "")).strip()
        if not replacement:
            break
        current = replacement
    return current


def _clean_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _clean_items(value: Any, *, count: int = 12, length: int = 120) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[str] = []
    for item in value:
        text = _clean_text(item, length)
        if text and text not in result:
            result.append(text)
        if len(result) >= count:
            break
    return tuple(result)


def _memory_tokens(value: str) -> set[str]:
    text = value.casefold()
    tokens = set(re.findall(r"[a-z0-9_]{2,}", text))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.update(run)
        tokens.update(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def _relevant_items(items: tuple[str, ...], current_message: str, limit: int) -> tuple[str, ...]:
    if len(items) <= limit:
        return items
    query_tokens = _memory_tokens(current_message)

    def score(index_and_item: tuple[int, str]) -> tuple[float, int]:
        index, item = index_and_item
        item_tokens = _memory_tokens(item)
        overlap = len(query_tokens & item_tokens) / max(1, min(len(query_tokens), len(item_tokens)))
        exact = 1.0 if current_message.strip() and current_message.strip() in item else 0.0
        recency = index / max(1, len(items) - 1)
        return (0.75 * max(overlap, exact) + 0.25 * recency, index)

    ranked = sorted(enumerate(items), key=score, reverse=True)[:limit]
    return tuple(item for _index, item in ranked)


@dataclass(frozen=True)
class PersonalProfile:
    preferred_name: str = ""
    summary: str = ""
    facts: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()
    communication_style: str = ""
    current_context: tuple[str, ...] = ()
    avoid_topics: tuple[str, ...] = ()
    message_count: int = 0
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, value: Any) -> "PersonalProfile":
        source = value if isinstance(value, Mapping) else {}
        try:
            message_count = max(0, int(source.get("message_count", 0)))
        except (TypeError, ValueError):
            message_count = 0
        return cls(
            preferred_name=_clean_text(source.get("preferred_name"), 60),
            summary=_clean_text(source.get("summary"), 320),
            facts=_clean_items(source.get("facts")),
            preferences=_clean_items(source.get("preferences")),
            communication_style=_clean_text(source.get("communication_style"), 240),
            current_context=_clean_items(source.get("current_context"), count=8),
            avoid_topics=_clean_items(source.get("avoid_topics"), count=8),
            message_count=message_count,
            updated_at=_clean_text(source.get("updated_at"), 40),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.preferred_name
            or self.summary
            or self.facts
            or self.preferences
            or self.communication_style
            or self.current_context
            or self.avoid_topics
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "preferred_name": self.preferred_name,
            "summary": self.summary,
            "facts": list(self.facts),
            "preferences": list(self.preferences),
            "communication_style": self.communication_style,
            "current_context": list(self.current_context),
            "avoid_topics": list(self.avoid_topics),
            "message_count": self.message_count,
            "updated_at": self.updated_at,
        }

    def prompt(self, display_name: str, current_message: str = "") -> str:
        if not self.configured:
            return ""
        lines = [
            f"以下是从以往对话中提炼的“{display_name}”个人记忆。",
            "只用于自然地调整回复，不要逐项复述档案，不要提到正在分析或记录对方；若与当前消息冲突，以当前消息为准。",
        ]
        if self.preferred_name:
            lines.append("对方偏好的称呼：" + self.preferred_name)
        if self.summary:
            lines.append("简要了解：" + self.summary)
        facts = _relevant_items(self.facts, current_message, 5)
        preferences = _relevant_items(self.preferences, current_message, 4)
        current_context = _relevant_items(self.current_context, current_message, 4)
        if facts:
            lines.append("与当前话题较相关的明确事实：" + "；".join(facts))
        if preferences:
            lines.append("与当前话题较相关的偏好：" + "；".join(preferences))
        if self.communication_style:
            lines.append("适合的交流方式：" + self.communication_style)
        if current_context:
            lines.append("与当前话题较相关的近期上下文：" + "；".join(current_context))
        if self.avoid_topics:
            lines.append("不喜欢或应避免：" + "；".join(self.avoid_topics))
        return "\n".join(lines)


class PersonalMemoryStore:
    def __init__(
        self,
        path: str | Path,
        *,
        aliases: Mapping[str, str] | None = None,
        ignored_names: set[str] | tuple[str, ...] | list[str] = (),
    ) -> None:
        self.path = Path(path)
        self.aliases = {
            str(source).strip(): str(target).strip()
            for source, target in (aliases or {}).items()
            if str(source).strip() and str(target).strip()
        }
        self.ignored_names = {str(name).strip() for name in ignored_names if str(name).strip()}
        self._lock = threading.RLock()
        self._profiles: dict[str, PersonalProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, Mapping):
                return
            changed = False
            for raw_name, raw_profile in data.items():
                name = str(raw_name).strip()
                if not name or name in self.ignored_names:
                    changed = changed or bool(name)
                    continue
                canonical = _canonical_name(name, self.aliases)
                profile = PersonalProfile.from_mapping(raw_profile)
                if not canonical or canonical in self.ignored_names:
                    changed = True
                    continue
                if canonical in self._profiles:
                    self._profiles[canonical] = _merge_profiles(self._profiles[canonical], profile)
                    changed = True
                else:
                    self._profiles[canonical] = profile
                    changed = changed or canonical != name
            if changed:
                self._write()
        except (OSError, ValueError, TypeError):
            self._profiles = {}

    def get(self, name: str) -> PersonalProfile:
        with self._lock:
            canonical = _canonical_name(name.strip(), self.aliases)
            return self._profiles.get(canonical, PersonalProfile())

    def names(self) -> list[str]:
        with self._lock:
            return sorted(name for name, profile in self._profiles.items() if profile.configured)

    def count(self) -> int:
        with self._lock:
            return sum(profile.configured for profile in self._profiles.values())

    def reload(self) -> None:
        with self._lock:
            self._profiles = {}
            self._load()

    def update(self, name: str, profile: PersonalProfile) -> None:
        key = name.strip()
        if not key:
            return
        key = _canonical_name(key, self.aliases)
        if not key or key in self.ignored_names:
            return
        with self._lock:
            self._profiles[key] = profile
            self._write()

    def delete(self, name: str) -> bool:
        key = _canonical_name(name.strip(), self.aliases)
        if not key:
            return False
        with self._lock:
            removed = self._profiles.pop(key, None) is not None
            if removed:
                self._write()
            return removed

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {item: value.to_mapping() for item, value in sorted(self._profiles.items())},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


class PersonalMemoryLearner:
    def __init__(self, client: ChatModelClient, store: PersonalMemoryStore) -> None:
        self.client = client
        self.store = store

    def learn(
        self,
        *,
        primary: ModelConfig,
        backup: ModelConfig | None,
        name: str,
        user_message: str,
        assistant_reply: str,
    ) -> PersonalProfile:
        span = operations.start("workflow", "personal_memory_learn", details={
            "person": name,
            "user_message_length": len(user_message),
            "assistant_reply_length": len(assistant_reply),
        })
        try:
            existing = self.store.get(name)
            payload = {
                "existing_profile": existing.to_mapping(),
                "new_exchange": {
                    "user": user_message[:2000],
                    "assistant": assistant_reply[:2000],
                },
            }
            response = self.client.generate_with_fallback(
                primary,
                backup,
                [
                    {"role": "system", "content": LEARNING_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
            learned = PersonalProfile.from_mapping(_parse_json_object(response))
            learned = PersonalProfile.from_mapping({
                **learned.to_mapping(),
                "message_count": existing.message_count + 1,
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            })
            self.store.update(name, learned)
            operations.finish(span, success=True, result={
                "person": name,
                "profile_changed": learned.to_mapping() != existing.to_mapping(),
                "message_count": learned.message_count,
            })
            return learned
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise


def _parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("个人记忆模型未返回 JSON 对象")
        result = json.loads(text[start : end + 1])
    if not isinstance(result, dict):
        raise ValueError("个人记忆模型返回的不是 JSON 对象")
    return result


def _merge_profiles(first: PersonalProfile, second: PersonalProfile) -> PersonalProfile:
    primary, secondary = (
        (second, first)
        if second.updated_at and second.updated_at > first.updated_at
        else (first, second)
    )

    def combined(left: tuple[str, ...], right: tuple[str, ...], limit: int = 12) -> tuple[str, ...]:
        values: list[str] = []
        for item in (*left, *right):
            if item and item not in values:
                values.append(item)
        return tuple(values[-limit:])

    return PersonalProfile(
        preferred_name=primary.preferred_name or secondary.preferred_name,
        summary=primary.summary or secondary.summary,
        facts=combined(first.facts, second.facts),
        preferences=combined(first.preferences, second.preferences),
        communication_style=primary.communication_style or secondary.communication_style,
        current_context=combined(first.current_context, second.current_context, 8),
        avoid_topics=combined(first.avoid_topics, second.avoid_topics, 8),
        message_count=max(first.message_count, second.message_count),
        updated_at=max(first.updated_at, second.updated_at),
    )
