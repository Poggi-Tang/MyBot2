from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from mybot_ui.api import Gateway, GatewayResult, command_timeout
from mybot_ui.catalog import TOOL_MAP, TOOLS, ToolSpec, build_options, missing_arguments
from mybot_ui.operation_log import operations


PROTOCOL_VERSION = "2024-11-05"
SERVER_VERSION = "0.1.0"
DEFAULT_GATEWAY_URL = "ws://127.0.0.1:5177/ws"
CONFIRMATION_TTL_SECONDS = 120
READ_ONLY_RISK = "只读"
LISTENER_OWNER_FUNCTIONS = {
    "AddFriendRequestAutoAcceptListener",
    "PauseNewFriendListener",
    "ResumeNewFriendListener",
    "AddGroupSystemMessageListener",
}
STRING_ARGUMENTS = {
    "who", "message", "emoji", "sticker", "file_path", "group_name",
    "old_group_name", "new_group_name", "nick_name", "group_notice",
    "content", "fetch_date", "navigation_type", "icon", "first_who",
    "new_memo", "start_time", "end_time", "endpoint", "f_type",
}
LIST_ARGUMENTS = {
    "files", "images", "members", "partners", "to", "friends", "ranges",
    "at_users", "labels",
}
BOOLEAN_ARGUMENTS = {"with_avatar", "setting"}


def _text_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _function_metadata(spec: ToolSpec) -> dict[str, Any]:
    return {
        "function": spec.function,
        "action_type": spec.action_type,
        "name": spec.name,
        "category": spec.category,
        "description": spec.description,
        "risk": spec.risk,
        "required": list(spec.required),
        "test_kind": spec.test_kind,
        "requires_confirmation": spec.risk != READ_ONLY_RISK,
    }


