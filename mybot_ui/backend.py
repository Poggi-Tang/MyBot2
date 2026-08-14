from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable
from urllib.parse import urlparse

from .api import DEFAULT_WEBSOCKET_MAX_MESSAGE_BYTES, Gateway, GatewayResult
from .attachments import ConversationAttachmentStore, WeChatAttachmentResolver
from .chat_engine import ChatModelClient, ConversationMemory, ImageConfig, ModelConfig
from .codex_install import CodexRuntimeManager
from .codex_router import ReusableTaskReviewer
from .codex_runner import CodexCliRunner, CodexRuntimeConfig, CodexThreadStore
from .conversation_actions import ConversationActionExecutor
from .conversation_scanner import ConversationScanner
from .controllers import (
    ConversationRouteController,
    ConversationTaskController,
    ExtensionController,
    MemoryController,
)
from .daily_workspace import DailyWorkspaceStore
from .episodic_memory import EpisodicMemoryStore
from .extension_abilities import ExtensionAbilityStore
from .extension_registry import ExtensionRegistry, ExtensionRegistryError
from .image_understanding import ImageUnderstandingCache
from .operation_log import operations
from .personal_memory import PersonalMemoryLearner, PersonalMemoryStore
from .realtime_tools import RealtimeToolExecutor
from .voice_actor import HiggsVoiceActor
from .wechat_message_service import WeChatMessageService


@dataclass(frozen=True)
class WeChatCommand:
    account: str
    function: str
    options: Any = ""
    timeout_seconds: int | None = None


@runtime_checkable
class WeChatAutomationPort(Protocol):
    @property
    def connected(self) -> bool: ...

    @connected.setter
    def connected(self, value: bool) -> None: ...

    @property
    def clients(self) -> list[str]: ...

    @property
    def uri(self) -> str: ...

    def add_listener(self, callback: Callable[[dict[str, Any]], None]) -> None: ...

    def connect(self, uri: str | None = None) -> Future: ...

    def disconnect(self) -> Future: ...

    def dispatch(self, command: WeChatCommand) -> Future: ...

    def close(self) -> None: ...


class GatewayWeChatAutomation:
    """Infrastructure adapter for the WeChat WebSocket SDK."""

    def __init__(
        self,
        *,
        max_message_bytes: int = DEFAULT_WEBSOCKET_MAX_MESSAGE_BYTES,
        gateway_factory: Callable[..., Gateway] = Gateway,
    ) -> None:
        self._gateway = gateway_factory(max_message_bytes=max_message_bytes)

    @property
    def connected(self) -> bool:
        return self._gateway.connected

    @connected.setter
    def connected(self, value: bool) -> None:
        self._gateway.connected = bool(value)

    @property
    def clients(self) -> list[str]:
        return self._gateway.clients

    @property
    def uri(self) -> str:
        return self._gateway.uri

    def add_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._gateway.add_listener(callback)

    def connect(self, uri: str | None = None) -> Future:
        return self._gateway.connect(uri)

    def disconnect(self) -> Future:
        return self._gateway.disconnect()

    def dispatch(self, command: WeChatCommand) -> Future:
        return self._gateway.call(
            command.account,
            command.function,
            command.options,
            timeout_seconds=command.timeout_seconds,
        )

    def close(self) -> None:
        self._gateway.close()


@runtime_checkable
class ModelOperationsPort(Protocol):
    def list_models(self, config: ModelConfig) -> list[str]: ...

    def generate(
        self,
        config: ModelConfig,
        messages: list[dict[str, Any]],
        *,
        timeout: int = 120,
    ) -> str: ...

    def generate_with_fallback(
        self,
        primary: ModelConfig,
        backup: ModelConfig | None,
        messages: list[dict[str, Any]],
        *,
        timeout: int = 120,
    ) -> str: ...

    def generate_image(
        self,
        config: ImageConfig,
        prompt: str,
        output_dir: str | Path | None = None,
    ) -> str: ...

    def edit_image(
        self,
        config: ImageConfig,
        prompt: str,
        source_image: str | Path,
        output_dir: str | Path | None = None,
    ) -> str: ...


