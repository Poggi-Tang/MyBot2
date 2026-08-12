import json
import os
import subprocess
import sys
import tempfile
import uuid
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest import mock

from autowx_mcp.server import AutoWxService, handle_request
from mybot_ui.api import GatewayResult


def completed(value):
    future = Future()
    future.set_result(value)
    return future


class FakeGateway:
    def __init__(self, uri="ws://127.0.0.1:5177/ws"):
        self.uri = uri
        self.connected = False
        self.demo_mode = True
        self.clients = []
        self.calls = []
        self.closed = False
        self.next_result = GatewayResult(True, {"accepted": True})

    def connect(self, uri):
        self.uri = uri
        self.connected = True
        self.demo_mode = False
        self.clients = ["圆子"]
        return completed(GatewayResult(True, self.clients))

    def call(self, account, function, options, **kwargs):
        self.calls.append((account, function, options, kwargs))
        return completed(self.next_result)

    def close(self):
        self.closed = True
        self.connected = False


def call_tool(service, name, arguments=None, request_id=1):
    return handle_request({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }, service=service)


def tool_value(response):
    return json.loads(response["result"]["content"][0]["text"])


class AutoWxMcpTests(unittest.TestCase):
    def setUp(self):
        self.gateways = []

        def factory(**kwargs):
            gateway = FakeGateway(**kwargs)
            self.gateways.append(gateway)
            return gateway

        self.service = AutoWxService(factory)

    def tearDown(self):
        self.service.close()

    def test_initialize_and_standalone_tool_list(self):
        initialized = handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }, service=self.service)
        self.assertEqual("autowx", initialized["result"]["serverInfo"]["name"])
        listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, service=self.service)
        self.assertEqual({
            "list_functions",
            "get_function_schema",
            "plan_function_call",
            "get_connection_status",
            "connect_gateway",
            "disconnect_gateway",
            "call_sdk_function",
        }, {item["name"] for item in listed["result"]["tools"]})

    def test_catalog_search_and_schema(self):
        searched = tool_value(call_tool(self.service, "list_functions", {"query": "SendMessage"}))
        self.assertEqual(1, searched["total"])
        self.assertEqual("SendMessage", searched["functions"][0]["function"])
        schema = tool_value(call_tool(self.service, "get_function_schema", {"function": "SendMessage"}))
        self.assertEqual(["who", "message"], schema["required"])
        self.assertTrue(schema["requires_confirmation"])

    def test_unknown_and_incomplete_calls_are_rejected(self):
        unknown = call_tool(self.service, "plan_function_call", {
            "function": "NotInCatalog",
            "arguments": {},
        })
        missing = call_tool(self.service, "plan_function_call", {
            "function": "SendMessage",
            "arguments": {"who": "小明"},
        })
        self.assertIn("not allowlisted", unknown["error"]["message"])
        self.assertIn("message", missing["error"]["message"])

    def test_argument_types_are_validated_before_planning(self):
        invalid_string = call_tool(self.service, "plan_function_call", {
            "function": "SendMessage",
            "arguments": {"who": ["小明"], "message": "你好"},
        })
        invalid_list = call_tool(self.service, "plan_function_call", {
            "function": "SendFile",
            "arguments": {"who": "小明", "files": "private.txt"},
        })
        self.assertIn("who must be a string", invalid_string["error"]["message"])
        self.assertIn("files must be an array", invalid_list["error"]["message"])

    def test_listener_lifecycle_is_reserved_for_mybot(self):
        response = call_tool(self.service, "plan_function_call", {
            "function": "PauseMessageListener",
            "arguments": {},
        })
        self.assertIn("listener lifecycle is owned by MyBot", response["error"]["message"])

    def test_task_binding_limits_non_admin_to_originating_conversation(self):
        project_root = Path(__file__).resolve().parent.parent
        control_root = project_root / "data" / "codex" / "tmp"
        control_root.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        context_path = control_root / f"autowx-test-{token}.json"
        context_path.write_text(json.dumps({
            "task_token": token,
            "conversation": "芝士圆子",
            "privileged": False,
        }, ensure_ascii=False), encoding="utf-8")
        try:
            with mock.patch.dict(os.environ, {
                "MYBOT_TASK_CONTEXT": str(context_path),
                "MYBOT_TASK_TOKEN": token,
            }):
                allowed = call_tool(self.service, "plan_function_call", {
                    "function": "SendMessage",
                    "arguments": {"who": "芝士圆子", "message": "测试"},
                })
                other = call_tool(self.service, "plan_function_call", {
                    "function": "SendMessage",
                    "arguments": {"who": "其他会话", "message": "测试"},
                })
                account_wide = call_tool(self.service, "plan_function_call", {
                    "function": "GetAllConversations",
                    "arguments": {},
                })
            self.assertTrue(tool_value(allowed)["requires_confirmation"])
            self.assertIn("originating conversation", other["error"]["message"])
            self.assertIn("account-wide reads", account_wide["error"]["message"])
        finally:
            context_path.unlink(missing_ok=True)

    def test_read_only_call_does_not_require_confirmation(self):
        connected = call_tool(self.service, "connect_gateway")
        self.assertTrue(tool_value(connected)["connected"])
        planned = tool_value(call_tool(self.service, "plan_function_call", {
            "function": "GetAllConversations",
            "arguments": {},
        }))
        self.assertFalse(planned["requires_confirmation"])
        self.assertNotIn("confirmation_token", planned)
        called = tool_value(call_tool(self.service, "call_sdk_function", {
            "function": "GetAllConversations",
            "arguments": {},
        }))
        self.assertTrue(called["ok"])
        self.assertEqual(("圆子", "GetAllConversations", ""), self.gateways[0].calls[0][:3])

    def test_write_call_requires_exact_one_time_confirmation(self):
        call_tool(self.service, "connect_gateway")
        arguments = {"who": "小明", "message": "你好"}
        planned = tool_value(call_tool(self.service, "plan_function_call", {
            "function": "SendMessage",
            "arguments": arguments,
        }))
        token = planned["confirmation_token"]
        rejected = call_tool(self.service, "call_sdk_function", {
            "function": "SendMessage",
            "arguments": {"who": "小明", "message": "被修改"},
            "confirmation_token": token,
        })
        self.assertIn("does not match", rejected["error"]["message"])

        second_plan = tool_value(call_tool(self.service, "plan_function_call", {
            "function": "SendMessage",
            "arguments": arguments,
        }))
        accepted = tool_value(call_tool(self.service, "call_sdk_function", {
            "function": "SendMessage",
            "arguments": arguments,
            "confirmation_token": second_plan["confirmation_token"],
        }))
        self.assertTrue(accepted["ok"])
        repeated = call_tool(self.service, "call_sdk_function", {
            "function": "SendMessage",
            "arguments": arguments,
            "confirmation_token": second_plan["confirmation_token"],
        })
        self.assertIn("one-time confirmation", repeated["error"]["message"])
        self.assertEqual("小明", self.gateways[0].calls[0][2]["who"])

    def test_confirmation_expires_and_sensitive_preview_is_redacted(self):
        clock = [10.0]
        service = AutoWxService(lambda **kwargs: FakeGateway(**kwargs), monotonic=lambda: clock[0])
        try:
            plan = service.plan_function_call("SendStreamingVoiceMessage", {
                "who": "小明",
                "request": {"text": "你好", "api_key": "secret-value"},
            })
            self.assertEqual("<redacted>", plan["arguments_preview"]["request"]["api_key"])
            clock[0] += 121
            service.connect_gateway()
            with self.assertRaisesRegex(PermissionError, "one-time confirmation"):
                service.call_sdk_function(
                    "SendStreamingVoiceMessage",
                    {"who": "小明", "request": {"text": "你好", "api_key": "secret-value"}},
                    confirmation_token=plan["confirmation_token"],
                )
        finally:
            service.close()

    def test_file_plan_validates_path_without_exposing_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "private.txt"
            file_path.write_text("do-not-expose-this-content", encoding="utf-8")
            plan = self.service.plan_function_call("SendFile", {
                "who": "小明",
                "files": [str(file_path)],
            })
            serialized = json.dumps(plan, ensure_ascii=False)
            self.assertNotIn("do-not-expose-this-content", serialized)
            self.assertEqual("<redacted>", plan["gateway_options_preview"]["upload"])
            with self.assertRaisesRegex(ValueError, "does not exist"):
                self.service.plan_function_call("SendFile", {
                    "who": "小明",
                    "files": [str(file_path.with_name("missing.txt"))],
                })

    def test_gateway_failure_is_not_reported_as_success(self):
        call_tool(self.service, "connect_gateway")
        self.gateways[0].next_result = GatewayResult(False, error="SDK rejected the call")
        response = call_tool(self.service, "call_sdk_function", {
            "function": "GetAllConversations",
            "arguments": {},
        })
        self.assertIn("SDK rejected the call", response["error"]["message"])

    def test_sdk_results_redact_binary_media_and_local_paths(self):
        call_tool(self.service, "connect_gateway")
        self.gateways[0].next_result = GatewayResult(True, {
            "nick_name": "圆子",
            "upload": "base64-secret",
            "avator_path": "C:/private/avatar.png",
            "nested": {"image_base64_str": "more-secret"},
        })
        value = tool_value(call_tool(self.service, "call_sdk_function", {
            "function": "GetOwerInfo",
            "arguments": {},
        }))["value"]
        self.assertEqual("圆子", value["nick_name"])
        self.assertEqual("<redacted>", value["upload"])
        self.assertEqual("<redacted>", value["avator_path"])
        self.assertEqual("<redacted>", value["nested"]["image_base64_str"])

    def test_call_rejects_demo_or_disconnected_gateway(self):
        response = call_tool(self.service, "call_sdk_function", {
            "function": "GetAllConversations",
            "arguments": {},
        })
        self.assertIn("not connected", response["error"]["message"])

    def test_multiple_accounts_require_explicit_selection(self):
        call_tool(self.service, "connect_gateway")
        self.gateways[0].clients = ["账号一", "账号二"]
        rejected = call_tool(self.service, "call_sdk_function", {
            "function": "GetAllConversations",
            "arguments": {},
        })
        accepted = call_tool(self.service, "call_sdk_function", {
            "function": "GetAllConversations",
            "arguments": {},
            "account": "账号二",
        })
        self.assertIn("multiple accounts", rejected["error"]["message"])
        self.assertEqual("账号二", tool_value(accepted)["account"])

    def test_stdio_server_initializes_without_connecting_to_wechat(self):
        request = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        completed_process = subprocess.run(
            [sys.executable, "-m", "autowx_mcp.server"],
            input=json.dumps(request) + "\n",
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=5,
            env=environment,
            check=False,
        )
        self.assertEqual(0, completed_process.returncode, completed_process.stderr)
        response = json.loads(completed_process.stdout.strip())
        self.assertEqual("autowx", response["result"]["serverInfo"]["name"])

    def test_stdio_server_accepts_windows_utf8_bom(self):
        request = {"jsonrpc": "2.0", "id": 10, "method": "ping"}
        completed_process = subprocess.run(
            [sys.executable, "-m", "autowx_mcp.server"],
            input="\ufeff" + json.dumps(request) + "\n",
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(0, completed_process.returncode, completed_process.stderr)
        response = json.loads(completed_process.stdout.strip())
        self.assertEqual({}, response["result"])


if __name__ == "__main__":
    unittest.main()
