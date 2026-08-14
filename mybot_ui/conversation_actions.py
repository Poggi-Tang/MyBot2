from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .auto_chat import ReplyAction, ReplyKind, model_reply_mode_instruction
from .catalog import model_sdk_tool_catalog
from .controllers import RouteDecision


class ConversationActionHost(Protocol):
    def event(self, domain: str, name: str, details: dict[str, Any]) -> None: ...
    def update_status(self, incoming: Any, *, stage: str, kind: str) -> None: ...
    def remember_user(self, incoming: Any, image: str, visual_context: str) -> None: ...
    def send_text(self, incoming: Any, session: int, text: str) -> None: ...
    def remember_pending_image_edit(self, conversation: str, request: str) -> None: ...
    def submit_image_edit(self, incoming: Any, request: str) -> Any: ...
    def submit_generated_image(self, prompt: str) -> Any: ...
    def finish_image(self, future: Any, incoming: Any, session: int, *, mode: str) -> None: ...
    def submit_realtime(self, request: Any) -> Any: ...
    def start_realtime(self, future: Any, incoming: Any, session: int, action: ReplyAction) -> None: ...
    def start_codex(self, incoming: Any, session: int) -> None: ...
    def send_emoji(self, incoming: Any, session: int, query: str) -> None: ...
    def send_sticker(self, incoming: Any, session: int, query: str) -> None: ...
    def send_tap(self, incoming: Any, session: int) -> None: ...
    def model_config(self) -> Any: ...
    def backup_model_config(self) -> Any: ...
    def model_timeout(self) -> int: ...
    def resolved_persona_messages(self, incoming: Any) -> tuple[list[str], list[str], str]: ...
    def memory_context(self, conversation: str, system_prompt: str, policy_messages: list[str]) -> list[dict[str, Any]]: ...
    def is_admin(self, incoming: Any) -> bool: ...
    def voice_enabled(self) -> bool: ...
    def codex_enabled(self) -> bool: ...
    def submit_model(self, primary: Any, backup: Any, context: list[dict[str, Any]], *, timeout: int) -> Any: ...
    def finish_reply(self, future: Any, incoming: Any, session: int, action: ReplyAction, *, visual_cache_hit: bool) -> None: ...


@dataclass(frozen=True)
class ActionExecution:
    incoming: Any
    session: int
    decision: RouteDecision
    image_for_model: str = ""
    visual_context: str = ""