class ModelOperations:
    """Application-facing model service; provider details stay behind this port."""

    def __init__(self, client: ChatModelClient | None = None) -> None:
        self._client = client or ChatModelClient()

    def list_models(self, config: ModelConfig) -> list[str]:
        return self._client.list_models(config)

    def generate(
        self,
        config: ModelConfig,
        messages: list[dict[str, Any]],
        *,
        timeout: int = 120,
    ) -> str:
        return self._client.generate(config, messages, timeout=timeout)

    def generate_with_fallback(
        self,
        primary: ModelConfig,
        backup: ModelConfig | None,
        messages: list[dict[str, Any]],
        *,
        timeout: int = 120,
    ) -> str:
        return self._client.generate_with_fallback(
            primary,
            backup,
            messages,
            timeout=timeout,
        )

    def generate_image(
        self,
        config: ImageConfig,
        prompt: str,
        output_dir: str | Path | None = None,
    ) -> str:
        return self._client.generate_image(config, prompt, output_dir)

    def edit_image(
        self,
        config: ImageConfig,
        prompt: str,
        source_image: str | Path,
        output_dir: str | Path | None = None,
    ) -> str:
        return self._client.edit_image(config, prompt, source_image, output_dir)


@runtime_checkable
class ExtensionManagementPort(Protocol):
    def list_mcps(self) -> tuple[dict[str, Any], ...]: ...

    def import_mcp(self, config_path: str | Path) -> tuple[str, ...]: ...

    def remove_mcp(self, identifier: str) -> None: ...

    def set_mcp_enabled(self, identifier: str, enabled: bool) -> None: ...

    def sync_skills(self) -> None: ...

    def list_skills(self) -> tuple[dict[str, Any], ...]: ...

    def import_skill(self, source_directory: str | Path) -> str: ...

    def remove_skill(self, identifier: str) -> None: ...

    def set_skill_enabled(self, identifier: str, enabled: bool) -> None: ...


class ExtensionOperationError(ValueError):
    pass


class ExtensionManagement:
    """Application service around project-local MCP and Skill persistence."""

    def __init__(self, registry: ExtensionRegistry) -> None:
        self._registry = registry

    def _call(self, method: str, *args):
        try:
            return getattr(self._registry, method)(*args)
        except ExtensionRegistryError as exc:
            raise ExtensionOperationError(str(exc)) from exc

    def list_mcps(self) -> tuple[dict[str, Any], ...]:
        return self._call("list_mcps")

    def import_mcp(self, config_path: str | Path) -> tuple[str, ...]:
        return self._call("import_mcp", config_path)

    def remove_mcp(self, identifier: str) -> None:
        self._call("remove_mcp", identifier)

    def set_mcp_enabled(self, identifier: str, enabled: bool) -> None:
        self._call("set_mcp_enabled", identifier, enabled)

    def sync_skills(self) -> None:
        self._call("sync_skills")

    def list_skills(self) -> tuple[dict[str, Any], ...]:
        return self._call("list_skills")

    def import_skill(self, source_directory: str | Path) -> str:
        return self._call("import_skill", source_directory)

    def remove_skill(self, identifier: str) -> None:
        self._call("remove_skill", identifier)

    def set_skill_enabled(self, identifier: str, enabled: bool) -> None:
        self._call("set_skill_enabled", identifier, enabled)


@runtime_checkable
class ConversationMemoryPort(Protocol):
    def add_user(self, chat: str, who: str, content: str, image_base64: str = "", visual_context: str = "") -> None: ...

    def add_assistant(self, chat: str, content: str) -> None: ...

    def recent_assistant_texts(self, chat: str, limit: int = 8) -> tuple[str, ...]: ...

    def resolve_latest_visual(self, chat: str, who: str, content: str, kind: str, description: str) -> bool: ...

    def transcript(self, chat: str, max_chars: int = 6_000) -> str: ...

    def context(self, chat: str, system_prompt: str, policy_messages=()) -> list[dict[str, Any]]: ...


@runtime_checkable
class PersonalMemoryPort(Protocol):
    path: Path

    def get(self, name: str): ...

    def names(self) -> list[str]: ...

    def count(self) -> int: ...

    def reload(self) -> None: ...

    def update(self, name: str, profile: Any) -> None: ...

    def delete(self, name: str) -> bool: ...


@runtime_checkable
class EpisodicMemoryPort(Protocol):
    path: Path

    def add(self, person: str, user_message: str, assistant_reply: str) -> bool: ...

    def names(self) -> list[str]: ...

    def count(self, person: str = "") -> int: ...

    def recent(self, person: str, *, limit: int = 50) -> list[Any]: ...

    def reload(self) -> None: ...

    def delete_person(self, person: str) -> bool: ...

    def prompt(self, person: str, current_message: str, *, limit: int = 3) -> str: ...


