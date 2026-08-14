import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from mybot_ui.auto_chat import ReplyAction, ReplyKind
from mybot_ui.controllers import RouteDecision
from mybot_ui.conversation_actions import ActionExecution, ConversationActionExecutor
from mybot_ui.realtime_tools import RealtimeToolRequest


class ConversationActionExecutorTests(unittest.TestCase):
    def setUp(self):
        self.executor = ConversationActionExecutor()
        self.incoming = SimpleNamespace(
            chat_title="芝士圆子",
            who="对方",
            content="测试消息",
        )
        self.host = MagicMock()
        self.host.submit_image_edit.return_value = "edit-future"
        self.host.submit_generated_image.return_value = "image-future"
        self.host.submit_realtime.return_value = "realtime-future"
        self.host.submit_model.return_value = "model-future"
        self.host.model_config.return_value = SimpleNamespace(system_prompt="基础人设")
        self.host.backup_model_config.return_value = "backup"
        self.host.model_timeout.return_value = 45
        self.host.resolved_persona_messages.return_value = (
            ["策略一"],
            ["规则一"],
            "芝士圆子",
        )
        self.context = [{"role": "system", "content": "基础人设"}]
        self.host.memory_context.return_value = self.context
        self.host.is_admin.return_value = True

    def execute(self, decision, *, image="", visual=""):
        self.executor.execute(
            self.host,
            ActionExecution(
                incoming=self.incoming,
                session=7,
                decision=decision,
                image_for_model=image,
                visual_context=visual,
            ),
        )

    def test_registered_routes_expose_all_direct_handlers(self):
        self.assertEqual(
            (
                "codex",
                "emoji",
                "image",
                "image_edit",
                "realtime",
                "security_denied",
                "sticker",
                "tap",
            ),
            self.executor.registered_routes,
        )

    def test_security_route_logs_and_sends_denial(self):
        self.execute(RouteDecision(
            "security_denied",
            ReplyAction(ReplyKind.TEXT),
            restricted_categories=("api_key",),
        ))

        self.host.event.assert_called_once_with(
            "security",
            "restricted_request_blocked",
            {
                "chat_title": "芝士圆子",
                "sender": "对方",
                "categories": ["api_key"],
            },
        )
        self.host.send_text.assert_called_once_with(
            self.incoming, 7, "这个内容只对管理员开放"
        )
        self.host.submit_model.assert_not_called()

    def test_image_edit_records_request_and_finishes_edited_image(self):
        self.execute(
            RouteDecision(
                "image_edit",
                ReplyAction(ReplyKind.TEXT),
                image_edit_request="把招牌改成 MyBot",
                image_edit_source="explicit",
            ),
            image="base64-image",
            visual="视觉上下文",
        )

        self.host.remember_pending_image_edit.assert_called_once_with(
            "芝士圆子", "把招牌改成 MyBot"
        )
        self.host.remember_user.assert_called_once_with(
            self.incoming, "base64-image", "视觉上下文"
        )
        self.host.submit_image_edit.assert_called_once_with(
            self.incoming, "把招牌改成 MyBot"
        )
        self.host.finish_image.assert_called_once_with(
            "edit-future", self.incoming, 7, mode="edited"
        )

    def test_realtime_route_preserves_requested_voice_action(self):
        action = ReplyAction(ReplyKind.VOICE)
        request = RealtimeToolRequest("weather", "上海徐汇天气")
        self.execute(RouteDecision("realtime", action, realtime_request=request))

        self.host.submit_realtime.assert_called_once_with(request)
        self.host.start_realtime.assert_called_once_with(
            "realtime-future", self.incoming, 7, action
        )

    def test_realtime_route_rejects_missing_request(self):
        with self.assertRaisesRegex(ValueError, "requires a request"):
            self.execute(RouteDecision("realtime", ReplyAction(ReplyKind.TEXT)))

    def test_codex_route_starts_codex_without_model_submission(self):
        self.execute(RouteDecision("codex", ReplyAction(ReplyKind.TEXT)))

        self.host.start_codex.assert_called_once_with(self.incoming, 7)
        self.host.submit_model.assert_not_called()

    def test_image_emoji_sticker_and_tap_dispatch_to_host(self):
        cases = (
            (ReplyKind.IMAGE, "画一朵花", "submit_generated_image"),
            (ReplyKind.EMOJI, "捂脸", "send_emoji"),
            (ReplyKind.STICKER, "可爱", "send_sticker"),
            (ReplyKind.TAP, "", "send_tap"),
        )

        for kind, argument, expected in cases:
            with self.subTest(kind=kind):
                host = MagicMock()
                host.submit_generated_image.return_value = "future"
                self.executor.execute(
                    host,
                    ActionExecution(
                        self.incoming,
                        7,
                        RouteDecision(kind.value, ReplyAction(kind, argument)),
                    ),
                )
                method = getattr(host, expected)
                if kind is ReplyKind.TAP:
                    method.assert_called_once_with(self.incoming, 7)
                elif kind is ReplyKind.IMAGE:
                    method.assert_called_once_with(argument)
                    host.finish_image.assert_called_once_with(
                        "future", self.incoming, 7, mode="generated"
                    )
                else:
                    method.assert_called_once_with(self.incoming, 7, argument)

    def test_text_model_adds_privacy_and_reply_mode_instructions(self):
        self.host.is_admin.return_value = False
        self.host.voice_enabled.return_value = True
        self.host.codex_enabled.return_value = True
        action = ReplyAction(ReplyKind.TEXT)

        self.execute(RouteDecision("text", action), visual="已缓存视觉语义")

        inserted = [item["content"] for item in self.context if item["role"] == "system"]
        self.assertTrue(any("当前发送者不是管理员" in item for item in inserted))
        self.assertTrue(any("回复方式" in item or "能力" in item for item in inserted))
        self.host.submit_model.assert_called_once_with(
            self.host.model_config.return_value,
            "backup",
            self.context,
            timeout=45,
        )
        self.host.finish_reply.assert_called_once_with(
            "model-future",
            self.incoming,
            7,
            action,
            visual_cache_hit=True,
        )

    def test_voice_and_reference_model_modes_add_specific_instruction(self):
        cases = (
            (ReplyKind.VOICE, "转换成微信语音消息"),
            (ReplyKind.REFERENCE, "真正引用对方当前这条微信消息"),
        )

        for kind, expected in cases:
            with self.subTest(kind=kind):
                self.context[:] = [{"role": "system", "content": "基础人设"}]
                self.host.reset_mock()
                self.host.model_config.return_value = SimpleNamespace(system_prompt="基础人设")
                self.host.backup_model_config.return_value = "backup"
                self.host.model_timeout.return_value = 45
                self.host.resolved_persona_messages.return_value = ([], [], "")
                self.host.memory_context.return_value = self.context
                self.host.is_admin.return_value = True
                self.host.submit_model.return_value = "model-future"
                action = ReplyAction(kind)

                self.execute(RouteDecision(kind.value, action))

                self.assertTrue(any(
                    expected in item["content"] for item in self.context
                ))
                self.host.finish_reply.assert_called_once_with(
                    "model-future",
                    self.incoming,
                    7,
                    action,
                    visual_cache_hit=False,
                )


if __name__ == "__main__":
    unittest.main()
