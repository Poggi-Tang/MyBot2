from __future__ import annotations

import hashlib
import math
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum


AUTO_REPLY_DELIMITER = "<MYBOT_SPLIT>"
MAX_AUTO_REPLY_SEGMENTS = 4
OUTGOING_ECHO_TTL_SECONDS = 24 * 60 * 60
OUTGOING_VOICE_ECHO_TTL_SECONDS = 45.0
OUTGOING_MEDIA_ECHO_TTL_SECONDS = 120.0
OUTGOING_FILE_ECHO_TTL_SECONDS = 120.0
INCOMING_DEDUPE_TTL_SECONDS = 10 * 60.0
MAX_TRACKED_MESSAGES_PER_CONVERSATION = 1_000
FORBIDDEN_AUTO_REPLY_CHARACTERS = "~。"
MODEL_STICKER_PATTERN = re.compile(r"^<MYBOT_STICKER(?::([^>]{0,24}))?>$", re.IGNORECASE)
TRAILING_MODEL_ARTIFACT_PATTERN = re.compile(
    r"\s+(?=[a-f0-9]{6,12}$)(?=[a-f0-9]*[a-f])(?=[a-f0-9]*\d)[a-f0-9]{6,12}$",
    re.IGNORECASE,
)
INTERNAL_CONTROL_MARKER_PATTERN = re.compile(
    r"</?MYBOT_(?!SPLIT(?:>|$))[^>]+>",
    re.IGNORECASE,
)
INTERNAL_WORKFLOW_SENTENCE_PATTERN = re.compile(
    r"[^。！？!?\n]*(?:"
    r"(?:通过|调用|使用|交给|转交|调度).{0,12}(?:Codex|CLI|后台|内部工具|接口|模型)|"
    r"(?:任务|文件)(?:登记|注册)服务|MCP\s+[A-Za-z0-9_.-]+|"
    r"(?:task|thread)[_-]?id"
    r")[^。！？!?\n]*[。！？!?]?",
    re.IGNORECASE,
)
SOURCE_TRAILER_PATTERN = re.compile(
    r"(?:数据源|观测时间)[：:].*$|这是\s*wttr\.in.*$",
    re.IGNORECASE | re.MULTILINE,
)


class AutoReplySegmentsError(ValueError):
    pass


class ReplyKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    EMOJI = "emoji"
    STICKER = "sticker"


@dataclass(frozen=True)
class ReplyAction:
    kind: ReplyKind
    argument: str = ""


