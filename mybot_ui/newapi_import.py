from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit


NEWAPI_CONNECTION_TYPE = "newapi_channel_conn"
DEFAULT_CHAT_MODEL = "gpt-5.6-sol"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_REASONING_EFFORT = "high"


@dataclass(frozen=True)
class NewApiConnection:
    api_key: str
    base_url: str
    chat_model: str = DEFAULT_CHAT_MODEL
    image_model: str = DEFAULT_IMAGE_MODEL
    reasoning_effort: str = DEFAULT_REASONING_EFFORT

    @property
    def codex_base_url(self) -> str:
        return self.base_url if self.base_url.endswith("/v1") else self.base_url + "/v1"


def parse_newapi_connection(value: str | dict[str, Any]) -> NewApiConnection:
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 格式无效：{exc.msg}") from exc
    elif isinstance(value, dict):
        payload = value
    else:
        raise ValueError("导入内容必须是 JSON 对象。")

    if not isinstance(payload, dict):
        raise ValueError("导入内容必须是 JSON 对象。")
    if str(payload.get("_type") or "").strip() != NEWAPI_CONNECTION_TYPE:
        raise ValueError(f"不支持的连接类型，需要 {NEWAPI_CONNECTION_TYPE}。")

    api_key = str(payload.get("key") or "").strip()
    if not api_key:
        raise ValueError("连接配置缺少 key。")

    base_url = _normalize_base_url(str(payload.get("url") or ""))
    return NewApiConnection(api_key=api_key, base_url=base_url)


def _normalize_base_url(value: str) -> str:
    raw = value.strip().rstrip("/")
    if not raw:
        raise ValueError("连接配置缺少 url。")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url 必须是有效的 HTTP 或 HTTPS 地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("url 不能包含账号、密码、查询参数或片段。")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
