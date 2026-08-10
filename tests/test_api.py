import asyncio
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mybot_ui.api import DEFAULT_WEBSOCKET_MAX_MESSAGE_BYTES, Gateway, command_timeout


class _FakeWebSocket:
    def __init__(self) -> None:
        self.gateway = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Future()

    async def send(self, payload: str) -> None:
        request_id = json.loads(payload)["request_id"]
        self.gateway._pending[request_id].set_result('["圆子"]')

    async def close(self) -> None:
        return None


class GatewayConnectionTests(unittest.IsolatedAsyncioTestCase):
    def test_preview_command_uses_short_stall_detection_timeout(self):
        self.assertEqual(10, command_timeout("GetVisibleConversations"))
        self.assertEqual(5, command_timeout("PauseMessageListener"))
        self.assertEqual(180, command_timeout("ScanAllStickers"))
        self.assertEqual(30, command_timeout("SendMessage"))

    async def test_command_package_contains_server_enforced_expiry(self):
        packages = []
        gateway = Gateway.__new__(Gateway)
        gateway.demo_mode = False
        gateway.connected = True
        gateway._pending = {}

        class CallWebSocket:
            async def send(self, payload: str) -> None:
                outer = json.loads(payload)
                package = json.loads(outer["data"])
                packages.append(package)
                gateway._pending[package["request_id"]].set_result("true")

        gateway._ws = CallWebSocket()
        before_ms = int(time.time() * 1000)
        result = await gateway._call("account", "SendMessage", {"message": "hello"})

        self.assertTrue(result.ok)
        self.assertGreaterEqual(
            packages[0]["expires_at_unix_ms"],
            before_ms + command_timeout("SendMessage") * 1000,
        )

    async def test_connection_accepts_large_original_image_frames(self):
        websocket = _FakeWebSocket()
        gateway = Gateway.__new__(Gateway)
        gateway.uri = "ws://127.0.0.1:5177/ws"
        gateway.max_message_bytes = DEFAULT_WEBSOCKET_MAX_MESSAGE_BYTES
        gateway.demo_mode = True
        gateway.connected = False
        gateway.clients = ["演示账号"]
        gateway._ws = None
        gateway._pending = {}
        gateway._receiver = None
        gateway._listeners = []
        websocket.gateway = gateway
        connect = AsyncMock(return_value=websocket)

        with patch("mybot_ui.api.websockets", SimpleNamespace(connect=connect)):
            result = await gateway._connect()
            await gateway._disconnect()

        self.assertTrue(result.ok)
        self.assertEqual(["圆子"], result.value)
        self.assertEqual(
            DEFAULT_WEBSOCKET_MAX_MESSAGE_BYTES,
            connect.await_args.kwargs["max_size"],
        )


if __name__ == "__main__":
    unittest.main()