class ListenerMessageCursor:
    """Inbound identity dedupe plus durable outgoing echo tracking.

    WeChatAuto callbacks and conversation previews can surface the same bubble
    many seconds apart. The inbound feature includes the message minute, so a
    longer TTL removes cross-source repeats while allowing later identical
    messages. Outgoing echoes live longer because UIA may rediscover a sent
    bubble after focus or navigation changes.
    """

    def __init__(self) -> None:
        self._incoming: dict[str, deque[tuple[str, float]]] = defaultdict(deque)
        self._outgoing: dict[str, deque[tuple[str, float]]] = defaultdict(deque)
        self._outgoing_voice: dict[str, deque[float]] = defaultdict(deque)
        self._outgoing_media: dict[str, deque[tuple[str, float]]] = defaultdict(deque)
        self._outgoing_files: dict[str, deque[tuple[str, float]]] = defaultdict(deque)

    def reset(self) -> None:
        self._incoming.clear()
        self._outgoing.clear()
        self._outgoing_voice.clear()
        self._outgoing_media.clear()
        self._outgoing_files.clear()

    def accept_incoming(self, conversation: str, feature: str) -> bool:
        now = time.monotonic()
        values = self._incoming[conversation]
        self._prune(values, now - INCOMING_DEDUPE_TTL_SECONDS)
        if any(candidate == feature for candidate, _ in values):
            return False
        values.append((feature, now))
        self._trim(values)
        return True

    def record_outgoing(self, conversation: str, text: str) -> None:
        if not conversation or not text:
            return
        now = time.monotonic()
        values = self._outgoing[conversation]
        self._prune(values, now - OUTGOING_ECHO_TTL_SECONDS)
        values.append((_echo_key(text), now))
        self._trim(values)

    def is_outgoing_echo(self, conversation: str, text: str) -> bool:
        values = self._outgoing.get(conversation)
        if not values:
            return False
        self._prune(values, time.monotonic() - OUTGOING_ECHO_TTL_SECONDS)
        key = _echo_key(text)
        if any(candidate == key for candidate, _ in values):
            return True
        truncated = _truncated_echo_prefix(key)
        return bool(
            truncated
            and any(candidate.startswith(truncated) for candidate, _ in values)
        )

    def record_outgoing_voice(self, conversation: str, text: str) -> None:
        """Remember the spoken text and the UIA placeholder echoes it creates."""
        self.record_outgoing(conversation, text)
        if not conversation:
            return
        now = time.monotonic()
        values = self._outgoing_voice[conversation]
        self._prune_voice(values, now - OUTGOING_VOICE_ECHO_TTL_SECONDS)
        # The same sent bubble can arrive through the listener and preview poller.
        values.extend((now, now))

    def is_outgoing_voice_echo(self, conversation: str, text: str) -> bool:
        if not _is_voice_placeholder(text):
            return False
        values = self._outgoing_voice.get(conversation)
        if not values:
            return False
        self._prune_voice(values, time.monotonic() - OUTGOING_VOICE_ECHO_TTL_SECONDS)
        if not values:
            return False
        values.popleft()
        return True

    def cancel_outgoing_voice(self, conversation: str, text: str) -> None:
        """Roll back a marker when the corresponding send did not succeed."""
        voice_values = self._outgoing_voice.get(conversation)
        if voice_values:
            for _ in range(min(2, len(voice_values))):
                voice_values.pop()
        outgoing_values = self._outgoing.get(conversation)
        if not outgoing_values:
            return
        key = _echo_key(text)
        for index in range(len(outgoing_values) - 1, -1, -1):
            if outgoing_values[index][0] == key:
                del outgoing_values[index]
                break

    def record_outgoing_media(self, conversation: str, placeholder: str = "[图片]") -> None:
        """Track one media echo without suppressing later inbound media."""
        if not conversation or not placeholder:
            return
        now = time.monotonic()
        values = self._outgoing_media[conversation]
        self._prune(values, now - OUTGOING_MEDIA_ECHO_TTL_SECONDS)
        values.append((_echo_key(placeholder), now))
        self._trim(values)

    def is_outgoing_media_echo(self, conversation: str, text: str) -> bool:
        values = self._outgoing_media.get(conversation)
        if not values:
            return False
        self._prune(values, time.monotonic() - OUTGOING_MEDIA_ECHO_TTL_SECONDS)
        key = _echo_key(text)
        for index, (candidate, _created_at) in enumerate(values):
            if candidate == key:
                del values[index]
                return True
        return False

    def cancel_outgoing_media(self, conversation: str, placeholder: str = "[图片]") -> None:
        values = self._outgoing_media.get(conversation)
        if not values:
            return
        key = _echo_key(placeholder)
        for index in range(len(values) - 1, -1, -1):
            if values[index][0] == key:
                del values[index]
                break

    def record_outgoing_file(self, conversation: str, filename: str) -> None:
        """Track the listener and preview echoes created by one sent file."""
        key = _file_echo_key(filename)
        if not conversation or not key:
            return
        now = time.monotonic()
        values = self._outgoing_files[conversation]
        self._prune(values, now - OUTGOING_FILE_ECHO_TTL_SECONDS)
        # A sent file can surface independently through the listener and the
        # conversation-preview poller.
        values.extend(((key, now), (key, now)))
        self._trim(values)

    def is_outgoing_file_echo(self, conversation: str, text: str) -> bool:
        key = _file_echo_key(text)
        values = self._outgoing_files.get(conversation)
        if not key or not values:
            return False
        self._prune(values, time.monotonic() - OUTGOING_FILE_ECHO_TTL_SECONDS)
        for index, (candidate, _created_at) in enumerate(values):
            if candidate == key:
                del values[index]
                return True
        return False

    def cancel_outgoing_file(self, conversation: str, filename: str) -> None:
        values = self._outgoing_files.get(conversation)
        if not values:
            return
        key = _file_echo_key(filename)
        for index in range(len(values) - 1, -1, -1):
            if values[index][0] == key:
                del values[index]

    @staticmethod
    def _prune(values: deque[tuple[str, float]], oldest: float) -> None:
        while values and values[0][1] < oldest:
            values.popleft()

    @staticmethod
    def _trim(values: deque[tuple[str, float]]) -> None:
        while len(values) > MAX_TRACKED_MESSAGES_PER_CONVERSATION:
            values.popleft()

    @staticmethod
    def _prune_voice(values: deque[float], oldest: float) -> None:
        while values and values[0] < oldest:
            values.popleft()


