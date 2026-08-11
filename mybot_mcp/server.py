from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mybot_ui.catalog import TOOLS
from mybot_ui.attachments import MAX_ATTACHMENT_BYTES
from mybot_ui.extension_abilities import ExtensionAbilityStore
from mybot_ui.operation_log import operations


PROTOCOL_VERSION = "2024-11-05"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _text_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    # Keep the stdio payload ASCII-only. The current Codex code-mode bridge can
    # leave non-ASCII MCP results pending even after the server has replied.
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_capabilities",
            "description": "List MyBot SDK functions and verified extension abilities.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "get_task_context",
            "description": "Read the fixed originating WeChat task context bound to this MCP process.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "report_progress",
            "description": "Append a short progress note for the current fixed task.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "maxLength": 500},
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "register_output_file",
            "description": "Register one completed file from this task's fixed output directory for delivery to the originating WeChat conversation.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "maxLength": 1000},
                    "description": {"type": "string", "maxLength": 300},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
        },
    ]


def _task_context() -> dict[str, Any]:
    expected = os.environ.get("MYBOT_TASK_TOKEN", "")
    path_value = os.environ.get("MYBOT_TASK_CONTEXT", "")
    if not expected or not path_value:
        raise PermissionError("task binding is unavailable")
    path = Path(path_value).resolve()
    control_root = (PROJECT_ROOT / "data" / "codex" / "tmp").resolve()
    path.relative_to(control_root)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("task_token") != expected:
        raise PermissionError("task context is invalid")
    return value


def _scan_output_files(output_dir: Path) -> tuple[Path, ...]:
    results: list[Path] = []
    try:
        candidates = output_dir.rglob("*")
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(output_dir)
                size = resolved.stat().st_size
            except (OSError, ValueError):
                continue
            if resolved.is_file() and 0 < size <= MAX_ATTACHMENT_BYTES:
                results.append(resolved)
                if len(results) >= 10:
                    break
    except OSError:
        pass
    return tuple(results)


def _repair_utf8_path(value: str) -> str:
    try:
        repaired = value.encode("gbk").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return ""
    return repaired if repaired != value else ""


def _resolve_output_file(output_dir: Path, value: str) -> tuple[Path | None, str, int]:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    candidate.resolve(strict=False).relative_to(output_dir)
    try:
        return candidate.resolve(strict=True), "requested_path", 0
    except FileNotFoundError:
        repaired_value = _repair_utf8_path(value)
        if repaired_value:
            repaired = Path(repaired_value)
            if not repaired.is_absolute():
                repaired = output_dir / repaired
            repaired.resolve(strict=False).relative_to(output_dir)
            try:
                return repaired.resolve(strict=True), "utf8_path_repair", 0
            except FileNotFoundError:
                pass
        scanned = _scan_output_files(output_dir)
        if len(scanned) == 1:
            return scanned[0], "outputs_scan", 1
        return None, "outputs_scan", len(scanned)


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "get_capabilities":
        abilities = ExtensionAbilityStore(PROJECT_ROOT / "extensions").list_abilities()
        categories: dict[str, int] = {}
        for tool in TOOLS:
            categories[tool.category] = categories.get(tool.category, 0) + 1
        return _text_result({
            "sdk_function_count": len(TOOLS),
            "sdk_categories": categories,
            "sdk_details_source": "mybot_ui/catalog.py",
            "verified_extension_abilities": [
                {
                    key: ability.get(key)
                    for key in ("id", "name", "description", "triggers", "recipe", "scripts")
                }
                for ability in abilities
            ],
        })
    if name == "get_task_context":
        context = _task_context()
        return _text_result({key: value for key, value in context.items() if key != "task_token"})
    if name == "report_progress":
        context = _task_context()
        message = str(arguments.get("message", "")).strip()[:500]
        if not message:
            raise ValueError("progress message is empty")
        path = PROJECT_ROOT / "data" / "codex" / "progress.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "task_id": context.get("task_id"),
                "conversation": context.get("conversation"),
                "message": message,
            }, ensure_ascii=False) + "\n")
        return _text_result({"recorded": True, "task_id": context.get("task_id")})
    if name == "register_output_file":
        context = _task_context()
        task_id = str(context.get("task_id", "")).strip()
        if not task_id or not re_fullmatch_task_id(task_id):
            raise PermissionError("task id is invalid")
        expected_output = (PROJECT_ROOT / "data" / "codex" / "tasks" / task_id / "outputs").resolve()
        configured_output = Path(str(context.get("output_dir", ""))).resolve()
        if configured_output != expected_output:
            raise PermissionError("output directory binding is invalid")
        value = str(arguments.get("path", "")).strip()
        if not value:
            raise ValueError("output path is empty")
        resolved, resolution, scanned_count = _resolve_output_file(configured_output, value)
        if resolved is None:
            return _text_result({
                "registered": False,
                "task_id": task_id,
                "delivery_fallback": "outputs_scan",
                "output_file_count": scanned_count,
                "retry": False,
            })
        resolved.relative_to(configured_output)
        if not resolved.is_file():
            raise ValueError("output path is not a file")
        size = resolved.stat().st_size
        if size <= 0 or size > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"output file size must be between 1 and {MAX_ATTACHMENT_BYTES} bytes")
        manifest_path = configured_output.parent / "outputs.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = []
        if not isinstance(manifest, list):
            manifest = []
        normalized = os.path.normcase(str(resolved))
        manifest = [
            item for item in manifest
            if isinstance(item, dict) and os.path.normcase(str(item.get("path", ""))) != normalized
        ]
        if len(manifest) >= 10:
            raise ValueError("a task can register at most 10 output files")
        manifest.append({
            "path": str(resolved),
            "name": resolved.name,
            "size": size,
            "description": str(arguments.get("description", "")).strip()[:300],
            "resolution": resolution,
        })
        temporary = manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, manifest_path)
        return _text_result({
            "registered": True,
            "task_id": task_id,
            "name": resolved.name,
            "size": size,
            "resolution": resolution,
        })
    raise KeyError(f"unknown tool: {name}")


def re_fullmatch_task_id(value: str) -> bool:
    return len(value) <= 64 and all(character.isalnum() or character in "-_" for character in value)


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    try:
        if method == "initialize":
            result = {
                "protocolVersion": request.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mybot-wechat", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": _tools()}
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = str(params.get("name", ""))
            arguments = params.get("arguments", {}) or {}
            span = operations.start("mcp", "mcp_tool_call", details={
                "tool": tool_name,
                "argument_names": sorted(arguments) if isinstance(arguments, dict) else [],
            })
            try:
                result = _call_tool(tool_name, arguments)
                operations.finish(span, success=True, result={"tool": tool_name})
            except Exception as exc:
                operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
                raise
        elif method == "ping":
            result = {}
        else:
            raise KeyError(f"unknown method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": f"{type(exc).__name__}: {exc}"},
        }


def main() -> None:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"{type(exc).__name__}: {exc}"},
            }, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
