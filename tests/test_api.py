import asyncio
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mybot_ui.api import (
    DEFAULT_WEBSOCKET_MAX_MESSAGE_BYTES,
    Gateway,
    SdkCommandMutex,
    command_timeout,
)


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
        self.assertEqual(180, command_timeout("ScanAllStickers"))
        self.assertEqual(30, command_timeout("SendMessage"))

    async def test_command_package_contains_server_enforced_expiry(self):
        packages = []
        recorded = []
        gateway = Gateway.__new__(Gateway)
        gateway.demo_mode = False
        gateway.connected = True
        gateway._pending = {}
        gateway._outgoing_echo_journal = SimpleNamespace(
            record=lambda conversation, content, kind: recorded.append(
                (conversation, content, kind)
            )
        )

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
        self.assertEqual([("", "hello", "text")], recorded)

    async def test_commands_are_serialized_without_spending_timeout_in_queue(self):
        gateway = Gateway.__new__(Gateway)
        gateway.demo_mode = False
        gateway.connected = True
        gateway._pending = {}
        gateway._command_lock = None
        first_sent = asyncio.Event()
        release_first = asyncio.Event()
        sent = []

        class CallWebSocket:
            async def send(self, payload: str) -> None:
                outer = json.loads(payload)
                package = json.loads(outer["data"])
                sent.append(package["func_Name"])
                if package["func_Name"] == "first":
                    first_sent.set()
                    await release_first.wait()
                gateway._pending[package["request_id"]].set_result("true")

        gateway._ws = CallWebSocket()
        first = asyncio.create_task(gateway._call("account", "first", timeout_seconds=1))
        await first_sent.wait()
        second = asyncio.create_task(gateway._call("account", "second", timeout_seconds=1))
        await asyncio.sleep(0)
        self.assertEqual(["first"], sent)
        release_first.set()

        self.assertTrue((await first).ok)
        self.assertTrue((await second).ok)
        self.assertEqual(["first", "second"], sent)

    async def test_sdk_timeout_disconnects_before_next_queued_command(self):
        gateway = Gateway.__new__(Gateway)
        gateway.uri = "ws://127.0.0.1:5177/ws"
        gateway.demo_mode = False
        gateway.connected = True
        gateway._pending = {}
        gateway._command_lock = None
        gateway._receiver = None
        timeout_events = []
        gateway._listeners = [timeout_events.append]
        gateway._process_command_lock = SimpleNamespace(
            try_acquire=lambda: True,
            release=lambda: None,
        )
        timeout_started = asyncio.Event()
        release_timeout = asyncio.Event()
        sent = []

        class CallWebSocket:
            async def send(self, payload: str) -> None:
                outer = json.loads(payload)
                package = json.loads(outer["data"])
                sent.append(package["func_Name"])

            async def close(self) -> None:
                sent.append("closed")

        async def wait_until_released(_pending, *, timeout):
            timeout_started.set()
            await release_timeout.wait()
            raise asyncio.TimeoutError

        gateway._ws = CallWebSocket()
        with patch("mybot_ui.api.asyncio.wait_for", side_effect=wait_until_released):
            first = asyncio.create_task(
                gateway._call("account", "first", timeout_seconds=1)
            )
            await timeout_started.wait()
            second = asyncio.create_task(
                gateway._call("account", "second", timeout_seconds=1)
            )
            await asyncio.sleep(0)
            release_timeout.set()
            first_result, second_result = await asyncio.gather(first, second)

        self.assertFalse(first_result.ok)
        self.assertFalse(second_result.ok)
        self.assertFalse(gateway.connected)
        self.assertIsNone(gateway._ws)
        self.assertEqual(["first", "closed"], sent)
        self.assertIn("WebSocket Server", second_result.error)
        self.assertEqual("command_timeout", timeout_events[0]["type"])
        self.assertEqual("first", timeout_events[0]["function"])

    async def test_disconnect_failure_completes_pending_commands(self):
        gateway = Gateway.__new__(Gateway)
        gateway._pending = {}
        pending = asyncio.get_running_loop().create_future()
        gateway._pending["request"] = pending

        gateway._fail_pending(ConnectionError("断开"))

        with self.assertRaisesRegex(ConnectionError, "断开"):
            await pending
        self.assertEqual({}, gateway._pending)

    async def test_disconnected_real_gateway_does_not_report_demo_success(self):
        gateway = Gateway.__new__(Gateway)
        gateway.demo_mode = False
        gateway.connected = False
        gateway._ws = None
        gateway._pending = {}
        gateway._command_lock = None

        result = await gateway._call("account", "SendMessage")

        self.assertFalse(result.ok)
        self.assertEqual("WebSocket Server 未连接", result.error)

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

    async def test_shutdown_cancels_unfinished_private_loop_tasks(self):
        gateway = Gateway.__new__(Gateway)
        gateway.uri = "ws://127.0.0.1:5177/ws"
        gateway.connected = False
        gateway._receiver = None
        gateway._ws = None
        gateway._pending = {}
        started = asyncio.Event()

        async def unfinished() -> None:
            started.set()
            await asyncio.Future()

        task = asyncio.create_task(unfinished())
        await started.wait()

        await gateway._shutdown()

        self.assertTrue(task.cancelled())

    async def test_named_sdk_mutex_serializes_another_process(self):
        lock = SdkCommandMutex()
        lock.acquire()
        script = (
            "import time; from mybot_ui.api import SdkCommandMutex; "
            "m=SdkCommandMutex(); print('ready', flush=True); "
            "started=time.monotonic(); m.acquire(); "
            "print(time.monotonic()-started, flush=True); m.release(); m.close()"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            ready = await asyncio.to_thread(process.stdout.readline)
            self.assertEqual("ready", ready.strip())
            await asyncio.sleep(0.2)
            self.assertIsNone(process.poll())
        finally:
            lock.release()
            lock.close()
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(0, process.returncode, stderr)
        self.assertGreaterEqual(float(stdout.strip()), 0.1)


if __name__ == "__main__":
    unittest.main()
