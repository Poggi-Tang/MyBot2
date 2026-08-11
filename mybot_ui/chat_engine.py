from __future__ import annotations

import json
import base64
import hashlib
import io
import mimetypes
import re
import uuid
import urllib.error
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .attachments import IncomingAttachment, attachment_name_from_message
from .operation_log import operations


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = ""
    api_key: str = ""
    system_prompt: str = "你是一个自然、简洁、有帮助的微信聊天助手。不要声称自己正在操作电脑。"
    temperature: float = 0.7


@dataclass(frozen=True)
class ImageConfig:
    base_url: str = "https://api.openai.com"
    model: str = "gpt-image-1.5"
    api_key: str = ""
    size: str = "1024x1024"


@dataclass(frozen=True)
class IncomingMessage:
    chat_title: str
    who: str
    content: str
    send_date: str = ""
    message_type: int = -1
    image_base64: str = ""
    attachments: tuple[IncomingAttachment, ...] = ()

    @property
    def feature(self) -> str:
        image_digest = (
            hashlib.sha256(self.image_base64.encode("ascii", errors="ignore")).hexdigest()[:16]
            if self.image_base64
            else ""
        )
        return (
            f"{self.chat_title}|{self.who}|{self.content}|{self.send_date}|"
            f"{self.message_type}|{image_digest}|"
            + ",".join(item.sha256 or item.path or item.name for item in self.attachments)
        )