def incoming_dedupe_feature(incoming, *, include_sender: bool = True) -> str:
    """Build a listener/preview-stable identity for one incoming bubble."""
    content = re.sub(r"\s+", " ", str(getattr(incoming, "content", "") or "")).strip().casefold()
    sender = (
        re.sub(r"\s+", " ", str(getattr(incoming, "who", "") or "")).strip().casefold()
        if include_sender
        else ""
    )
    send_date = str(getattr(incoming, "send_date", "") or "")
    minute_matches = re.findall(r"(?:T|\s|^)(\d{1,2}):(\d{2})(?::\d{2})?", send_date)
    minute = f"{int(minute_matches[-1][0]):02d}:{minute_matches[-1][1]}" if minute_matches else ""
    image_base64 = str(getattr(incoming, "image_base64", "") or "")
    media_digest = (
        hashlib.sha256(image_base64.encode("ascii", errors="ignore")).hexdigest()[:16]
        if image_base64
        else ""
    )
    attachments = getattr(incoming, "attachments", ()) or ()
    attachment_identity = ",".join(
        str(getattr(item, "sha256", "") or getattr(item, "path", "") or getattr(item, "name", ""))
        for item in attachments
    )
    return "\x00".join((sender, content, minute, media_digest, attachment_identity))


def requested_action(text: str) -> ReplyAction:
    value = _strip_chat_mentions(re.sub(r"\s+", " ", text).strip())
    lowered = value.casefold()
    for prefix in ("/image", "生成图片", "生成一张图", "画图", "画一张", "生图"):
        if lowered.startswith(prefix.casefold()):
            prompt = value[len(prefix) :].lstrip("：: ，,")
            return ReplyAction(ReplyKind.IMAGE, prompt or "一张适合微信聊天分享的图片")

    natural_image = re.fullmatch(
        r"(?:请|麻烦)?(?:你)?(?:帮我|给我)?(?:画|生成|制作|做)"
        r"(?P<prompt>.+?)(?:给我|发给我|让我看看)?[。！？!?]?",
        value,
    )
    if natural_image:
        prompt = _clean_image_prompt(natural_image.group("prompt"))
        if prompt:
            return ReplyAction(ReplyKind.IMAGE, prompt)

    send_image = re.fullmatch(
        r"(?:请|麻烦)?(?:你)?(?:给我)?发(?:给我)?(?:一张|一个|一幅)?"
        r"(?P<prompt>.+?)(?:的)?(?:图片|图像|图|照片)(?:给我)?[。！？!?]?",
        value,
    )
    if send_image:
        prompt = _clean_image_prompt(send_image.group("prompt"))
        if prompt:
            return ReplyAction(ReplyKind.IMAGE, prompt)

    if "语音" in value and any(word in value for word in ("发", "用", "回复", "回我", "说")):
        return ReplyAction(ReplyKind.VOICE)

    sticker_action = _requested_sticker_action(value)
    if sticker_action is not None:
        return sticker_action

    return ReplyAction(ReplyKind.TEXT)