def _call_digest(function: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"function": function, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _redact_options(value: Any, key: str = "") -> Any:
    normalized_key = key.lower()
    if normalized_key in {
        "upload", "api_key", "token", "authorization", "image_base64_str",
        "image_base64", "avatar_path", "avator_path", "file_path", "image_file",
    }:
        return "<redacted>"
    if isinstance(value, dict):
        return {str(name): _redact_options(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact_options(item) for item in value]
    return value


def _upload_path(value: Any) -> str:
    path = Path(str(value or ""))
    if not path.is_file():
        raise ValueError(f"upload file does not exist: {path}")
    return str(path)


def _preview_options(function: str, arguments: dict[str, Any]) -> Any:
    """Serialize without reading file contents before execution is approved."""
    if function == "SendFile":
        files = [_upload_path(path) for path in arguments.get("files", [])]
        return {
            "who": arguments["who"],
            "files": json.dumps(files, ensure_ascii=False),
            "upload": "<redacted>",
        }
    if function == "SendVoiceMessage":
        file_path = _upload_path(arguments["file_path"])
        return {"who": arguments["who"], "filePath": file_path, "upload": "<redacted>"}
    if function == "AddMoments":
        images = [_upload_path(path) for path in arguments.get("images", [])]
        return {
            "image_files": json.dumps(images, ensure_ascii=False),
            "content": arguments["content"],
            "upload": "<redacted>",
            "options": json.dumps({"at_usrs": [], "labels": [], "is_close_moments": True}),
        }
    return _redact_options(build_options(function, arguments))


@dataclass(frozen=True)
class PendingConfirmation:
    digest: str
    expires_at: float


class AutoWxService:
    """Own one explicit connection to the local WeChat SDK gateway."""

    def __init__(
        self,
        gateway_factory: Callable[..., Gateway] = Gateway,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._gateway_factory = gateway_factory
        self._monotonic = monotonic
        self._gateway: Gateway | None = None
        self._confirmations: dict[str, PendingConfirmation] = {}

    @property
    def gateway_url(self) -> str:
        if self._gateway is not None:
            return self._gateway.uri
        return os.environ.get("AUTOWX_GATEWAY_URL", DEFAULT_GATEWAY_URL).strip() or DEFAULT_GATEWAY_URL

    def close(self) -> None:
        if self._gateway is not None:
            self._gateway.close()
            self._gateway = None
        self._confirmations.clear()

    def list_functions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip().casefold()
        category = str(arguments.get("category", "")).strip().casefold()
        risk = str(arguments.get("risk", "")).strip().casefold()
        try:
            limit = min(100, max(1, int(arguments.get("limit", 25))))
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        matches: list[ToolSpec] = []
        for spec in TOOLS:
            haystack = " ".join((spec.function, spec.name, spec.category, spec.description)).casefold()
            if query and query not in haystack:
                continue
            if category and category != spec.category.casefold():
                continue
            if risk and risk != spec.risk.casefold():
                continue
            matches.append(spec)
        return {
            "total": len(matches),
            "returned": min(limit, len(matches)),
            "functions": [_function_metadata(spec) for spec in matches[:limit]],
        }

    def get_function_schema(self, function: str) -> dict[str, Any]:
        spec = self._get_spec(function)
        metadata = _function_metadata(spec)
        metadata["arguments_schema"] = {
            "type": "object",
            "properties": {
                name: self._argument_schema(name)
                for name in spec.required
            },
            "required": list(spec.required),
            "additionalProperties": True,
        }
        return metadata

    def plan_function_call(self, function: str, arguments: dict[str, Any]) -> dict[str, Any]:
        spec = self._validate_call(function, arguments)
        result = {
            "function": function,
            "action_type": spec.action_type,
            "risk": spec.risk,
            "test_kind": spec.test_kind,
            "arguments_preview": _redact_options(arguments),
            "gateway_options_preview": _preview_options(function, arguments),
            "requires_confirmation": spec.risk != READ_ONLY_RISK,
        }
        if spec.risk != READ_ONLY_RISK:
            self._prune_confirmations()
            token = secrets.token_urlsafe(24)
            self._confirmations[token] = PendingConfirmation(
                _call_digest(function, arguments),
                self._monotonic() + CONFIRMATION_TTL_SECONDS,
            )
            result.update({
                "confirmation_token": token,
                "confirmation_expires_in_seconds": CONFIRMATION_TTL_SECONDS,
                "confirmation_instruction": (
                    "Obtain explicit user approval for this exact call, then pass this one-time token "
                    "to call_sdk_function without changing the arguments."
                ),
            })
        return result

    def connection_status(self) -> dict[str, Any]:
        gateway = self._gateway
        return {
            "gateway_url": self.gateway_url,
            "connected": bool(gateway and gateway.connected and not gateway.demo_mode),
            "demo_mode": True if gateway is None else bool(gateway.demo_mode),
            "accounts": [] if gateway is None else list(gateway.clients),
        }

    def connect_gateway(self, gateway_url: str = "") -> dict[str, Any]:
        uri = gateway_url.strip() or self.gateway_url
        parsed = urlparse(uri)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
            raise ValueError("gateway_url must be a ws:// or wss:// URL")
        if self._gateway is None:
            self._gateway = self._gateway_factory(uri=uri)
        result = self._gateway.connect(uri).result(timeout=8)
        if not isinstance(result, GatewayResult) or not result.ok:
            error = result.error if isinstance(result, GatewayResult) else "invalid gateway response"
            raise ConnectionError(error or "gateway connection failed")
        status = self.connection_status()
        if not status["connected"]:
            raise ConnectionError("gateway entered demo mode instead of establishing a real connection")
        return status

    def disconnect_gateway(self) -> dict[str, Any]:
        self.close()
        return self.connection_status()

    def call_sdk_function(
        self,
        function: str,
        arguments: dict[str, Any],
        *,
        account: str = "",
        confirmation_token: str = "",
    ) -> dict[str, Any]:
        spec = self._validate_call(function, arguments)
        gateway = self._gateway
        if gateway is None or not gateway.connected or gateway.demo_mode:
            raise ConnectionError("autowx is not connected to a real WeChat SDK gateway")
        selected_account = self._select_account(account, gateway.clients)
        options = build_options(function, arguments)
        if spec.risk != READ_ONLY_RISK:
            self._consume_confirmation(function, arguments, confirmation_token)
        result = gateway.call(
            selected_account,
            function,
            options,
            timeout_seconds=command_timeout(function),
        ).result(timeout=command_timeout(function) + 5)
        if not isinstance(result, GatewayResult):
            raise RuntimeError("gateway returned an invalid result")
        if not result.ok:
            raise RuntimeError(result.error or f"{function} failed")
        return {
            "ok": True,
            "account": selected_account,
            "function": function,
            "action_type": spec.action_type,
            "risk": spec.risk,
            "value": _redact_options(result.value),
        }

    @staticmethod
    def _get_spec(function: str) -> ToolSpec:
        normalized = str(function or "").strip()
        spec = TOOL_MAP.get(normalized)
        if spec is None:
            raise KeyError(f"SDK function is not allowlisted: {normalized}")
        return spec

    def _validate_call(self, function: str, arguments: dict[str, Any]) -> ToolSpec:
        spec = self._get_spec(function)
        if function in LISTENER_OWNER_FUNCTIONS:
            raise PermissionError(
                "listener lifecycle is owned by MyBot and is unavailable through autowx"
            )
        if not isinstance(arguments, dict):
            raise TypeError("arguments must be an object")
        missing = missing_arguments(function, arguments)
        if missing:
            raise ValueError(f"missing required arguments: {', '.join(missing)}")
        for name, value in arguments.items():
            self._validate_argument_type(name, value)
        self._validate_task_scope(spec, arguments)
        return spec

    @staticmethod
    def _argument_schema(name: str) -> dict[str, Any]:
        if name in STRING_ARGUMENTS:
            return {"type": "string", "minLength": 1}
        if name in LIST_ARGUMENTS:
            return {"type": "array", "minItems": 1}
        if name in BOOLEAN_ARGUMENTS:
            return {"type": "boolean"}
        if name == "request":
            return {"type": ["object", "string"]}
        return {}

    @staticmethod
    def _validate_argument_type(name: str, value: Any) -> None:
        if name in STRING_ARGUMENTS and not isinstance(value, str):
            raise TypeError(f"argument {name} must be a string")
        if name in LIST_ARGUMENTS and not isinstance(value, list):
            raise TypeError(f"argument {name} must be an array")
        if name in BOOLEAN_ARGUMENTS and not isinstance(value, bool):
            raise TypeError(f"argument {name} must be a boolean")
        if name == "request" and not isinstance(value, (dict, str)):
            raise TypeError("argument request must be an object or string")

    @staticmethod
    def _task_context() -> dict[str, Any] | None:
        context_path = os.environ.get("MYBOT_TASK_CONTEXT", "").strip()
        expected_token = os.environ.get("MYBOT_TASK_TOKEN", "").strip()
        if not context_path and not expected_token:
            return None
        if not context_path or not expected_token:
            raise PermissionError("MyBot task binding is incomplete")
        path = Path(context_path).resolve()
        control_root = (Path(__file__).resolve().parent.parent / "data" / "codex" / "tmp").resolve()
        path.relative_to(control_root)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("task_token") != expected_token:
            raise PermissionError("MyBot task binding is invalid")
        return value

    def _validate_task_scope(self, spec: ToolSpec, arguments: dict[str, Any]) -> None:
        context = self._task_context()
        if context is None or bool(context.get("privileged")):
            return
        conversation = str(context.get("conversation", "")).strip()
        if not conversation:
            raise PermissionError("originating conversation is unavailable")
        targets: list[str] = []
        if isinstance(arguments.get("who"), str):
            targets.append(arguments["who"].strip())
        if isinstance(arguments.get("group_name"), str):
            targets.append(arguments["group_name"].strip())
        if isinstance(arguments.get("old_group_name"), str):
            targets.append(arguments["old_group_name"].strip())
        for name in ("to",):
            if isinstance(arguments.get(name), list):
                targets.extend(str(value).strip() for value in arguments[name])
        if any(target and target != conversation for target in targets):
            raise PermissionError(
                "non-administrator autowx tasks are limited to the originating conversation"
            )
        if spec.risk != READ_ONLY_RISK and not targets:
            raise PermissionError(
                "non-administrator autowx writes require the originating conversation as target"
            )
        if spec.risk == READ_ONLY_RISK and not targets and spec.function not in {
            "GetTitle", "GetOnlyTitle", "GetHandler", "GetProcessId",
        }:
            raise PermissionError(
                "non-administrator autowx tasks cannot perform account-wide reads"
            )

    def _consume_confirmation(
        self,
        function: str,
        arguments: dict[str, Any],
        token: str,
    ) -> None:
        self._prune_confirmations()
        pending = self._confirmations.pop(str(token or ""), None)
        if pending is None:
            raise PermissionError("a valid one-time confirmation token is required")
        if not secrets.compare_digest(pending.digest, _call_digest(function, arguments)):
            raise PermissionError("confirmation token does not match this exact call")

    def _prune_confirmations(self) -> None:
        now = self._monotonic()
        self._confirmations = {
            token: pending
            for token, pending in self._confirmations.items()
            if pending.expires_at > now
        }

    @staticmethod
    def _select_account(requested: str, clients: list[str]) -> str:
        requested = str(requested or os.environ.get("AUTOWX_ACCOUNT", "")).strip()
        available = [str(client).strip() for client in clients if str(client).strip()]
        if requested:
            if requested not in available:
                raise ValueError(f"account is not connected: {requested}")
            return requested
        if len(available) == 1:
            return available[0]
        if not available:
            raise ConnectionError("the gateway has no connected WeChat accounts")
        raise ValueError("multiple accounts are connected; account is required")


def _tools() -> list[dict[str, Any]]:
    function_property = {"type": "string", "description": "Exact allowlisted SDK function name."}
    arguments_property = {"type": "object", "description": "Agent-friendly SDK arguments."}
    return [
        {
            "name": "list_functions",
            "description": "Search the allowlisted WeChat SDK function catalog.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {"type": "string"},
                    "risk": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
                },
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "get_function_schema",
            "description": "Read required arguments, risk, and test classification for one SDK function.",
            "inputSchema": {
                "type": "object",
                "properties": {"function": function_property},
                "required": ["function"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "plan_function_call",
            "description": "Validate and preview one SDK call. Returns a short-lived token for non-read-only calls.",
            "inputSchema": {
                "type": "object",
                "properties": {"function": function_property, "arguments": arguments_property},
                "required": ["function", "arguments"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "get_connection_status",
            "description": "Read the standalone autowx gateway connection and available accounts.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "connect_gateway",
            "description": "Connect this MCP process to an explicitly configured WeChat SDK WebSocket gateway.",
            "inputSchema": {
                "type": "object",
                "properties": {"gateway_url": {"type": "string", "default": DEFAULT_GATEWAY_URL}},
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
        },
        {
            "name": "disconnect_gateway",
            "description": "Close the standalone autowx gateway connection.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "call_sdk_function",
            "description": "Execute one allowlisted SDK function against a real connected gateway.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "function": function_property,
                    "arguments": arguments_property,
                    "account": {"type": "string"},
                    "confirmation_token": {"type": "string"},
                },
                "required": ["function", "arguments"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
        },
    ]


_DEFAULT_SERVICE = AutoWxService()


def _call_tool(name: str, arguments: dict[str, Any], service: AutoWxService) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise TypeError("tool arguments must be an object")
    if name == "list_functions":
        return _text_result(service.list_functions(arguments))
    if name == "get_function_schema":
        return _text_result(service.get_function_schema(str(arguments.get("function", ""))))
    if name == "plan_function_call":
        return _text_result(service.plan_function_call(
            str(arguments.get("function", "")),
            arguments.get("arguments", {}),
        ))
    if name == "get_connection_status":
        return _text_result(service.connection_status())
    if name == "connect_gateway":
        return _text_result(service.connect_gateway(str(arguments.get("gateway_url", ""))))
    if name == "disconnect_gateway":
        return _text_result(service.disconnect_gateway())
    if name == "call_sdk_function":
        return _text_result(service.call_sdk_function(
            str(arguments.get("function", "")),
            arguments.get("arguments", {}),
            account=str(arguments.get("account", "")),
            confirmation_token=str(arguments.get("confirmation_token", "")),
        ))
    raise KeyError(f"unknown tool: {name}")


def handle_request(
    request: dict[str, Any],
    *,
    service: AutoWxService | None = None,
) -> dict[str, Any] | None:
    service = service or _DEFAULT_SERVICE
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    try:
        if method == "initialize":
            result = {
                "protocolVersion": request.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "autowx", "version": SERVER_VERSION},
            }
        elif method == "tools/list":
            result = {"tools": _tools()}
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = str(params.get("name", ""))
            tool_arguments = params.get("arguments", {}) or {}
            span = operations.start("autowx_mcp", "tool_call", details={
                "tool": tool_name,
                "argument_names": sorted(tool_arguments) if isinstance(tool_arguments, dict) else [],
            })
            try:
                result = _call_tool(tool_name, tool_arguments, service)
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
    service = AutoWxService()
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line.lstrip("\ufeff"))
                response = handle_request(request, service=service)
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
    finally:
        service.close()


if __name__ == "__main__":
    main()