@runtime_checkable
class DailyWorkspacePort(Protocol):
    root: Path

    def names(self) -> list[str]: ...

    def dates(self, person: str) -> list[str]: ...

    def entries(self, person: str, day: str) -> list[Any]: ...

    def files(self, person: str, day: str) -> list[Any]: ...

    def workspace_path(self, person: str, day: str, *, create: bool = False) -> Path | None: ...

    def record(self, *args, **kwargs): ...


@runtime_checkable
class AttachmentWorkspacePort(Protocol):
    root: Path

    def remember(self, conversation: str, attachments, **kwargs) -> tuple[Any, ...]: ...

    def recent(self, conversation: str, **kwargs) -> tuple[Any, ...]: ...

    def for_request(self, conversation: str, request: str, *, received_at: str = "") -> tuple[Any, ...]: ...

    def all(self, conversation: str) -> tuple[Any, ...]: ...


@runtime_checkable
class CodexOperationsPort(Protocol):
    @property
    def executable(self) -> Path: ...

    @property
    def proxy_executable(self) -> Path: ...

    @property
    def codex_home(self) -> Path: ...

    def status(self): ...

    def install(self, progress=None): ...

    def runner(self, config: CodexRuntimeConfig) -> CodexCliRunner: ...


class CodexOperations:
    def __init__(self, manager: CodexRuntimeManager, abilities: Any, threads: Any) -> None:
        self._manager = manager
        self._abilities = abilities
        self._threads = threads

    @property
    def executable(self) -> Path:
        return self._manager.executable

    @property
    def proxy_executable(self) -> Path:
        return self._manager.proxy_executable

    @property
    def codex_home(self) -> Path:
        return self._manager.codex_home

    def status(self):
        return self._manager.status()

    def install(self, progress=None):
        return self._manager.install(progress)

    def runner(self, config: CodexRuntimeConfig) -> CodexCliRunner:
        return CodexCliRunner(config, self._abilities, self._threads)


@dataclass
class TaskExecutors:
    models: ThreadPoolExecutor
    memory: ThreadPoolExecutor
    codex: ThreadPoolExecutor
    abilities: ThreadPoolExecutor
    conversations: ThreadPoolExecutor

    @classmethod
    def create(cls, *, chat_concurrency: int) -> TaskExecutors:
        return cls(
            models=ThreadPoolExecutor(
                max_workers=max(4, chat_concurrency * 2),
                thread_name_prefix="mybot-ai",
            ),
            memory=ThreadPoolExecutor(max_workers=1, thread_name_prefix="mybot-memory"),
            codex=ThreadPoolExecutor(max_workers=2, thread_name_prefix="mybot-codex"),
            abilities=ThreadPoolExecutor(max_workers=1, thread_name_prefix="mybot-ability"),
            conversations=ThreadPoolExecutor(max_workers=1, thread_name_prefix="mybot-conversation-scan"),
        )

    def close(self) -> None:
        for executor in (
            self.models,
            self.memory,
            self.codex,
            self.abilities,
            self.conversations,
        ):
            executor.shutdown(wait=False, cancel_futures=True)