def parse_auto_reply_segments(
    text: str,
    *,
    prefix: str = "",
    multi_message_enabled: bool = True,
) -> tuple[str, ...]:
    raw = sanitize_auto_reply_text(text)
    if not raw or "\x00" in raw or len(raw) > 2_000:
        raise AutoReplySegmentsError("AI 自动回复为空、无效或超过 2000 字。")
    if not multi_message_enabled:
        return (_prefixed(raw, prefix),)

    pieces = [item.strip() for item in raw.split(AUTO_REPLY_DELIMITER) if item.strip()]
    if len(pieces) == 1:
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", raw) if item.strip()]
        if len(paragraphs) > 1:
            pieces = paragraphs
        else:
            lines = [item.strip() for item in raw.splitlines() if item.strip()]
            if 1 < len(lines) <= MAX_AUTO_REPLY_SEGMENTS:
                pieces = lines

    expanded: list[str] = []
    for piece in pieces:
        expanded.extend(_split_long_piece(piece, 120))
    if len(expanded) > MAX_AUTO_REPLY_SEGMENTS:
        combined = " ".join(expanded)
        target = max(120, math.ceil(len(combined) / MAX_AUTO_REPLY_SEGMENTS))
        if target > 500:
            raise AutoReplySegmentsError("AI 自动回复无法安全拆分为短消息。")
        expanded = _split_long_piece(combined, target)
    if not expanded or len(expanded) > MAX_AUTO_REPLY_SEGMENTS:
        raise AutoReplySegmentsError("AI 自动回复分段数量无效。")
    return tuple(_prefixed(piece, prefix) for piece in expanded)


