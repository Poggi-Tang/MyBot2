from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .operation_log import operations

try:
    import websockets
except ImportError:  # pragma: no cover - dependency is declared in requirements
    websockets = None


DEFAULT_WEBSOCKET_MAX_MESSAGE_BYTES = 64 * 1024 * 1024


def command_timeout(function: str) -> int:
    if function == "ScanAllStickers":
        return 180
    if function == "GetVisibleConversations":
        return 10
    if function == "PauseMessageListener":
        return 5
    return 30


@dataclass
class GatewayResult:
    ok: bool
    value: Any = None
    error: str = ""


class Gateway:
    """Thread-safe facade for the WeChatAuto4_X WebSocket protocol.

    The GUI never waits on an asyncio loop. Calls are scheduled on a private
    thread and returned through a Future, which keeps the Qt event loop smooth.
    """

    def __init__(
        self,
        uri: str = "ws://127.0.0.1:5177/ws",
        *,
        max_message_bytes: int = DEFAULT_WEBSOCKET_MAX_MESSAGE_BYTES,
    ) -> None:
        self.uri = uri
        self.max_message_bytes = max(1024 * 1024, int(max_message_bytes))
        self.demo_mode = True
        self.connected = False
        self.clients: list[str] = ["演示账号"]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._ready = threading.Event()
        self._ws = None
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._receiver = None
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._thread.start()
        self._ready.wait(timeout=2)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def close(self) -> None:
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)
            future.result(timeout=2)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def add_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(callback)

    def submit(self, coroutine) -> Future:
        if not self._loop:
            future = Future()
            future.set_exception(RuntimeError("asyncio loop is not ready"))
            return future
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def connect(self, uri: str | None = None) -> Future:
        if uri:
            self.uri = uri
        return self.submit(self._connect())

    def disconnect(self) -> Future:
        return self.submit(self._disconnect())

    def call(self, account: str, function: str, options: Any = "") -> Future:
        return self.submit(self._call(account, function, options))

    async def _connect(self) -> GatewayResult:
        request_id = uuid.uuid4().hex
        span = operations.start("gateway", "Connect", operation_id=request_id, details={"uri": self.uri})
        if websockets is None:
            self.demo_mode = True
            self.connected = False
            result = GatewayResult(False, error="未安装 websockets，已切换演示模式")
            operations.finish(span, success=False, error=result.error)
            return result
        try:
            self._ws = await websockets.connect(
                self.uri,
                open_timeout=3,
                close_timeout=2,
                max_size=self.max_message_bytes,
            )
            self._receiver = asyncio.create_task(self._recv_loop())
            pending = asyncio.get_running_loop().create_future()
            self._pending[request_id] = pending
            await self._ws.send(json.dumps({"type": "global", "data": "", "request_id": request_id}))
            raw = await asyncio.wait_for(pending, timeout=5)
            self.clients = json.loads(raw) if isinstance(raw, str) else list(raw)
            self.clients = self.clients or ["未识别账号"]
            self.demo_mode = False
            self.connected = True
            result = GatewayResult(True, self.clients)
            operations.finish(span, success=True, result=self.clients)
            return result
        except Exception as exc:
            await self._disconnect()
            self.demo_mode = True
            self.connected = False
            result = GatewayResult(False, self.clients, f"连接失败：{exc}")
            operations.finish(span, success=False, result=self.clients, error=result.error)
            return result

    async def _disconnect(self) -> GatewayResult:
        span = operations.start("gateway", "Disconnect", details={"uri": self.uri})
        self.connected = False
        try:
            if self._receiver:
                self._receiver.cancel()
                try:
                    await self._receiver
                except asyncio.CancelledError:
                    pass
                self._receiver = None
            if self._ws:
                await self._ws.close()
                self._ws = None
            operations.finish(span, success=True)
            return GatewayResult(True)
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    async def _recv_loop(self) -> None:
        try:
            async for payload in self._ws:
                response = json.loads(payload)
                request_id = response.get("request_id")
                if response.get("type") == "ping":
                    await self._ws.send(json.dumps({"type": "pong", "data": "", "request_id": uuid.uuid4().hex}))
                    continue
                pending = self._pending.pop(request_id, None)
                if pending and not pending.done():
                    if response.get("type") == "error":
                        pending.set_exception(RuntimeError(response.get("data", "服务端错误")))
                    else:
                        pending.set_result(response.get("data", ""))
                    continue
                for listener in self._listeners:
                    listener(response)
                operations.event("gateway", "WebSocketEvent", response)
        except Exception as exc:
            operations.event("gateway", "WebSocketReceiverError", {"error": f"{type(exc).__name__}: {exc}"})
            for listener in self._listeners:
                listener({"type": "connection_error", "data": str(exc)})

    async def _call(self, account: str, function: str, options: Any = "") -> GatewayResult:
        request_id = uuid.uuid4().hex
        timeout_seconds = command_timeout(function)
        span = operations.start(
            "gateway",
            function,
            operation_id=request_id,
            details={"account": account, "options": options, "timeout_seconds": timeout_seconds},
        )
        if self.demo_mode or not self.connected:
            value = self._demo_value(function, options)
            operations.finish(span, success=True, result=value, details={"demo_mode": True})
            return GatewayResult(True, value)
        package = {
            "request_id": request_id,
            "func_Name": function,
            "options": options if isinstance(options, str) else json.dumps(options, ensure_ascii=False),
            "from_wechat": account,
            "expires_at_unix_ms": int((time.time() + timeout_seconds) * 1000),
        }
        pending = asyncio.get_running_loop().create_future()
        self._pending[request_id] = pending
        await self._ws.send(json.dumps({"type": "command", "data": json.dumps(package, ensure_ascii=False), "request_id": request_id}))
        try:
            value = await asyncio.wait_for(pending, timeout=timeout_seconds)
            if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
                result = GatewayResult(True, value.strip().lower() == "true")
                operations.finish(span, success=True, result=result.value)
                return result
            try:
                result = GatewayResult(True, json.loads(value))
            except (TypeError, json.JSONDecodeError):
                result = GatewayResult(True, value)
            operations.finish(span, success=True, result=result.value)
            return result
        except Exception as exc:
            self._pending.pop(request_id, None)
            result = GatewayResult(False, error=str(exc) or type(exc).__name__)
            operations.finish(span, success=False, error=result.error)
            return result

    def _demo_value(self, function: str, options: Any) -> Any:
        if function in {"GetAllConversations", "GetVisibleConversationTitles"}:
            return ["产品讨论群", "文件传输助手", "林然", "AI 自动化测试群"]
        if function == "GetAllChatGroups":
            return ["产品讨论群", "AI 自动化测试群"]
        if function == "GetVisibleConversations":
            return [{"title": name, "unreadCount": count, "avatar": ""} for name, count in [("产品讨论群", 3), ("林然", 0), ("文件传输助手", 1)]]
        if function in {"GetAllFriendNames", "GetAllFriends"}:
            names = ["林然", "Alex", "小陈", "产品讨论群", "AI 自动化测试群"]
            return names if function == "GetAllFriendNames" else [{"nickName": name, "wxid": f"wxid_{i:03d}", "remark": ""} for i, name in enumerate(names)]
        if function in {"GetChatHistory_Current_Window", "GetChatHistory_Who"}:
            return [{"sender": "林然", "content": "演示模式：连接服务端后这里会显示真实消息。", "time": "10:24", "messageType": "Text"}]
        if function == "GetChatGroupMemberList":
            return ["林然", "Alex", "小陈", "产品讨论群管理员"]
        if function == "GetTitle":
            return {"title": "产品讨论群", "chatType": "Group", "canTalk": True}
        if function == "GetOwerInfo":
            return {"nickName": "演示账号", "wxid": "demo_wxid", "avatorPath": "", "upload": ""}
        if function in {"IsOwnerChatGroup", "SearchFriend", "LocateConversation", "SetDoNotDisturb", "SetTopMost", "TapWho", "CreateOwnerChatGroup", "InviteChatGroupMember", "RemoveFriend"}:
            return True
        return {"success": True, "message": f"演示模式已执行 {function}"}


def encode_upload(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("utf-8")