class ConversationMemory:
    def __init__(self, max_messages: int = 16) -> None:
        self.max_messages = max_messages
        self._messages: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=self.max_messages))

    def add_user(
        self,
        chat: str,
        who: str,
        content: str,
        image_base64: str = "",
        visual_context: str = "",
    ) -> None:
        text = f"{who}: {content}"
        if visual_context:
            text += f"\n{visual_context}"
        if image_base64:
            text += (
                "\n请理解当前收到的图片；如果视觉输入本身是聊天窗口截图，"
                "只分析最下方最新的图片气泡，不要概述其他历史图片或聊天文字。"
                "完成理解后，必须在正常回复末尾附加一个内部标记："
                '<MYBOT_IMAGE_META>{"kind":"screenshot|image|sticker中的一个",'
                '"description":"对视觉内容的简短、可复用语义描述"}</MYBOT_IMAGE_META>。'
                "截图指界面、聊天记录、网页或软件画面；普通照片和可复用图片归为 image；"
                "用于表达情绪或反应的图片形式表情包归为 sticker。不要向用户解释这个内部标记。"
            )
            media_type = _image_media_type(image_base64)
            content_value: Any = [
                {"type": "text", "text": text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{_raw_base64(image_base64)}"},
                },
            ]
        else:
            content_value = text
        self._messages[chat].append({"role": "user", "content": content_value})

    def add_assistant(self, chat: str, content: str) -> None:
        self._messages[chat].append({"role": "assistant", "content": content})

    def resolve_latest_visual(
        self,
        chat: str,
        who: str,
        content: str,
        kind: str,
        description: str,
    ) -> bool:
        for message in reversed(self._messages[chat]):
            if message.get("role") != "user" or not isinstance(message.get("content"), list):
                continue
            message["content"] = (
                f"{who}: {content}\n"
                f"[已理解视觉内容，类型：{kind}] {description}"
            )
            return True
        return False

    def transcript(self, chat: str, max_chars: int = 6_000) -> str:
        lines: list[str] = []
        for message in self._messages[chat]:
            role = "对方" if message.get("role") == "user" else "MyBot"
            content = message.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    str(item.get("text", ""))
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                content = " ".join(text_parts) + " [包含图片]"
            lines.append(f"{role}: {str(content).strip()}")
        return "\n".join(lines)[-max_chars:]

    def context(
        self,
        chat: str,
        system_prompt: str,
        policy_messages: list[str] | tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        behavior = (
            "自然回复当前微信消息，不要复述发送者标签。需要分成多条短消息时，"
            "只用 <MYBOT_SPLIT> 分隔，最多四条。图片会作为视觉输入附在消息中。"
        )
        return [
            {"role": "system", "content": system_prompt},
            *({"role": "system", "content": message} for message in policy_messages if message.strip()),
            {"role": "system", "content": behavior},
            *list(self._messages[chat]),
        ]

    def clear(self) -> None:
        self._messages.clear()


class ChatModelClient:
    def list_models(self, config: ModelConfig) -> list[str]:
        span = operations.start("model", "ListModels", details={"provider": config.provider, "base_url": config.base_url})
        try:
            if config.provider != "ollama":
                data = self._request_json("GET", self._openai_endpoint(config.base_url, "/models"), None, config.api_key)
                models = data.get("data") or data.get("models") or []
                names = [str(item.get("id") or item.get("name") or "") for item in models if isinstance(item, dict)]
                result = [name for name in names if name]
            else:
                data = self._request_json("GET", config.base_url.rstrip("/") + "/api/tags", None, config.api_key)
                result = [str(item.get("name", "")) for item in data.get("models", []) if item.get("name")]
            operations.finish(span, success=True, result={"model_count": len(result)})
            return result
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def generate(
        self,
        config: ModelConfig,
        messages: list[dict[str, Any]],
        *,
        timeout: int = 120,
    ) -> str:
        timeout = max(5, int(timeout))
        span = operations.start("model", "GenerateChat", details={
            "provider": config.provider, "base_url": config.base_url,
            "model": config.model, "message_count": len(messages),
            "request_timeout_seconds": timeout, "messages": messages,
        })
        try:
            if not config.model.strip():
                raise RuntimeError("未选择聊天模型")
            if config.provider == "ollama":
                payload = {
                    "model": config.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": config.temperature},
                }
                data = self._request_json("POST", config.base_url.rstrip("/") + "/api/chat", payload, config.api_key, timeout=timeout)
                content = ((data.get("message") or {}).get("content") or "").strip()
            else:
                endpoint = self._openai_endpoint(config.base_url, "/chat/completions")
                payload = {"model": config.model, "messages": messages, "temperature": config.temperature}
                data = self._request_json("POST", endpoint, payload, config.api_key, timeout=timeout)
                choices = data.get("choices") or []
                content = (((choices[0] if choices else {}).get("message") or {}).get("content") or "").strip()
            if not content:
                raise RuntimeError("模型返回了空回复")
            operations.finish(span, success=True, result=content)
            return content
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def generate_image(self, config: ImageConfig, prompt: str, output_dir: str | Path | None = None) -> str:
        span = operations.start("model", "GenerateImage", details={
            "base_url": config.base_url, "model": config.model, "size": config.size, "prompt": prompt,
        })
        try:
            return self._generate_image(config, prompt, output_dir, span)
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def _generate_image(self, config: ImageConfig, prompt: str, output_dir: str | Path | None, span) -> str:
        if not config.model.strip():
            raise RuntimeError("未选择生图模型")
        payload = {
            "model": config.model,
            "prompt": prompt.strip(),
            "size": config.size,
            "response_format": "b64_json",
        }
        data = self._request_json("POST", self._openai_endpoint(config.base_url, "/images/generations"), payload, config.api_key, timeout=180)
        return self._save_image_response(data, config.api_key, output_dir, span, "wechat-image")

    def edit_image(
        self,
        config: ImageConfig,
        prompt: str,
        image_path: str | Path,
        output_dir: str | Path | None = None,
    ) -> str:
        source = Path(image_path)
        span = operations.start("model", "EditImage", details={
            "base_url": config.base_url,
            "model": config.model,
            "size": config.size,
            "prompt": prompt,
            "source_name": source.name,
        })
        try:
            if not config.model.strip():
                raise RuntimeError("未选择生图模型")
            if not source.is_file():
                raise FileNotFoundError(f"待编辑图片不存在：{source.name}")
            if source.stat().st_size > 25 * 1024 * 1024:
                raise RuntimeError("待编辑图片超过 25 MiB")
            data = self._request_multipart_json(
                self._openai_endpoint(config.base_url, "/images/edits"),
                {
                    "model": config.model,
                    "prompt": prompt.strip(),
                    "size": config.size,
                    "response_format": "b64_json",
                },
                "image",
                source,
                config.api_key,
                timeout=180,
            )
            return self._save_image_response(data, config.api_key, output_dir, span, "wechat-image-edit")
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def _save_image_response(
        self,
        data: dict[str, Any],
        api_key: str,
        output_dir: str | Path | None,
        span,
        prefix: str,
    ) -> str:
        item = (data.get("data") or [{}])[0]
        encoded = item.get("b64_json")
        if encoded:
            raw = base64.b64decode(_raw_base64(str(encoded)))
        elif item.get("url"):
            headers = {"User-Agent": "MyBot/2.0"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            request = urllib.request.Request(str(item["url"]), headers=headers)
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = response.read()
        else:
            raise RuntimeError("生图接口未返回图片数据")
        target_dir = Path(output_dir) if output_dir else Path(__file__).resolve().parent.parent / "generated_images"
        target_dir.mkdir(parents=True, exist_ok=True)
        if not raw or len(raw) > 25 * 1024 * 1024:
            raise RuntimeError("生图接口返回的图片为空或超过 25 MiB")
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image_format = str(image.format or "").upper()
                image.verify()
        except (OSError, ValueError, UnidentifiedImageError) as exc:
            raise RuntimeError("生图接口返回的文件不是有效图片") from exc
        extension = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "WEBP": ".webp"}.get(image_format)
        if not extension:
            raise RuntimeError(f"生图接口返回了不支持的图片格式：{image_format or 'unknown'}")
        path = target_dir / f"{prefix}-{uuid.uuid4().hex}{extension}"
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(raw)
        temporary.replace(path)
        operations.finish(span, success=True, result={"path": str(path), "bytes": len(raw), "format": image_format})
        return str(path)

    def generate_with_fallback(
        self,
        primary: ModelConfig,
        backup: ModelConfig | None,
        messages: list[dict[str, Any]],
        *,
        timeout: int = 120,
    ) -> str:
        try:
            return self.generate(primary, messages, timeout=timeout)
        except Exception as primary_error:
            if not backup or not backup.base_url or not backup.model:
                raise
            try:
                return self.generate(backup, messages, timeout=timeout)
            except Exception as backup_error:
                raise RuntimeError(f"主接口失败：{primary_error}；备用接口失败：{backup_error}") from backup_error

    @staticmethod
    def _openai_endpoint(base_url: str, suffix: str) -> str:
        root = base_url.rstrip("/")
        if root.endswith(suffix):
            return root
        if root.endswith("/v1"):
            return root + suffix
        return root + "/v1" + suffix

    @staticmethod
    def _request_json(method: str, url: str, payload: dict[str, Any] | None, api_key: str, timeout: int = 15) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MyBot/2.0",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"模型服务 HTTP {exc.code}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接模型服务：{exc.reason}") from exc

    @staticmethod
    def _request_multipart_json(
        url: str,
        fields: dict[str, str],
        file_field: str,
        file_path: Path,
        api_key: str,
        *,
        timeout: int,
    ) -> dict[str, Any]:
        boundary = f"----MyBot{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("ascii"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        safe_name = f"source{file_path.suffix.lower() or '.png'}"
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(
            f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_name}"\r\n'.encode("ascii")
        )
        body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("ascii"))
        body.extend(file_path.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode("ascii"))
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "MyBot/2.0",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(url, data=bytes(body), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"模型服务 HTTP {exc.code}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接模型服务：{exc.reason}") from exc