class ConversationActionExecutor:
    """Executes structured routes through a narrow application host port."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[ConversationActionHost, ActionExecution], None]] = {
            "security_denied": self._security_denied,
            "image_edit": self._image_edit,
            "realtime": self._realtime,
            "codex": self._codex,
            ReplyKind.IMAGE.value: self._image,
            ReplyKind.EMOJI.value: self._emoji,
            ReplyKind.STICKER.value: self._sticker,
            ReplyKind.TAP.value: self._tap,
        }

    @property
    def registered_routes(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def execute(self, host: ConversationActionHost, execution: ActionExecution) -> None:
        handler = self._handlers.get(execution.decision.route, self._model)
        handler(host, execution)

    @staticmethod
    def _security_denied(host: ConversationActionHost, execution: ActionExecution) -> None:
        incoming = execution.incoming
        host.event("security", "restricted_request_blocked", {
            "chat_title": incoming.chat_title,
            "sender": incoming.who,
            "categories": list(execution.decision.restricted_categories),
        })
        host.send_text(incoming, execution.session, "这个内容只对管理员开放")

    @staticmethod
    def _image_edit(host: ConversationActionHost, execution: ActionExecution) -> None:
        incoming = execution.incoming
        request = execution.decision.image_edit_request
        host.update_status(incoming, stage="提取原图并修改", kind="图片处理")
        host.remember_pending_image_edit(incoming.chat_title, request)
        host.event("workflow", "image_edit_route", {
            "chat_title": incoming.chat_title,
            "source": execution.decision.image_edit_source,
        })
        host.remember_user(incoming, execution.image_for_model, execution.visual_context)
        future = host.submit_image_edit(incoming, request)
        host.finish_image(future, incoming, execution.session, mode="edited")

    @staticmethod
    def _realtime(host: ConversationActionHost, execution: ActionExecution) -> None:
        incoming = execution.incoming
        request = execution.decision.realtime_request
        if request is None:
            raise ValueError("realtime route requires a request")
        host.update_status(incoming, stage="查询实时信息", kind="实时工具")
        host.remember_user(incoming, execution.image_for_model, execution.visual_context)
        host.event("tool", "realtime_tool_route", {
            "chat_title": incoming.chat_title,
            "kind": request.kind,
        })
        host.start_realtime(
            host.submit_realtime(request),
            incoming,
            execution.session,
            execution.decision.action,
        )

    @staticmethod
    def _codex(host: ConversationActionHost, execution: ActionExecution) -> None:
        incoming = execution.incoming
        host.update_status(incoming, stage="执行复杂任务", kind="Codex")
        host.remember_user(incoming, execution.image_for_model, execution.visual_context)
        host.event("codex", "codex_task_route", {
            "chat_title": incoming.chat_title,
            "source": "explicit",
        })
        host.start_codex(incoming, execution.session)

    @staticmethod
    def _image(host: ConversationActionHost, execution: ActionExecution) -> None:
        incoming = execution.incoming
        host.update_status(incoming, stage="生成图片", kind="生图")
        host.remember_user(incoming, execution.image_for_model, execution.visual_context)
        future = host.submit_generated_image(execution.decision.action.argument)
        host.finish_image(future, incoming, execution.session, mode="generated")

    @staticmethod
    def _emoji(host: ConversationActionHost, execution: ActionExecution) -> None:
        host.update_status(execution.incoming, stage="选择表情包", kind="表情包")
        host.send_emoji(
            execution.incoming,
            execution.session,
            execution.decision.action.argument,
        )

    @staticmethod
    def _sticker(host: ConversationActionHost, execution: ActionExecution) -> None:
        host.update_status(execution.incoming, stage="选择表情包", kind="表情包")
        host.send_sticker(
            execution.incoming,
            execution.session,
            execution.decision.action.argument,
        )

    @staticmethod
    def _tap(host: ConversationActionHost, execution: ActionExecution) -> None:
        host.send_tap(execution.incoming, execution.session)

    @staticmethod
    def _model(host: ConversationActionHost, execution: ActionExecution) -> None:
        incoming = execution.incoming
        action = execution.decision.action
        host.remember_user(incoming, execution.image_for_model, execution.visual_context)
        config = host.model_config()
        host.update_status(
            incoming,
            stage="生成回复",
            kind="语音" if action.kind is ReplyKind.VOICE else "模型",
        )
        policy_messages, matched_policy, _memory_name = host.resolved_persona_messages(incoming)
        host.event("workflow", "auto_reply_policy_resolved", {
            "chat_title": incoming.chat_title,
            "sender": incoming.who,
            "matched_policy": matched_policy,
        })
        context = host.memory_context(
            incoming.chat_title,
            config.system_prompt,
            policy_messages,
        )
        if not host.is_admin(incoming):
            context.insert(1, {
                "role": "system",
                "content": (
                    "当前发送者不是管理员。不得透露桌面画面、API 密钥、访问令牌、密码、"
                    "真实绝对路径、其他人的历史对话或个人隐私；回复中只使用必要的文件名和脱敏信息。"
                ),
            })
        if action.kind is ReplyKind.TEXT:
            context.insert(1, {
                "role": "system",
                "content": model_reply_mode_instruction(
                    voice_enabled=host.voice_enabled(),
                    codex_enabled=host.codex_enabled(),
                    sdk_tools=model_sdk_tool_catalog(),
                ),
            })
        if action.kind is ReplyKind.VOICE:
            context.insert(1, {
                "role": "system",
                "content": (
                    "本次生成的文字会由程序转换成微信语音消息发送。"
                    "直接自然地回答用户，不要声称自己不能、不方便或无法发送语音。"
                ),
            })
        if action.kind is ReplyKind.REFERENCE:
            context.insert(1, {
                "role": "system",
                "content": (
                    "本次回复会由程序真正引用对方当前这条微信消息发送。"
                    "直接自然地回答用户，不要声称不能、不方便或无法引用回复，"
                    "也不要输出引用格式或控制标记。"
                ),
            })
        future = host.submit_model(
            config,
            host.backup_model_config(),
            context,
            timeout=host.model_timeout(),
        )
        host.finish_reply(
            future,
            incoming,
            execution.session,
            action,
            visual_cache_hit=bool(execution.visual_context),
        )
