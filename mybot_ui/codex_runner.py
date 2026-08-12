from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .attachments import IncomingAttachment, MAX_ATTACHMENT_BYTES, stage_task_inputs
from .extension_abilities import ExtensionAbilityStore
from .operation_log import operations


class CodexCliError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexRuntimeConfig:
    executable: Path
    proxy_executable: Path
    project_root: Path
    base_url: str
    api_key: str
    model: str
    codex_home: Path | None = None
    timeout_seconds: int = 900
    mcp_tool_timeout_seconds: int = 5
    thread_max_tasks: int = 2
    thread_max_context_chars: int = 12_000
    thread_max_age_seconds: int = 1_800
    model_reasoning_effort: str = "low"
    yolo_mode: bool = False
    restricted_workspace: bool = False
    privileged: bool = False


@dataclass(frozen=True)
class CodexResult:
    text: str
    thread_id: str
    task_id: str
    matched_abilities: tuple[str, ...] = ()
    output_files: tuple[str, ...] = ()


class CodexThreadStore:
    _lock = threading.RLock()

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get(self, conversation: str) -> str:
        with self._lock:
            item = self._read().get(conversation, "")
            if isinstance(item, dict):
                return str(item.get("thread_id", "")).strip()
            return str(item).strip()

    def select(
        self,
        conversation: str,
        *,
        incoming_context_chars: int,
        max_tasks: int,
        max_context_chars: int,
        max_age_seconds: int,
        now: float | None = None,
    ) -> tuple[str, str]:
        with self._lock:
            item = self._read().get(conversation)
        if item is None:
            return "", "new_conversation"
        if not isinstance(item, dict):
            return "", "legacy_thread"
        thread_id = str(item.get("thread_id", "")).strip()
        if not thread_id:
            return "", "invalid_thread"
        try:
            task_count = max(0, int(item.get("task_count", 0)))
            context_chars = max(0, int(item.get("context_chars", 0)))
            created_at = float(item.get("created_at", 0))
        except (TypeError, ValueError):
            return "", "invalid_metadata"
        current_time = time.time() if now is None else now
        if created_at <= 0 or current_time - created_at >= max_age_seconds:
            return "", "age_limit"
        if task_count >= max_tasks:
            return "", "task_limit"
        if context_chars + max(0, incoming_context_chars) > max_context_chars:
            return "", "context_limit"
        return thread_id, "resume"

    def set(
        self,
        conversation: str,
        thread_id: str,
        *,
        context_chars: int = 0,
        resumed: bool = False,
        now: float | None = None,
    ) -> None:
        if not conversation.strip() or not thread_id.strip():
            return
        with self._lock:
            data = self._read()
            current_time = time.time() if now is None else now
            previous = data.get(conversation)
            if resumed and isinstance(previous, dict) and str(previous.get("thread_id", "")).strip() == thread_id:
                try:
                    task_count = max(0, int(previous.get("task_count", 0))) + 1
                    total_context_chars = max(0, int(previous.get("context_chars", 0))) + max(0, context_chars)
                    created_at = float(previous.get("created_at", current_time))
                except (TypeError, ValueError):
                    task_count = 1
                    total_context_chars = max(0, context_chars)
                    created_at = current_time
            else:
                task_count = 1
                total_context_chars = max(0, context_chars)
                created_at = current_time
            data[conversation] = {
                "thread_id": thread_id,
                "created_at": created_at,
                "updated_at": current_time,
                "task_count": task_count,
                "context_chars": total_context_chars,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)

    def clear(self, conversation: str) -> None:
        with self._lock:
            data = self._read()
            data.pop(conversation, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


class CodexCliRunner:
    _locks_guard = threading.Lock()
    _conversation_locks: dict[str, threading.Lock] = {}

    def __init__(
        self,
        config: CodexRuntimeConfig,
        ability_store: ExtensionAbilityStore,
        thread_store: CodexThreadStore,
    ) -> None:
        self.config = config
        self.ability_store = ability_store
        self.thread_store = thread_store

    def run(
        self,
        conversation: str,
        request: str,
        *,
        conversation_context: str = "",
        task_id: str = "",
        attachments: tuple[IncomingAttachment, ...] = (),
    ) -> CodexResult:
        message = request.strip()
        if not message or len(message) > 12_000 or "\x00" in message:
            raise CodexCliError("Codex 任务为空、过长或无效。")
        self._validate_runtime()
        lock = self._conversation_lock(conversation)
        with lock:
            return self._run_locked(conversation, message, conversation_context, task_id, attachments)

    def probe(self) -> str:
        self._validate_runtime()
        completed, text, _thread_id = self._execute(
            "只回复 MYBOT_CODEX_OK",
            workspace=self.config.project_root,
            previous_thread="",
            ephemeral=True,
            task_context=None,
        )
        if completed.returncode:
            raise CodexCliError("Codex CLI 连接测试失败：" + self._last_error(completed))
        if "MYBOT_CODEX_OK" not in text:
            raise CodexCliError("Codex CLI 已启动，但模型没有返回预期测试结果。")
        return text

    def _run_locked(
        self,
        conversation: str,
        request: str,
        context: str,
        task_id: str,
        attachments: tuple[IncomingAttachment, ...],
    ) -> CodexResult:
        task_id = task_id or uuid.uuid4().hex
        task_root = self.config.project_root / "data" / "codex" / "tasks" / task_id
        output_dir = task_root / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        staged_inputs = stage_task_inputs(task_root, attachments)
        matches = () if self.config.restricted_workspace else self.ability_store.matching(request)
        ability_context = "\n\n".join(value.prompt() for value in matches)
        attachment_context = self._attachment_prompt(staged_inputs, output_dir)
        incoming_context_chars = sum(map(len, (request, context, ability_context, attachment_context)))
        thread_conversation = (
            f"restricted::{conversation}"
            if self.config.restricted_workspace
            else conversation
        )
        previous_thread, thread_decision = self.thread_store.select(
            thread_conversation,
            incoming_context_chars=incoming_context_chars,
            max_tasks=self.config.thread_max_tasks,
            max_context_chars=self.config.thread_max_context_chars,
            max_age_seconds=self.config.thread_max_age_seconds,
        )
        prompt = (
            self._resume_prompt(request, context, ability_context, attachment_context)
            if previous_thread
            else self._initial_prompt(request, context, ability_context, attachment_context)
        )
        span = operations.start("codex", "codex_cli_run", operation_id=task_id, details={
            "conversation": conversation,
            "request_length": len(request),
            "resumed": bool(previous_thread),
            "thread_decision": thread_decision,
            "incoming_context_chars": incoming_context_chars,
            "matched_abilities": [value.ability_id for value in matches],
            "input_file_count": len(staged_inputs),
        })
        task_context = {
            "task_id": task_id,
            "conversation": conversation,
            "request": request,
            "matched_abilities": [value.ability_id for value in matches],
            "input_files": [
                {
                    "name": item.name,
                    "path": item.path,
                    "kind": item.kind,
                    "size": item.size,
                    "sha256": item.sha256,
                }
                for item in staged_inputs
            ],
            "output_dir": str(output_dir.resolve()),
            "privileged": bool(self.config.privileged),
        }
        try:
            completed, text, thread_id = self._execute(
                prompt,
                workspace=task_root if self.config.restricted_workspace else self.config.project_root,
                previous_thread=previous_thread,
                ephemeral=False,
                task_context=task_context,
            )
            if completed.returncode and previous_thread and self._resume_missing(completed):
                self.thread_store.clear(thread_conversation)
                previous_thread = ""
                thread_decision = "missing_thread"
                prompt = self._initial_prompt(request, context, ability_context, attachment_context)
                completed, text, thread_id = self._execute(
                    prompt,
                    workspace=task_root if self.config.restricted_workspace else self.config.project_root,
                    previous_thread="",
                    ephemeral=False,
                    task_context=task_context,
                )
            if completed.returncode:
                raise CodexCliError("Codex CLI 执行失败：" + self._last_error(completed))
            if not text:
                raise CodexCliError("Codex CLI 没有返回可发送的结果。")
            active_thread = thread_id or previous_thread
            if active_thread:
                self.thread_store.set(
                    thread_conversation,
                    active_thread,
                    context_chars=len(prompt),
                    resumed=bool(previous_thread),
                )
            output_files = self._task_output_files(task_root)
            operations.event("codex", "codex_output_scan", {
                "task_id": task_id,
                "output_file_count": len(output_files),
                "delivery_source": "manifest_and_outputs_scan",
            })
            result = CodexResult(
                text=text[:4_000],
                thread_id=active_thread,
                task_id=task_id,
                matched_abilities=tuple(value.ability_id for value in matches),
                output_files=output_files,
            )
            if result.matched_abilities:
                try:
                    self.ability_store.record_usage(result.matched_abilities)
                    operations.event("codex", "codex_ability_usage", {
                        "task_id": task_id,
                        "ability_ids": list(result.matched_abilities),
                        "recorded": True,
                    })
                except OSError as exc:
                    operations.event("codex", "codex_ability_usage", {
                        "task_id": task_id,
                        "ability_ids": list(result.matched_abilities),
                        "recorded": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            operations.finish(span, success=True, result={
                "thread_id": active_thread,
                "thread_decision": thread_decision,
                "reply_length": len(result.text),
                "matched_abilities": list(result.matched_abilities),
                "output_file_count": len(result.output_files),
            })
            return result
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def distill_ability(
        self,
        *,
        task_id: str,
        request: str,
        result: str,
        suggested_name: str,
        suggested_triggers: tuple[str, ...],
        forbidden_terms: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        candidate = self.ability_store.candidate_path(task_id)
        candidate.mkdir(parents=True, exist_ok=False)
        prompt = self._distillation_prompt(
            request=request,
            result=result,
            candidate=candidate,
            suggested_name=suggested_name,
            suggested_triggers=suggested_triggers,
        )
        span = operations.start("codex", "codex_ability_distill", operation_id=task_id, details={
            "candidate": str(candidate),
            "suggested_name": suggested_name,
        })
        try:
            completed, codex_text, _thread = self._execute(
                prompt,
                workspace=candidate,
                previous_thread="",
                ephemeral=True,
                task_context=None,
            )
            if completed.returncode:
                raise CodexCliError("能力沉淀任务失败：" + self._last_error(completed))
            if not (candidate / "manifest.json").is_file():
                raise CodexCliError(
                    "Codex 未创建候选能力文件：" + (codex_text.strip()[:500] or "未返回说明")
                )
            item = self.ability_store.promote_candidate(candidate, forbidden_terms=forbidden_terms)
            operations.finish(span, success=True, result={
                "ability_id": item["id"],
                "scripts": item["scripts"],
            })
            return item
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def _execute(
        self,
        prompt: str,
        *,
        workspace: Path,
        previous_thread: str,
        ephemeral: bool,
        task_context: dict[str, Any] | None,
    ) -> tuple[subprocess.CompletedProcess[str], str, str]:
        control_dir = self.config.project_root / "data" / "codex" / "tmp"
        control_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="last-", suffix=".txt", dir=control_dir, delete=False) as stream:
            output_path = Path(stream.name)
        context_path: Path | None = None
        task_token = ""
        proxy = None
        try:
            if task_context is not None:
                task_token = uuid.uuid4().hex
                context_path = control_dir / f"task-{task_context['task_id']}.json"
                context_path.write_text(
                    json.dumps({**task_context, "task_token": task_token}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            proxy, proxy_base_url = self._start_proxy(control_dir)
            command = self._command(
                proxy_base_url,
                output_path,
                workspace,
                previous_thread=previous_thread,
                ephemeral=ephemeral,
            )
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
                shell=False,
                cwd=workspace,
                startupinfo=self._startupinfo(),
                env=self._environment(context_path=context_path, task_token=task_token),
            )
            try:
                text = output_path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                text = ""
            return completed, text, self._thread_id(completed.stdout)
        except subprocess.TimeoutExpired as exc:
            stage = self._timeout_stage(exc)
            suffix = f"（最后阶段：{stage}）" if stage else ""
            raise CodexCliError(f"Codex CLI 执行超时{suffix}。") from exc
        except OSError as exc:
            raise CodexCliError("无法启动 Codex CLI 或官方代理。") from exc
        finally:
            output_path.unlink(missing_ok=True)
            if context_path is not None:
                context_path.unlink(missing_ok=True)
            if proxy is not None:
                self._stop_proxy(proxy)

    def _start_proxy(self, control_dir: Path) -> tuple[subprocess.Popen, str]:
        info_path = control_dir / f"proxy-{uuid.uuid4().hex}.json"
        command = [
            str(self.config.proxy_executable),
            "--server-info", str(info_path),
            "--http-shutdown",
            "--upstream-url", self._responses_url(self.config.base_url),
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            cwd=self.config.project_root,
            startupinfo=self._startupinfo(),
            env=self._environment(),
        )
        assert process.stdin is not None
        process.stdin.write(self.config.api_key + "\n")
        process.stdin.close()
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise CodexCliError("Codex Responses 代理启动失败。")
                if info_path.is_file():
                    info = json.loads(info_path.read_text(encoding="utf-8"))
                    port = int(info["port"])
                    return process, f"http://127.0.0.1:{port}/v1"
                time.sleep(0.05)
            raise CodexCliError("Codex Responses 代理启动超时。")
        finally:
            info_path.unlink(missing_ok=True)

    @staticmethod
    def _stop_proxy(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            # The proxy listens only on loopback, but its ephemeral port is not
            # retained here. Closing stdin is not a shutdown signal on Windows.
            process.terminate()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass

    def _command(
        self,
        proxy_base_url: str,
        output_path: Path,
        workspace: Path,
        *,
        previous_thread: str,
        ephemeral: bool,
    ) -> list[str]:
        base = [
            str(self.config.executable),
            "-c", 'model_provider="mybot"',
            "-c", 'model_providers.mybot.name="MyBot"',
            "-c", f'model_providers.mybot.base_url="{proxy_base_url}"',
            "-c", 'model_providers.mybot.wire_api="responses"',
            "-c", "model_providers.mybot.requires_openai_auth=false",
            "-c", "model_providers.mybot.supports_websockets=false",
            "-c", "disable_response_storage=true",
            "-c", f'model_reasoning_effort="{self.config.model_reasoning_effort}"',
            "-c", f'mcp_servers.mybot.command="{Path(sys.executable).as_posix()}"',
            "-c", 'mcp_servers.mybot.args=["-m","mybot_mcp.server"]',
            "-c", "mcp_servers.mybot.startup_timeout_sec=20",
            "-c", f"mcp_servers.mybot.tool_timeout_sec={self.config.mcp_tool_timeout_seconds}",
            "-c", "mcp_servers.mybot.enabled=true",
            "-c", 'mcp_servers.mybot.default_tools_approval_mode="approve"',
            "-c", 'mcp_servers.mybot.enabled_tools=["report_progress","register_output_file"]',
            "-c", 'mcp_servers.mybot.env_vars=["MYBOT_TASK_CONTEXT","MYBOT_TASK_TOKEN","PYTHONPATH","PYTHONUTF8","PYTHONIOENCODING"]',
            "-c", f'mcp_servers.autowx.command="{Path(sys.executable).as_posix()}"',
            "-c", 'mcp_servers.autowx.args=["-m","autowx_mcp.server"]',
            "-c", "mcp_servers.autowx.startup_timeout_sec=20",
            "-c", f"mcp_servers.autowx.tool_timeout_sec={max(35, self.config.mcp_tool_timeout_seconds)}",
            "-c", "mcp_servers.autowx.enabled=true",
            "-c", 'mcp_servers.autowx.default_tools_approval_mode="approve"',
            "-c", 'mcp_servers.autowx.enabled_tools=["list_functions","get_function_schema","plan_function_call","get_connection_status","connect_gateway","disconnect_gateway","call_sdk_function"]',
            "-c", 'mcp_servers.autowx.env_vars=["AUTOWX_GATEWAY_URL","AUTOWX_ACCOUNT","MYBOT_TASK_CONTEXT","MYBOT_TASK_TOKEN","PYTHONPATH","PYTHONUTF8","PYTHONIOENCODING"]',
            "--enable", "code_mode_host",
        ]
        if not self.config.yolo_mode:
            base.extend([
                "-c", 'approval_policy="never"',
                "-c", 'windows.sandbox="elevated"',
                "-c", 'default_permissions="mybot_workspace"',
                "-c", 'permissions.mybot_workspace.description="Current MyBot task workspace only"',
                "-c", 'permissions.mybot_workspace.filesystem={":minimal"="read",":workspace_roots"={"."="write"}}',
                "-c", "permissions.mybot_workspace.network.enabled=true",
            ])
        unrestricted = ["--dangerously-bypass-approvals-and-sandbox"] if self.config.yolo_mode else []
        if previous_thread:
            return [
                *base,
                "exec", "resume",
                *unrestricted,
                "--json", "--ignore-user-config", "--skip-git-repo-check",
                "-m", self.config.model,
                "--output-last-message", str(output_path),
                previous_thread, "-",
            ]
        return [
            *base,
            "exec",
            *unrestricted,
            "--json", "--ignore-user-config", "--skip-git-repo-check",
            "-C", str(workspace),
            "-m", self.config.model,
            *( ["--ephemeral"] if ephemeral else [] ),
            "--output-last-message", str(output_path),
            "-",
        ]

    def _validate_runtime(self) -> None:
        for path, name in (
            (self.config.executable, "Codex CLI"),
            (self.config.proxy_executable, "Codex Responses 代理"),
        ):
            if not path.is_file():
                raise CodexCliError(f"{name}不存在：{path}")
        if not self.config.api_key or not self.config.base_url or not self.config.model:
            raise CodexCliError("Codex 接口地址、模型或密钥未配置。")
        self._codex_home().mkdir(parents=True, exist_ok=True)

    def _initial_prompt(self, request: str, context: str, abilities: str, attachments: str = "") -> str:
        return "\n\n".join((
            "你是 MyBot 异步调度的 Codex CLI。实际完成任务并验证结果，不要只给建议。",
            "需要直接读取或操作微信时，使用 $autowx-strategyd 并通过 autowx MCP 执行；不得自行绕过 MCP 调用 SDK。MyBot 消息监听器由主程序独占，不得暂停、恢复或重建监听。写操作必须先向当前用户说明准确目标和影响，并取得本次任务中的明确授权。",
            "任务上下文、附件和匹配能力已经完整注入，不要重复读取通用 MyBot Skill，也不要调用 get_task_context 或 get_capabilities。若明确匹配到快捷能力，只读取该能力自己的 SKILL.md、配方和脚本。只修改完成任务所需的文件并保留已有改动。只有用户在当前任务中明确要求时，才可以执行 git commit、git push、创建远程仓库、PR、Issue 或 Release 等外部写操作；GitHub 操作优先使用本机已认证的 gh CLI。",
            "如果任务需要用户刚发的附件，但【任务附件】显示没有输入文件，必须明确说明没有拿到本次原文件并停止。严禁搜索或复用 data/codex/tasks、旧 outputs、其他会话或历史任务中的文件来代替本次附件。",
            "需要交付文件时，只能写入任务指定的 output_dir；调用 mybot.register_output_file 时只传相对于 output_dir 的准确文件名。登记失败或超时不要重试、不要等待，MyBot 会直接扫描 outputs 目录交付。不要把输入原件当作成果回传。",
            "最终回复必须适合微信发送，说明结果和验证，最多 1600 个中文字符，不输出内部推理或冗长日志。",
            "【最近对话】\n" + (context.strip()[-6_000:] or "[无]"),
            "【匹配的快捷能力】\n" + (abilities or "[无，按常规流程执行]"),
            "【任务附件】\n" + (attachments or "[无]"),
            "【本次任务】\n" + request,
        ))

    @staticmethod
    def _resume_prompt(request: str, context: str, abilities: str, attachments: str = "") -> str:
        return "\n\n".join((
            "继续处理同一微信会话的新任务，不重复已完成工作。任务上下文和匹配能力已经注入，不要调用 get_task_context 或 get_capabilities；若匹配到快捷能力，只读取对应能力的 SKILL.md、配方和脚本。",
            "需要直接读取或操作微信时，使用 $autowx-strategyd 和 autowx MCP；不得操作 MyBot 消息监听器，写操作必须有当前任务中的明确授权。",
            "只有用户在当前任务中明确要求时，才可以执行 git commit、git push、创建远程仓库、PR、Issue 或 Release 等外部写操作；GitHub 操作优先使用本机已认证的 gh CLI。",
            "如果任务需要用户刚发的附件，但【任务附件】显示没有输入文件，必须明确说明没有拿到本次原文件并停止。严禁搜索或复用 data/codex/tasks、旧 outputs、其他会话或历史任务中的文件来代替本次附件。",
            "【最近对话增量】\n" + (context.strip()[-3_000:] or "[无]"),
            "【匹配的快捷能力】\n" + (abilities or "[无]"),
            "【任务附件】\n" + (attachments or "[无]"),
            "【本次任务】\n" + request,
            "需要交付文件时，只能写入本次任务的 output_dir；调用 mybot.register_output_file 时只传相对文件名。登记失败或超时不要重试、不要等待，MyBot 会扫描 outputs 目录交付。",
            "完成并验证后，用不超过 1600 个中文字符给出可直接发送的结果。",
        ))

    @staticmethod
    def _attachment_prompt(attachments: tuple[IncomingAttachment, ...], output_dir: Path) -> str:
        lines = [f"成果输出目录：{output_dir.resolve()}"]
        if attachments:
            lines.append("输入文件（只读原件副本）：")
            lines.extend(
                f"- {item.name} | {item.kind} | {item.size} bytes | {item.path}"
                for item in attachments
            )
        else:
            lines.append("输入文件：[无]")
        return "\n".join(lines)

    @staticmethod
    def _task_output_files(task_root: Path) -> tuple[str, ...]:
        output_dir = (task_root / "outputs").resolve()
        manifest_path = task_root / "outputs.json"
        candidates: list[Path] = []
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = []
        if isinstance(manifest, list):
            for item in manifest:
                value = item.get("path") if isinstance(item, dict) else item
                if value:
                    candidates.append(Path(str(value)))
        try:
            candidates.extend(path for path in output_dir.rglob("*") if path.is_file())
        except OSError:
            pass
        results: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(output_dir)
                size = resolved.stat().st_size
            except (OSError, ValueError):
                continue
            key = os.path.normcase(str(resolved))
            if key in seen or size <= 0 or size > MAX_ATTACHMENT_BYTES:
                continue
            seen.add(key)
            results.append(str(resolved))
            if len(results) >= 10:
                break
        return tuple(results)

    @staticmethod
    def _distillation_prompt(
        *, request: str,
        result: str,
        candidate: Path,
        suggested_name: str,
        suggested_triggers: tuple[str, ...],
    ) -> str:
        return "\n\n".join((
            "把下面已完成任务沉淀成通用、离线可验证的 MyBot 快捷能力。当前目录就是唯一可写候选目录，不得访问或修改父目录。",
            "创建 SKILL.md、manifest.json、recipe.md、scripts/<能力>.py、tests/test_<能力>.py。SKILL.md 必须有只包含 name 和 description 的 YAML 前置元数据，并用简洁正文写清适用条件、输入契约、执行步骤和失败处理。脚本使用 argparse，输入必须参数化，不得写入联系人名、原始对话、绝对路径、密钥或实时结果。测试不得联网。",
            "manifest.json 格式：{\"reusable\":true,\"id\":\"lowercase-slug\",\"name\":\"名称\",\"description\":\"用途\",\"triggers\":[\"短语\"]}；name、description 和触发词必须与 SKILL.md 语义一致。",
            "recipe.md 记录适用条件、输入、命令、输出、依赖和失败处理。运行 compileall 与 unittest；只有测试通过才结束。",
            f"建议名称：{suggested_name or '[自行概括]'}",
            "建议触发词：" + ("、".join(suggested_triggers) or "[自行概括]"),
            "【原任务】\n" + request[:4_000],
            "【完成结果】\n" + result[:4_000],
            f"候选目录：{candidate}",
        ))

    def _conversation_lock(self, conversation: str) -> threading.Lock:
        key = conversation.strip()
        with self._locks_guard:
            return self._conversation_locks.setdefault(key, threading.Lock())

    @staticmethod
    def _thread_id(stdout: str) -> str:
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
                return event["thread_id"]
        return ""

    @staticmethod
    def _timeout_stage(exc: subprocess.TimeoutExpired) -> str:
        output = exc.stdout or exc.output or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        pending: dict[str, dict[str, Any]] = {}
        last_type = ""
        for line in str(output).splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            last_type = str(event.get("type", ""))
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", ""))
            if event.get("type") == "item.started" and item_id:
                pending[item_id] = item
            elif event.get("type") == "item.completed" and item_id:
                pending.pop(item_id, None)
        for item in reversed(tuple(pending.values())):
            if item.get("type") == "mcp_tool_call":
                return f"MCP {item.get('server', '?')}.{item.get('tool', '?')}"
            if item.get("type") == "command_execution":
                return "命令执行"
            if item.get("type"):
                return str(item["type"])
        return last_type

    @staticmethod
    def _resume_missing(completed: subprocess.CompletedProcess[str]) -> bool:
        value = (completed.stdout + "\n" + completed.stderr).casefold()
        return any(marker in value for marker in (
            "session not found", "thread not found", "no rollout found", "failed to load session",
        ))

    @staticmethod
    def _last_error(completed: subprocess.CompletedProcess[str]) -> str:
        lines = [line.strip() for line in (completed.stderr + "\n" + completed.stdout).splitlines() if line.strip()]
        return lines[-1][:500] if lines else f"退出码 {completed.returncode}"

    @staticmethod
    def _responses_url(base_url: str) -> str:
        value = base_url.rstrip("/")
        if value.endswith("/v1"):
            return value + "/responses"
        return value + "/v1/responses"

    @staticmethod
    def _startupinfo():
        if not hasattr(subprocess, "STARTUPINFO"):
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo

    def _environment(
        self,
        *,
        context_path: Path | None = None,
        task_token: str = "",
    ) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("OPENAI_API_KEY", None)
        environment.pop("OPENAI_BASE_URL", None)
        environment["CODEX_HOME"] = str(self._codex_home())
        existing_pythonpath = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = str(self.config.project_root) + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        if context_path is not None:
            environment["MYBOT_TASK_CONTEXT"] = str(context_path)
            environment["MYBOT_TASK_TOKEN"] = task_token
        return environment

    def _codex_home(self) -> Path:
        return (
            self.config.codex_home
            if self.config.codex_home is not None
            else self.config.project_root / "data" / "codex" / "home"
        ).resolve()