def _parse_send_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def repair_wechat_sdk_text(value: Any) -> str:
    """Repair text corrupted across UTF-8/GB18030/Latin-1 SDK boundaries."""
    text = str(value or "").strip()
    if not text:
        return ""
    for source_encoding, target_encoding in (
        ("gb18030", "utf-8"),
        ("latin1", "gb18030"),
    ):
        try:
            repaired = text.encode(source_encoding).decode(target_encoding).strip()
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if (
            not repaired
            or repaired == text
            or "\ufffd" in repaired
            or len(repaired) >= len(text)
        ):
            continue
        if len(text) - len(repaired) < 2 and len(text) < len(repaired) * 1.4:
            continue
        return repaired
    return text


def _credible_sender(who: str) -> bool:
    if not who or len(who) > 64 or "\n" in who or "\r" in who:
        return False
    if who in {
        "昨天", "今天", "前天", "上午", "下午", "晚上", "星期",
        "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日", "星期天",
        "周一", "周二", "周三", "周四", "周五", "周六", "周日", "周天",
    }:
        return False
    if re.fullmatch(r"\d{1,2}(:\d{2})?", who):
        return False
    return bool(re.search(r"[A-Za-z\u3400-\u9fff]", who))


def _credible_preview_sender(who: str) -> bool:
    if not _credible_sender(who) or len(who) > 24:
        return False
    # Conversation previews use "sender: message" for groups. A sentence
    # containing a colon must not become a fake contact and poison memory.
    return not bool(re.search(r"[,，。！？!?；;：:\[\]【】]", who))


