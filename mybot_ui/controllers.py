from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol

from .attachments import is_image_edit_followup, is_image_edit_request
from .auto_chat import ReplyAction, ReplyKind, requested_action
from .codex_router import CodexTaskRouter
from .personal_memory import PersonalProfile
from .realtime_tools import RealtimeToolRequest, detect_realtime_request


class PersonalMemoryStorePort(Protocol):
    def reload(self) -> None: ...
    def names(self) -> list[str]: ...
    def count(self) -> int: ...
    def get(self, name: str) -> PersonalProfile: ...
    def update(self, name: str, profile: PersonalProfile) -> None: ...
    def delete(self, name: str) -> bool: ...


class EpisodicMemoryStorePort(Protocol):
    def reload(self) -> None: ...
    def names(self) -> list[str]: ...
    def count(self, person: str = "") -> int: ...
    def recent(self, person: str, *, limit: int = 50) -> list[Any]: ...
    def delete_person(self, person: str) -> bool: ...


class DailyWorkspaceStorePort(Protocol):
    def names(self) -> list[str]: ...
    def dates(self, person: str) -> list[str]: ...
    def entries(self, person: str, day: str) -> list[Any]: ...
    def files(self, person: str, day: str) -> list[Any]: ...
    def workspace_path(self, person: str, day: str, *, create: bool = False) -> Path | None: ...


class ExtensionStorePort(Protocol):
    def list_mcps(self) -> tuple[dict[str, Any], ...]: ...
    def import_mcp(self, config_path: str | Path) -> tuple[str, ...]: ...
    def remove_mcp(self, identifier: str) -> None: ...
    def set_mcp_enabled(self, identifier: str, enabled: bool) -> None: ...
    def sync_skills(self) -> None: ...
    def list_skills(self) -> tuple[dict[str, Any], ...]: ...
    def import_skill(self, source_directory: str | Path) -> str: ...
    def remove_skill(self, identifier: str) -> None: ...
    def set_skill_enabled(self, identifier: str, enabled: bool) -> None: ...


@dataclass(frozen=True)
class PersonListItem:
    person: str
    label: str


@dataclass(frozen=True)
class MemoryCatalog:
    people: tuple[PersonListItem, ...]
    person_count: int
    episode_count: int


@dataclass(frozen=True)
class MemoryDetail:
    person: str
    profile: PersonalProfile
    episodes: tuple[Any, ...]
    dates: tuple[str, ...]
    metadata: str


@dataclass(frozen=True)
class DailyWorkspaceView:
    entries: tuple[Any, ...]
    files: tuple[Any, ...]
    workspace: Path | None


@dataclass(frozen=True)
class MemoryDeleteResult:
    profile_deleted: bool
    episodes_deleted: bool


class EmptyMemoryProfileError(ValueError):
    pass