def sanitize_auto_reply_text(text: str) -> str:
    """Apply non-negotiable output character rules immediately before send."""
    cleaned = INTERNAL_CONTROL_MARKER_PATTERN.sub("", str(text))
    cleaned = re.sub(
        r"我(?:是|只是)(?:一个)?(?:AI|人工智能|机器人|语言模型)",
        "我是圆子",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"作为(?:一个)?(?:AI|人工智能|机器人|语言模型)[，,]?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = INTERNAL_WORKFLOW_SENTENCE_PATTERN.sub("", cleaned)
    cleaned = SOURCE_TRAILER_PATTERN.sub("", cleaned)
    replacements = {
        "这个任务需要一些时间，我处理完成后把结果发给你": "等我一下，我去看看",
        "我去处理一下，有结果就发群里": "稍等，我去看一下",
        "这次任务执行失败了，我已经记录错误，暂时无法给出可靠结果": "这次没弄好，我再看看",
    }
    for source, replacement in replacements.items():
        cleaned = cleaned.replace(source, replacement)
    cleaned = cleaned.translate({ord(char): None for char in FORBIDDEN_AUTO_REPLY_CHARACTERS}).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Some OpenAI-compatible gateways occasionally append a short trace-like
    # hexadecimal token to otherwise natural text. It is never useful in chat.
    return TRAILING_MODEL_ARTIFACT_PATTERN.sub("", cleaned).rstrip()


def select_sticker_item(
    items: list[dict],
    query: str,
    *,
    selection_index: int = 0,
) -> tuple[dict | None, str]:
    """Resolve a request only against custom or saved sticker collections."""
    ranked = sticker_selection_candidates(items, query)
    if not ranked:
        eligible = [item for item in items if _is_allowed_sticker_item(item)]
        if not eligible:
            return None, "目录中没有自定义或收藏表情包"
        return None, f"目录中没有匹配“{query}”的自定义或收藏表情包"
    best_score = ranked[0][0]
    best = [item for score, item in ranked if score == best_score]
    chosen = best[selection_index % len(best)]
    normalized_query = _normalize_sticker_text(query)
    generic = not normalized_query or normalized_query in {"随机", "随便", "一个", "表情", "表情包"}
    reason = "随机轮换" if generic else f"匹配请求“{query}”"
    return chosen, reason


def sticker_selection_candidates(items: list[dict], query: str) -> list[tuple[int, dict]]:
    """Return allowed candidates ranked by the explicit request, preserving ties."""
    eligible = [item for item in items if _is_allowed_sticker_item(item)]
    if not eligible:
        return []

    normalized_query = _normalize_sticker_text(query)
    generic = not normalized_query or normalized_query in {"随机", "随便", "一个", "表情", "表情包"}
    scored: list[tuple[int, dict]] = []
    for item in eligible:
        category = _normalize_sticker_text(_item_field(item, "Category"))
        name = _normalize_sticker_text(_item_field(item, "Name"))
        score = 1 if generic else 0
        if normalized_query:
            if normalized_query == category or normalized_query == name:
                score += 100
            elif normalized_query in category or normalized_query in name:
                score += 70
            elif category in normalized_query or (name and name in normalized_query):
                score += 45
            if any(word in normalized_query for word in ("可爱", "萌")):
                if any(word in category + name for word in ("可爱", "萌", "爱心", "亲亲", "抱抱", "嘻嘻", "美滋滋")):
                    score += 35
            if "狗" in normalized_query and "狗" in category + name:
                score += 40
            if "猫" in normalized_query and "猫" in category + name:
                score += 40
        if score > 0:
            scored.append((score, item))

    return sorted(scored, key=lambda pair: pair[0], reverse=True)


def model_sticker_request(text: str) -> str | None:
    match = MODEL_STICKER_PATTERN.fullmatch(str(text).strip())
    return match.group(1).strip() if match and match.group(1) else ("" if match else None)


def infer_sticker_query(request: str, transcript: str) -> str:
    """Use recent conversation cues when the request leaves the style implicit."""
    query = _normalize_sticker_text(request)
    if query and query not in {"随机", "随便", "一个", "表情", "表情包"}:
        return request
    context = _normalize_sticker_text(transcript[-2400:])
    for marker, inferred in (
        (("舔狗",), "舔狗"),
        (("狗狗", "狗"), "狗"),
        (("可爱", "萌"), "可爱"),
        (("开心", "哈哈", "高兴"), "开心"),
        (("难过", "伤心", "哭"), "哭"),
        (("生气", "骂", "傻逼", "斩token", "断token"), "神经"),
    ):
        if any(marker_item in context for marker_item in marker):
            return inferred
    return request


def sticker_item_send_value(item: dict) -> str:
    mode = _item_field(item, "Mode").casefold()
    return _item_field(item, "Hash") if mode == "visual" else _item_field(item, "Name")


def sticker_item_display_name(item: dict) -> str:
    category = _item_field(item, "Category")
    name = _item_field(item, "Name")
    if name:
        return f"{category}/{name}"
    value = _item_field(item, "Hash")
    return f"{category}/自定义#{value[:6]}"


def _requested_sticker_action(value: str) -> ReplyAction | None:
    if any(marker in value for marker in ("发完告诉我", "告诉我为什么选", "为什么选这个")):
        return None
    if re.search(r"(?:别|不要|不准|禁止).{0,8}(?:发|来).{0,12}表情", value):
        return None
    if re.search(r"再发默认表情(?:包)?.{0,12}(?:我就|试试|别怪)", value):
        return None

    matches: list[str] = []
    explicit = re.compile(
        r"(?:发|来|整|回复)(?:给我)?(?:一个|个|点|张|只)?\s*"
        r"(?P<name>[\u3400-\u9fffA-Za-z0-9]{0,16}?)(?:的)?(?:表情包|表情)"
    )
    for match in explicit.finditer(value):
        name = _clean_sticker_query(match.group("name"))
        if name in {"默认", "微信默认", "默认的"}:
            continue
        matches.append(name)

    # Collection requests often omit the noun: “发个可爱联盟的”“发点可爱的”。
    collection = re.compile(
        r"(?:发(?:一个|个|点|张|只)|来(?:一个|个)|整(?:一个|个))\s*"
        r"(?P<name>[\u3400-\u9fffA-Za-z0-9]{1,16}?)(?:的)?"
        r"(?:行不行|可以吗|吧|啊|呀|呗)?(?:[，,。！？!?]|$)"
    )
    for match in collection.finditer(value):
        name = _clean_sticker_query(match.group("name"))
        if name and not any(marker in name for marker in ("消息", "图片", "照片", "语音", "文件", "链接", "表情")):
            matches.append(name)

    if matches:
        return ReplyAction(ReplyKind.STICKER, matches[-1])
    return None


def _strip_chat_mentions(value: str) -> str:
    value = re.sub(
        r"^@[^\s，,。！？!?]{1,12}?(?=(?:再|发|来|整|用|回|给|请|麻烦|你|我))",
        "",
        value,
    )
    value = re.sub(r"@[^\s，,。！？!?]+$", "", value).strip()
    return re.sub(r"^@[^\s，,。！？!?]+\s+", "", value).strip()


def _clean_sticker_query(value: str) -> str:
    result = value.strip(" ，,。！？!?的呢吧啊呀呗")
    return "可爱" if result in {"可爱的", "萌萌的"} else result


def _normalize_sticker_text(value: str) -> str:
    result = re.sub(r"\s+", "", value).casefold()
    result = re.sub(r"[0-9①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]+$", "", result)
    return result.strip("-_·（）()[]【】的")


def _item_field(item: dict, name: str) -> str:
    return str(item.get(name) or item.get(name.casefold()) or "").strip()


def _is_allowed_sticker_item(item: dict) -> bool:
    category = _normalize_sticker_text(_item_field(item, "Category"))
    if not category or category in {"默认表情", "最近使用", "推荐表情", "热门表情", "搜索表情"}:
        return False
    mode = _item_field(item, "Mode").casefold()
    return bool(_item_field(item, "Hash")) if mode == "visual" else bool(_item_field(item, "Name"))


def _split_long_piece(text: str, target: int) -> list[str]:
    if len(text) <= target:
        return [text]
    sentences = [
        value.strip()
        for value in re.findall(r".*?(?:[。！？!?…]+|$)", text, flags=re.DOTALL)
        if value.strip()
    ]
    values: list[str] = []
    current = ""
    for sentence in sentences:
        chunks = (
            [sentence[index : index + target] for index in range(0, len(sentence), target)]
            if len(sentence) > target
            else [sentence]
        )
        for chunk in chunks:
            if current and len(current) + len(chunk) > target:
                values.append(current.strip())
                current = ""
            current += chunk
    if current.strip():
        values.append(current.strip())
    return values


def _prefixed(text: str, prefix: str) -> str:
    value = f"{prefix}{text.strip()}"
    if not value.strip() or len(value) > 2_000 or "\x00" in value:
        raise AutoReplySegmentsError("添加前缀后的自动回复为空、无效或超过 2000 字。")
    return value


def _echo_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _file_echo_key(text: str) -> str:
    value = str(text).strip().replace("\\", "/")
    value = re.sub(r"^\s*(?:\[文件\]|文件)\s*[:：]?\s*", "", value)
    value = value.splitlines()[-1].strip() if value else ""
    return value.rsplit("/", 1)[-1].strip().casefold()


def _truncated_echo_prefix(key: str) -> str:
    match = re.search(r"(?:…|\.{3})$", key)
    if not match:
        return ""
    prefix = key[: match.start()].rstrip()
    return prefix if len(prefix) >= 12 else ""


def _clean_image_prompt(text: str) -> str:
    value = text.strip(" ：:，,。！？!?")
    value = re.sub(r"(?:的)?(?:图片|图像|图|照片)$", "", value).strip()
    return value


def _is_voice_placeholder(text: str) -> bool:
    value = re.sub(r"\s+", "", text)
    return bool(
        re.fullmatch(r"(?:\[|【)?语音(?:\]|】)?(?:\d+(?:[\"'”″]?秒?)?)?", value)
    )