def parse_listener_event(
    data: Any,
    *,
    self_names: set[str] | None = None,
    now: datetime | None = None,
    max_age: timedelta = timedelta(minutes=5),
) -> list[IncomingMessage]:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict) or "new_message" not in data:
        return []
    new_messages = data.get("new_message", [])
    if isinstance(new_messages, str):
        try:
            new_messages = json.loads(new_messages)
        except json.JSONDecodeError:
            return []
    chat_title = repair_wechat_sdk_text(data.get("chat_title") or "")
    ignored_senders = {"我", "自己", "系统", *(self_names or set())}
    current_time = now or datetime.now()
    result: list[IncomingMessage] = []
    for item in new_messages or []:
        if not isinstance(item, dict):
            continue
        who = repair_wechat_sdk_text(item.get("who") or item.get("sender") or "")
        # The SDK sometimes omits the sender on fresh OCR callbacks even
        # though the message body and timestamp are valid. Preserve the live
        # message; outgoing-echo suppression still prevents self-replies.
        if not who:
            who = "对方"
        content = repair_wechat_sdk_text(item.get("message") or item.get("text") or "")
        image_base64 = str(
            item.get("image_base64_str")
            or item.get("image_base64")
            or item.get("imageBase64Str")
            or ""
        ).strip()
        image_file = str(item.get("image_file") or item.get("ImageFile") or "").strip()
        file_path = str(item.get("file_path") or item.get("FilePath") or "").strip()
        file_name = repair_wechat_sdk_text(item.get("file_name") or item.get("FileName") or "")
        if not image_base64 and image_file:
            image_base64 = _image_file_base64(image_file)
        if not content and image_base64:
            content = "[图片]"
        send_date = _parse_send_date(item.get("send_date") or item.get("sendDate"))
        try:
            message_type = int(item.get("message_type", item.get("messageType", -1)))
        except (TypeError, ValueError):
            message_type = -1
        attachments: list[IncomingAttachment] = []
        if file_path or file_name or content.startswith(("文件", "[文件]")):
            name = file_name or attachment_name_from_message(content)
            if name:
                attachments.append(IncomingAttachment(name=name, path=file_path, kind="file"))
        if image_file:
            media_kind = "sticker" if content.startswith(("动画表情", "[动画表情]")) else "image"
            attachments.append(IncomingAttachment(
                name=Path(image_file).name,
                path=image_file,
                kind=media_kind,
            ))
        # WeChatAuto4_X reports file-only callbacks with DateTime.MinValue.
        # The callback itself is live, so use its arrival time while retaining
        # strict timestamp validation for ordinary text messages.
        if attachments and (send_date is None or send_date.year <= 1):
            send_date = current_time
        if (
            not chat_title
            or not content
            or who in ignored_senders
            or not _credible_sender(who)
            or send_date is None
            or send_date > current_time + timedelta(minutes=1)
            or current_time - send_date > max_age
        ):
            continue
        result.append(
            IncomingMessage(
                chat_title,
                who,
                content,
                send_date.isoformat(timespec="seconds"),
                message_type,
                image_base64,
                tuple(attachments),
            )
        )
    if not result:
        return []
    # The first OCR callback can include historical bubbles, while a real burst
    # can also contain several questions with the same second/minute timestamp.
    # Keep the newest short burst and discard older context from the callback.
    latest = max(
        datetime.fromisoformat(message.send_date.replace("Z", "+00:00")).replace(tzinfo=None)
        for message in result
    )
    return [
        message
        for message in result
        if latest
        - datetime.fromisoformat(message.send_date.replace("Z", "+00:00")).replace(tzinfo=None)
        <= timedelta(seconds=10)
    ]


def _image_file_base64(value: str) -> str:
    path = Path(value)
    try:
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            return ""
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""


def _raw_base64(value: str) -> str:
    text = value.strip()
    if text.startswith("data:") and "," in text:
        return text.split(",", 1)[1]
    return text


def _image_media_type(value: str) -> str:
    text = value.strip()
    if text.startswith("data:") and ";" in text:
        return text[5:].split(";", 1)[0]
    try:
        prefix = base64.b64decode(_raw_base64(text)[:64] + "===", validate=False)
    except (ValueError, TypeError):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def parse_conversation_preview(
    item: Any,
    *,
    self_names: set[str] | None = None,
    now: datetime | None = None,
) -> IncomingMessage | None:
    if not isinstance(item, dict) or int(item.get("not_read_numbr") or 0) != 0:
        return None
    chat_title = str(item.get("conversation_title") or "").strip()
    content = str(item.get("conversation_content") or "").strip()
    if not chat_title or not content:
        return None

    who = "对方"
    for separator in (": ", "："):
        if separator not in content:
            continue
        candidate, message = content.split(separator, 1)
        if _credible_preview_sender(candidate.strip()) and message.strip():
            who = candidate.strip()
            content = message.strip()
        break
    if who in ({"我", "自己", "系统"} | (self_names or set())):
        return None

    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    time_label = str(item.get("time") or "").strip()
    return IncomingMessage(chat_title, who, content, f"{stamp}|{time_label}")