@dataclass
class ApplicationServices:
    """Non-Qt composition root for application capabilities and state stores."""

    conversation_memory: ConversationMemoryPort
    personal_memory: PersonalMemoryPort
    personal_memory_learner: Any
    episodic_memory: EpisodicMemoryPort
    daily_workspace: DailyWorkspacePort
    abilities: Any
    extensions: ExtensionManagementPort
    codex: CodexOperationsPort
    attachments: AttachmentWorkspacePort
    image_understanding: Any
    reusable_task_reviewer: Any
    realtime_tools: Any
    voice_actor: Any
    memory_controller: MemoryController
    extension_controller: ExtensionController
    conversation_tasks: ConversationTaskController
    conversation_router: ConversationRouteController
    conversation_actions: ConversationActionExecutor
    conversation_scanner: ConversationScanner
    wechat_messages: WeChatMessageService
    executors: TaskExecutors
    personal_memory_aliases: dict[str, str]
    personal_memory_ignored_names: set[str]

    @classmethod
    def create(
        cls,
        *,
        project_root: Path,
        settings: dict[str, Any],
        models: ModelOperationsPort,
        chat_concurrency: int,
    ) -> ApplicationServices:
        memory_settings = settings.get("personal_memory", {})
        if not isinstance(memory_settings, dict):
            memory_settings = {}
        configured_aliases = memory_settings.get("name_aliases", {})
        aliases = (
            {
                str(source).strip(): str(target).strip()
                for source, target in configured_aliases.items()
                if str(source).strip() and str(target).strip()
            }
            if isinstance(configured_aliases, dict)
            else {}
        )
        configured_ignored_names = memory_settings.get("ignored_names", [])
        ignored_names = (
            {str(name).strip() for name in configured_ignored_names if str(name).strip()}
            if isinstance(configured_ignored_names, list)
            else set()
        )

        personal_path = cls._project_path(
            project_root,
            memory_settings.get("path", "data/personal-memory.json"),
        )
        episodic_path = cls._project_path(
            project_root,
            memory_settings.get("episodic_path", "data/episodic-memory.json"),
        )
        workspace_path = cls._project_path(
            project_root,
            memory_settings.get("daily_workspace_path", "data/people"),
        )
        personal_memory = PersonalMemoryStore(
            personal_path,
            aliases=aliases,
            ignored_names=ignored_names,
        )
        abilities = ExtensionAbilityStore(project_root / "extensions")

        attachment_settings = settings.get("attachments", {})
        if not isinstance(attachment_settings, dict):
            attachment_settings = {}
        attachment_roots = attachment_settings.get("wechat_file_roots", [])
        if not isinstance(attachment_roots, list):
            attachment_roots = []

        vision_settings = settings.get("vision_cache", {})
        if not isinstance(vision_settings, dict):
            vision_settings = {}
        try:
            perceptual_threshold = int(vision_settings.get("perceptual_threshold", 4) or 4)
        except (TypeError, ValueError):
            perceptual_threshold = 4

        episodic_memory = EpisodicMemoryStore(
            episodic_path,
            aliases=aliases,
            ignored_names=ignored_names,
        )
        daily_workspace = DailyWorkspaceStore(
            workspace_path,
            aliases=aliases,
            ignored_names=ignored_names,
        )
        extensions = ExtensionManagement(ExtensionRegistry(project_root))
        codex = CodexOperations(
            CodexRuntimeManager(project_root),
            abilities,
            CodexThreadStore(project_root / "data" / "codex" / "threads.json"),
        )
        return cls(
            conversation_memory=ConversationMemory(),
            personal_memory=personal_memory,
            personal_memory_learner=PersonalMemoryLearner(models, personal_memory),
            episodic_memory=episodic_memory,
            daily_workspace=daily_workspace,
            abilities=abilities,
            extensions=extensions,
            codex=codex,
            attachments=ConversationAttachmentStore(
                project_root / "data" / "attachments",
                WeChatAttachmentResolver(attachment_roots),
            ),
            image_understanding=ImageUnderstandingCache(
                project_root / "data" / "image-understanding-cache.json",
                perceptual_threshold=perceptual_threshold,
            ),
            reusable_task_reviewer=ReusableTaskReviewer(models),
            realtime_tools=RealtimeToolExecutor(),
            voice_actor=HiggsVoiceActor(models),
            memory_controller=MemoryController(
                personal_memory,
                episodic_memory,
                daily_workspace,
            ),
            extension_controller=ExtensionController(extensions, abilities, codex),
            conversation_tasks=ConversationTaskController(),
            conversation_router=ConversationRouteController(),
            conversation_actions=ConversationActionExecutor(),
            conversation_scanner=ConversationScanner(),
            wechat_messages=WeChatMessageService(project_root),
            executors=TaskExecutors.create(chat_concurrency=chat_concurrency),
            personal_memory_aliases=aliases,
            personal_memory_ignored_names=ignored_names,
        )

    @staticmethod
    def _project_path(project_root: Path, configured: Any) -> Path:
        path = Path(str(configured))
        return path if path.is_absolute() else project_root / path

    def close(self) -> None:
        self.wechat_messages.stop()
        self.executors.close()


@runtime_checkable
class ServerLifecyclePort(Protocol):
    def process_ids(self, executable: Path) -> list[int]: ...

    def stop(self, executable: Path) -> None: ...

    def restart(self, executable: Path, websocket_url: str) -> GatewayResult: ...