class MemoryController:
    """Application controller for memory queries and profile commands."""

    def __init__(
        self,
        personal: PersonalMemoryStorePort,
        episodic: EpisodicMemoryStorePort,
        daily: DailyWorkspaceStorePort,
    ) -> None:
        self._personal = personal
        self._episodic = episodic
        self._daily = daily
        self._people: tuple[str, ...] = ()

    def refresh(self, query: str = "") -> MemoryCatalog:
        self._personal.reload()
        self._episodic.reload()
        self._people = tuple(sorted(
            set(self._personal.names())
            | set(self._episodic.names())
            | set(self._daily.names())
        ))
        return self.search(query)

    def search(self, query: str = "") -> MemoryCatalog:
        normalized = query.strip().casefold()
        rows: list[PersonListItem] = []
        for person in self._people:
            profile = self._personal.get(person)
            searchable = " ".join((
                person,
                profile.preferred_name,
                profile.summary,
                profile.communication_style,
                *profile.facts,
                *profile.preferences,
            )).casefold()
            if normalized and normalized not in searchable:
                continue
            label = person
            if profile.preferred_name and profile.preferred_name != person:
                label += f"\n称呼：{profile.preferred_name}"
            rows.append(PersonListItem(person, label))
        return MemoryCatalog(tuple(rows), len(self._people), self._episodic.count())

    def detail(self, person: str) -> MemoryDetail | None:
        person = person.strip()
        if not person:
            return None
        profile = self._personal.get(person)
        episodes = tuple(self._episodic.recent(person, limit=100))
        dates = tuple(self._daily.dates(person))
        metadata = [
            f"学习消息 {profile.message_count} 条",
            f"互动记忆 {len(episodes)} 条",
            f"日期工作区 {len(dates)} 天",
        ]
        if profile.updated_at:
            metadata.append("更新于 " + profile.updated_at.replace("T", " ")[:19])
        return MemoryDetail(person, profile, episodes, dates, " · ".join(metadata))

    def save(self, person: str, values: Mapping[str, Any]) -> PersonalProfile:
        existing = self._personal.get(person)
        profile = PersonalProfile.from_mapping({
            **dict(values),
            "message_count": existing.message_count,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        if not profile.configured:
            raise EmptyMemoryProfileError(
                "至少保留一项人物信息；如需彻底清除，请使用“删除人物”。"
            )
        self._personal.update(person, profile)
        return profile

    def delete(self, person: str) -> MemoryDeleteResult:
        return MemoryDeleteResult(
            profile_deleted=self._personal.delete(person),
            episodes_deleted=self._episodic.delete_person(person),
        )

    def episode_count(self, person: str) -> int:
        return self._episodic.count(person)

    def daily_workspace(self, person: str, day: str) -> DailyWorkspaceView:
        if not person.strip() or not day.strip():
            return DailyWorkspaceView((), (), None)
        return DailyWorkspaceView(
            entries=tuple(reversed(self._daily.entries(person, day))),
            files=tuple(self._daily.files(person, day)),
            workspace=self._daily.workspace_path(person, day),
        )


@dataclass(frozen=True)
class McpView:
    identifier: str
    name: str
    description: str
    source: str
    state: str
    enabled: bool


@dataclass(frozen=True)
class McpCatalog:
    items: tuple[McpView, ...]
    runtime_status: str


@dataclass(frozen=True)
class SkillView:
    identifier: str
    name: str
    kind: str
    triggers: str
    description: str
    validation: str
    usage_count: str
    state: str
    enabled: bool | None


@dataclass(frozen=True)
class SkillCatalog:
    items: tuple[SkillView, ...]
    summary: str


class ExtensionController:
    """Application controller for MCP and Skill inventory commands."""

    def __init__(self, extensions: ExtensionStorePort, abilities: Any, codex: Any) -> None:
        self._extensions = extensions
        self._abilities = abilities
        self._codex = codex

    def mcps(self) -> McpCatalog:
        runtime = self._codex.status()
        rows = []
        for server in self._extensions.list_mcps():
            enabled = bool(server["enabled"])
            state = "可用" if runtime.installed and enabled else (
                "已禁用" if not enabled else "等待安装 CLI"
            )
            rows.append(McpView(
                identifier=str(server["id"]),
                name=str(server.get("name", server["id"])),
                description=str(server.get("description", "")),
                source="内置" if server["builtin"] else "已导入",
                state=state,
                enabled=enabled,
            ))
        status = f"CLI {runtime.version}" if runtime.installed else "CLI 未安装"
        return McpCatalog(tuple(rows), status)

    def skills(self) -> SkillCatalog:
        self._extensions.sync_skills()
        project_skills = self._extensions.list_skills()
        matched_skills = self._abilities.list_abilities()
        rows = [
            SkillView(
                identifier=str(skill["id"]),
                name=str(skill["name"]),
                kind="内置" if skill["builtin"] else "已导入",
                triggers="",
                description=str(skill["description"]),
                validation="",
                usage_count="",
                state="可读取" if skill["enabled"] else "已禁用",
                enabled=bool(skill["enabled"]),
            )
            for skill in project_skills
        ]
        for skill in matched_skills:
            triggers = skill.get("triggers", [])
            if not isinstance(triggers, list):
                triggers = [str(triggers)] if triggers else []
            rows.append(SkillView(
                identifier="",
                name=str(skill.get("name", "")),
                kind="自动匹配",
                triggers="、".join(str(value) for value in triggers if str(value).strip()),
                description=str(skill.get("description", "")),
                validation=str(skill.get("validation", "未记录")),
                usage_count=str(skill.get("usage_count", 0)),
                state="已验证",
                enabled=None,
            ))
        return SkillCatalog(
            tuple(rows),
            f"项目 {len(project_skills)} · 自动匹配 {len(matched_skills)}",
        )

    def import_mcp(self, path: str | Path) -> tuple[str, ...]:
        return self._extensions.import_mcp(path)

    def remove_mcp(self, identifier: str) -> None:
        self._extensions.remove_mcp(identifier)

    def set_mcp_enabled(self, identifier: str, enabled: bool) -> None:
        self._extensions.set_mcp_enabled(identifier, enabled)

    def import_skill(self, path: str | Path) -> str:
        return self._extensions.import_skill(path)

    def remove_skill(self, identifier: str) -> None:
        self._extensions.remove_skill(identifier)

    def set_skill_enabled(self, identifier: str, enabled: bool) -> None:
        self._extensions.set_skill_enabled(identifier, enabled)


@dataclass(frozen=True)
class QueueDispatch:
    state: str
    incoming: Any = None
    task_key: str = ""
    delay_ms: int = 0
    active_before: int = 0
    remaining_depth: int = 0
    enqueued_at: float | None = None
    started_at: float | None = None


@dataclass(frozen=True)
class QueueCompletion:
    was_active: bool
    no_active_tasks: bool
    enqueued_at: float | None
    started_at: float | None


class ConversationTaskController:
    """Owns per-conversation queue, concurrency, and task timing state."""

    def __init__(self) -> None:
        self.pending: dict[str, int] = {}
        self.active_tasks: set[str] = set()
        self.queues: dict[str, deque[Any]] = {}
        self.enqueued_at: dict[str, float] = {}
        self.started_at: dict[str, float] = {}

    def reset(self) -> None:
        self.pending.clear()
        self.active_tasks.clear()
        self.queues.clear()
        self.enqueued_at.clear()
        self.started_at.clear()

    def enqueue(self, incoming: Any, task_key: str, *, now: float) -> int:
        chat_title = str(getattr(incoming, "chat_title", ""))
        self.enqueued_at[task_key] = now
        queue = self.queues.setdefault(chat_title, deque())
        queue.append(incoming)
        return len(queue)

    def active_count(self, chat_title: str) -> int:
        return max(0, int(self.pending.get(chat_title, 0)))

    def acquire(
        self,
        chat_title: str,
        *,
        running: bool,
        connected: bool,
        recovering: bool,
        selected: set[str],
        concurrency: int,
        cooldown_remaining: float,
        task_key_for: Any,
        now: float,
    ) -> QueueDispatch:
        queue = self.queues.get(chat_title)
        if not running or not queue or recovering or not connected:
            return QueueDispatch("blocked")
        active_before = self.active_count(chat_title)
        if active_before >= max(1, int(concurrency)):
            return QueueDispatch("capacity", active_before=active_before)
        if active_before == 0 and cooldown_remaining > 0:
            return QueueDispatch(
                "cooldown",
                delay_ms=max(50, int(cooldown_remaining * 1000)),
                active_before=active_before,
            )
        incoming = queue.popleft()
        task_key = str(task_key_for(incoming))
        enqueued_at = self.enqueued_at.get(task_key)
        if str(getattr(incoming, "chat_title", "")) not in selected:
            self.enqueued_at.pop(task_key, None)
            return QueueDispatch(
                "discarded",
                incoming=incoming,
                task_key=task_key,
                active_before=active_before,
                remaining_depth=len(queue),
                enqueued_at=enqueued_at,
            )
        self.started_at[task_key] = now
        self.pending[chat_title] = active_before + 1
        self.active_tasks.add(task_key)
        return QueueDispatch(
            "start",
            incoming=incoming,
            task_key=task_key,
            active_before=active_before,
            remaining_depth=len(queue),
            enqueued_at=enqueued_at,
            started_at=now,
        )

    def finish(self, chat_title: str, task_key: str) -> QueueCompletion:
        enqueued_at = self.enqueued_at.pop(task_key, None)
        started_at = self.started_at.pop(task_key, None)
        was_active = task_key in self.active_tasks
        self.active_tasks.discard(task_key)
        if was_active:
            remaining = max(0, self.active_count(chat_title) - 1)
            if remaining:
                self.pending[chat_title] = remaining
            else:
                self.pending.pop(chat_title, None)
        return QueueCompletion(
            was_active=was_active,
            no_active_tasks=not self.active_tasks,
            enqueued_at=enqueued_at,
            started_at=started_at,
        )


@dataclass(frozen=True)
class RouteDecision:
    route: str
    action: ReplyAction
    image_edit_request: str = ""
    image_edit_source: str = ""
    realtime_request: RealtimeToolRequest | None = None
    restricted_categories: tuple[str, ...] = ()


class ConversationRouteController:
    """Pure routing policy for one accepted inbound conversation task."""

    def decide(
        self,
        *,
        content: str,
        conversation_context: str,
        codex_enabled: bool,
        restricted_categories: tuple[str, ...] = (),
        is_admin: bool = False,
        pending_image_edit: str = "",
        has_incoming_image: bool = False,
    ) -> RouteDecision:
        action = requested_action(content)
        if restricted_categories and not is_admin:
            return RouteDecision(
                "security_denied",
                action,
                restricted_categories=restricted_categories,
            )

        explicit_image_edit = (
            action.kind is ReplyKind.TEXT and is_image_edit_request(content)
        )
        resume_pending_edit = bool(pending_image_edit) and (
            has_incoming_image or is_image_edit_followup(content)
        )
        image_edit = (
            content
            if explicit_image_edit
            else pending_image_edit if resume_pending_edit else ""
        )
        if image_edit:
            source = (
                "explicit"
                if explicit_image_edit
                else "pending_with_image" if has_incoming_image else "pending_followup"
            )
            return RouteDecision("image_edit", action, image_edit, source)

        realtime_request = (
            detect_realtime_request(content, conversation_context)
            if codex_enabled and action.kind in {ReplyKind.TEXT, ReplyKind.VOICE}
            else None
        )
        if realtime_request is not None:
            return RouteDecision(
                "realtime",
                action,
                realtime_request=realtime_request,
            )
        if (
            codex_enabled
            and action.kind is ReplyKind.TEXT
            and CodexTaskRouter.should_delegate(content)
        ):
            return RouteDecision("codex", action)
        return RouteDecision(action.kind.value, action)
