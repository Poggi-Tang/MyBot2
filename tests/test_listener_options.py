import unittest
from pathlib import Path

from mybot_ui.catalog import TOOL_MAP


class ListenerOptionsTests(unittest.TestCase):
    def test_legacy_dotnet_message_listener_is_not_catalogued(self) -> None:
        legacy = {
            "AddMessageListener",
            "PauseMessageListener",
            "ResumeMessageListener",
            "AddListeningFriend",
            "RemoveListeningFriend",
        }
        self.assertTrue(legacy.isdisjoint(TOOL_MAP))

    def test_server_has_no_dotnet_message_listener_or_quote_entry(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        relative = Path("WeChatAuto4_X/WebSocketServer/Server/WebSockets/MessageHandler.cs")
        candidates = (
            project_root / "sdk" / relative,
            project_root.parent / "wechatautosdk" / relative,
        )
        handler = next((path for path in candidates if path.is_file()), None)
        self.assertIsNotNone(handler, "MessageHandler.cs is missing from both supported layouts")
        source = handler.read_text(encoding="utf-8")
        for function in (
            "AddMessageListener",
            "PauseMessageListener",
            "ResumeMessageListener",
            "AddListeningFriend",
            "RemoveListeningFriend",
        ):
            self.assertNotIn(f'case "{function}"', source)
        self.assertNotIn("DeserializeObject<ChatRefer>", source)

    def test_autowx_and_mybot_share_the_fixed_gateway_server(self) -> None:
        from autowx_mcp.server import DEFAULT_GATEWAY_URL

        self.assertEqual("ws://127.0.0.1:5177/ws", DEFAULT_GATEWAY_URL)


if __name__ == "__main__":
    unittest.main()