class WindowsServerLifecycle:
    """Owns only the configured WeChat SDK Server.exe process lifecycle."""

    @staticmethod
    def process_ids(executable: Path) -> list[int]:
        if os.name != "nt":
            return []
        if executable.name.casefold() != "server.exe":
            operations.event("backend", "server_process_target_rejected", {
                "path": str(executable),
                "reason": "unexpected executable name",
            })
            return []
        escaped = str(executable).replace("'", "''")
        script = (
            "$target='" + escaped + "'; "
            "Get-CimInstance Win32_Process -Filter \"Name='Server.exe'\" | "
            "Where-Object { $_.ExecutablePath -eq $target } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        pids: list[int] = []
        for line in completed.stdout.splitlines():
            try:
                pids.append(int(line.strip()))
            except ValueError:
                continue
        return pids

    def stop(self, executable: Path) -> None:
        self._validate_target(executable)
        for pid in self.process_ids(executable):
            stopped = subprocess.run(
                ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if stopped.returncode != 0:
                detail = (stopped.stderr or stopped.stdout).strip()
                raise RuntimeError(
                    f"无法停止旧 Server (PID {pid})：{detail or '权限不足'}"
                )

    def restart(self, executable: Path, websocket_url: str) -> GatewayResult:
        span = operations.start(
            "backend",
            "server_restart",
            details={"executable": str(executable), "websocket_url": websocket_url},
        )
        try:
            self._validate_target(executable)
            self.stop(executable)
            shutdown_deadline = time.monotonic() + 5.0
            while self.process_ids(executable) and time.monotonic() < shutdown_deadline:
                time.sleep(0.1)
            if self.process_ids(executable):
                raise RuntimeError("旧 Server 未在 5 秒内完全退出")
            sync_deadline = time.monotonic() + 5.0
            while True:
                try:
                    synced_dll = self.sync_development_server_dll(executable)
                    break
                except PermissionError:
                    if time.monotonic() >= sync_deadline:
                        raise
                    time.sleep(0.1)
            parsed = urlparse(websocket_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 5177
            server_environment = os.environ.copy()
            server_environment["ASPNETCORE_URLS"] = f"http://{host}:{port}"
            process = subprocess.Popen(
                [str(executable), "--urls", f"http://{host}:{port}"],
                cwd=str(executable.parent),
                env=server_environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Server 启动后立即退出，退出码 {process.returncode}"
                    )
                try:
                    with socket.create_connection((host, port), timeout=0.4):
                        result = {
                            "pid": process.pid,
                            "path": str(executable),
                            "sdk_dll_synced": synced_dll,
                        }
                        operations.finish(span, success=True, result=result)
                        return GatewayResult(True, result)
                except OSError:
                    time.sleep(0.25)
            raise TimeoutError(f"等待 Server 端口 {host}:{port} 超时")
        except Exception as exc:
            operations.finish(span, success=False, error=exc)
            return GatewayResult(False, error=str(exc))

    @staticmethod
    def sync_development_server_dll(executable: Path) -> bool:
        target = executable.parent / "WeChatAuto.dll"
        sdk_root = executable.parents[5] if len(executable.parents) > 5 else None
        if sdk_root is None or sdk_root.name != "WeChatAuto4_X":
            return False
        source = (
            sdk_root / "WeChatAuto" / "bin" / "Debug"
            / "net10.0-windows" / "WeChatAuto.dll"
        )
        if not source.is_file():
            return False
        if target.is_file() and source.stat().st_mtime_ns <= target.stat().st_mtime_ns:
            return False
        shutil.copy2(source, target)
        return True

    @staticmethod
    def _validate_target(executable: Path) -> None:
        if executable.name.casefold() != "server.exe":
            raise ValueError(f"拒绝操作非 Server.exe 目标：{executable}")


@dataclass
class ApplicationBackend:
    wechat: WeChatAutomationPort
    server: ServerLifecyclePort
    models: ModelOperationsPort
    services: ApplicationServices | None = None

    @classmethod
    def create(
        cls,
        *,
        websocket_max_message_bytes: int,
        project_root: Path | None = None,
        settings: dict[str, Any] | None = None,
        chat_concurrency: int = 3,
    ) -> ApplicationBackend:
        models = ModelOperations()
        backend = cls(
            wechat=GatewayWeChatAutomation(
                max_message_bytes=websocket_max_message_bytes,
            ),
            server=WindowsServerLifecycle(),
            models=models,
        )
        if project_root is not None:
            backend.services = ApplicationServices.create(
                project_root=project_root,
                settings=settings or {},
                models=models,
                chat_concurrency=chat_concurrency,
            )
        return backend

    def dispatch_wechat(
        self,
        account: str,
        function: str,
        options: Any = "",
        *,
        timeout_seconds: int | None = None,
    ) -> Future:
        return self.wechat.dispatch(WeChatCommand(
            account=account,
            function=function,
            options=options,
            timeout_seconds=timeout_seconds,
        ))

    def close(self) -> None:
        self.wechat.close()
        if self.services is not None:
            self.services.close()
