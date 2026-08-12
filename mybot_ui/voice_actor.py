from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any

from .chat_engine import ChatModelClient, ModelConfig


EMOTIONS = frozenset({
    "elation", "amusement", "enthusiasm", "determination", "pride",
    "contentment", "affection", "relief", "contemplation", "confusion",
    "surprise", "awe", "longing", "arousal", "anger", "fear", "disgust",
    "bitterness", "sadness", "shame", "helplessness",
})
STYLES = frozenset({"singing", "shouting", "whispering"})
SPEEDS = frozenset({"very_slow", "slow", "normal", "fast", "very_fast"})
PITCHES = frozenset({"low", "normal", "high"})
EXPRESSIVENESS = frozenset({"low", "normal", "high"})
PAUSES = frozenset({"none", "pause", "long_pause"})
SFX = frozenset({
    "cough", "laughter", "crying", "screaming", "burping", "humming",
    "sigh", "sniff", "sneeze",
})
INTENSITIES = frozenset({"restrained", "natural", "dramatic"})

_SFX_CUES = {
    "cough": ("咳", "ahem"),
    "laughter": ("哈", "呵呵", "嘿嘿", "笑"),
    "crying": ("呜", "哭"),
    "screaming": ("啊", "呀"),
    "burping": ("嗝", "burp"),
    "humming": ("嗯", "哼", "hmm"),
    "sigh": ("唉", "哎", "呼", "叹"),
    "sniff": ("吸鼻", "抽鼻", "sniff"),
    "sneeze": ("阿嚏", "喷嚏", "achoo"),
}


class VoicePerformanceError(ValueError):
    pass


@dataclass(frozen=True)
class VoicePerformanceSegment:
    text: str
    emotion: str = ""
    style: str = ""
    speed: str = "normal"
    pitch: str = "normal"
    expressiveness: str = "normal"
    pause_after: str = "none"
    sfx: str = ""

    def higgs_input(self) -> str:
        tags: list[str] = []
        if self.emotion:
            tags.append(f"<|emotion:{self.emotion}|>")
        if self.style:
            tags.append(f"<|style:{self.style}|>")
        if self.speed != "normal":
            tags.append(f"<|prosody:speed_{self.speed}|>")
        if self.pitch != "normal":
            tags.append(f"<|prosody:pitch_{self.pitch}|>")
        if self.expressiveness != "normal":
            tags.append(f"<|prosody:expressive_{self.expressiveness}|>")
        if self.sfx:
            tags.append(f"<|sfx:{self.sfx}|>")
        value = "".join(tags) + self.text
        if self.pause_after != "none":
            value += f"<|prosody:{self.pause_after}|>"
        return value


@dataclass(frozen=True)
class VoicePerformancePlan:
    segments: tuple[VoicePerformanceSegment, ...]

    def higgs_inputs(self) -> tuple[str, ...]:
        return tuple(segment.higgs_input() for segment in self.segments)

    def direction(self, base_style: str = "") -> str:
        labels: list[str] = []
        for index, segment in enumerate(self.segments, 1):
            parts = [
                value
                for value in (
                    f"情绪={segment.emotion}" if segment.emotion else "",
                    f"风格={segment.style}" if segment.style else "",
                    f"语速={segment.speed}" if segment.speed != "normal" else "",
                    f"音高={segment.pitch}" if segment.pitch != "normal" else "",
                    (
                        f"表现力={segment.expressiveness}"
                        if segment.expressiveness != "normal"
                        else ""
                    ),
                )
                if value
            ]
            if parts:
                labels.append(f"第{index}段" + "、".join(parts))
        values = [
            value.strip("；; ")
            for value in (base_style, "；".join(labels))
            if value.strip()
        ]
        return "；".join(values)[:500]


class HiggsVoiceActor:
    def __init__(self, client: ChatModelClient) -> None:
        self.client = client

    def plan(
        self,
        primary: ModelConfig,
        backup: ModelConfig | None,
        *,
        user_message: str,
        reply_text: str,
        direction: str = "",
        intensity: str = "natural",
        base_speed: float = 1.0,
        timeout: int = 25,
    ) -> VoicePerformancePlan:
        intensity = intensity if intensity in INTENSITIES else "natural"
        messages = voice_actor_messages(
            user_message=user_message,
            reply_text=reply_text,
            direction=direction,
            intensity=intensity,
            base_speed=base_speed,
        )
        raw = self.client.generate_with_fallback(
            replace(primary, temperature=0.2),
            replace(backup, temperature=0.2) if backup else None,
            messages,
            timeout=timeout,
        )
        return parse_voice_performance(raw, reply_text)


def voice_actor_messages(
    *,
    user_message: str,
    reply_text: str,
    direction: str,
    intensity: str,
    base_speed: float,
) -> list[dict[str, str]]:
    prompt = (
        "你是配音导演，只编排台词表演，不改写台词。根据用户消息和回复的情绪曲线，"
        "把回复切成1到4个连续片段，并为每段选择Higgs TTS 3控制项。所有片段text按顺序"
        "拼接后必须与原回复完全一致（仅允许空白差异）；不得增加语气词、拟声词或解释。"
        "情绪可选：" + ",".join(sorted(EMOTIONS)) + "；"
        "style可选：空、singing、shouting、whispering；"
        "speed可选：very_slow、slow、normal、fast、very_fast；"
        "pitch可选：low、normal、high；expressiveness可选：low、normal、high；"
        "pause_after可选：none、pause、long_pause；"
        "sfx可选：空、" + ",".join(sorted(SFX)) + "。"
        "只有原文已包含对应的笑声、叹气、咳嗽等文字线索时才能选择sfx。"
        "输出严格JSON，不要Markdown："
        '{"segments":[{"text":"原文片段","emotion":"affection",'
        '"style":"","speed":"normal","pitch":"normal",'
        '"expressiveness":"high","pause_after":"none","sfx":""}]}'
    )
    task = (
        f"表演强度：{intensity}\n基础语速：{base_speed:.1f}\n"
        f"额外方向：{direction.strip() or '无'}\n"
        f"用户消息：{user_message.strip()}\n原回复：{reply_text}"
    )
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": task},
    ]


def parse_voice_performance(raw: str, original_text: str) -> VoicePerformancePlan:
    payload = _extract_json(raw)
    segments_value = payload.get("segments")
    if not isinstance(segments_value, list) or not 1 <= len(segments_value) <= 4:
        raise VoicePerformanceError("配音计划必须包含1到4个片段。")
    segments: list[VoicePerformanceSegment] = []
    for item in segments_value:
        if not isinstance(item, dict):
            raise VoicePerformanceError("配音计划片段格式无效。")
        text = str(item.get("text", ""))
        if not text.strip():
            raise VoicePerformanceError("配音计划包含空片段。")
        emotion = _choice(
            item.get("emotion"), EMOTIONS, empty_values={"", "neutral", "normal"}
        )
        style = _choice(item.get("style"), STYLES, empty_values={"", "normal"})
        speed = _choice(item.get("speed"), SPEEDS, default="normal")
        pitch = _choice(item.get("pitch"), PITCHES, default="normal")
        expressiveness = _choice(
            item.get("expressiveness"), EXPRESSIVENESS, default="normal"
        )
        pause_after = _choice(item.get("pause_after"), PAUSES, default="none")
        sfx = _choice(item.get("sfx"), SFX, empty_values={"", "none"})
        if sfx and not any(cue.casefold() in text.casefold() for cue in _SFX_CUES[sfx]):
            sfx = ""
        segments.append(VoicePerformanceSegment(
            text=text,
            emotion=emotion,
            style=style,
            speed=speed,
            pitch=pitch,
            expressiveness=expressiveness,
            pause_after=pause_after,
            sfx=sfx,
        ))
    planned_text = "".join(segment.text for segment in segments)
    if _without_whitespace(planned_text) != _without_whitespace(original_text):
        if _spoken_text_key(planned_text) != _spoken_text_key(original_text):
            raise VoicePerformanceError("配音计划改写了原回复。")
        segments = _restore_original_segment_texts(segments, original_text)
    return VoicePerformancePlan(tuple(segments))


def fallback_voice_performance(
    text: str,
    *,
    intensity: str = "natural",
    base_speed: float = 1.0,
) -> VoicePerformancePlan:
    folded = text.casefold()
    if any(value in folded for value in ("哈哈", "呵呵", "嘿嘿")):
        emotion = "amusement"
    elif any(value in text for value in ("抱歉", "难过", "遗憾")):
        emotion = "sadness"
    elif any(value in text for value in ("谢谢", "想你", "陪你", "在呢")):
        emotion = "affection"
    elif "！" in text or "!" in text:
        emotion = "enthusiasm"
    elif "？" in text or "?" in text:
        emotion = "contemplation"
    else:
        emotion = "contentment"
    if base_speed <= 0.75:
        speed = "very_slow"
    elif base_speed < 0.95:
        speed = "slow"
    elif base_speed >= 1.3:
        speed = "very_fast"
    elif base_speed > 1.05:
        speed = "fast"
    else:
        speed = "normal"
    expressive = {
        "restrained": "low", "natural": "normal", "dramatic": "high"
    }.get(intensity, "normal")
    return VoicePerformancePlan((VoicePerformanceSegment(
        text=text,
        emotion=emotion,
        speed=speed,
        expressiveness=expressive,
    ),))


def _extract_json(raw: str) -> dict[str, Any]:
    value = str(raw or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end < start:
        raise VoicePerformanceError("配音模型没有返回JSON。")
    try:
        payload = json.loads(value[start:end + 1])
    except json.JSONDecodeError as exc:
        raise VoicePerformanceError("配音模型返回了无效JSON。") from exc
    if not isinstance(payload, dict):
        raise VoicePerformanceError("配音模型返回的顶层结构无效。")
    return payload


def _choice(
    value: Any,
    allowed: frozenset[str],
    *,
    default: str = "",
    empty_values: set[str] | None = None,
) -> str:
    normalized = str(value or "").strip().lower()
    if empty_values and normalized in empty_values:
        return ""
    return normalized if normalized in allowed else default


def _without_whitespace(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _spoken_text_key(value: str) -> str:
    # Tolerate punctuation and whitespace added by the director model. They do
    # not change the spoken wording, and the original text is restored below.
    return re.sub(r"[\s\W_]+", "", str(value or ""), flags=re.UNICODE).casefold()


def _restore_original_segment_texts(
    segments: list[VoicePerformanceSegment],
    original_text: str,
) -> list[VoicePerformanceSegment]:
    restored: list[VoicePerformanceSegment] = []
    cursor = 0
    significant_seen = 0
    significant_targets: list[int] = []
    total = 0
    for segment in segments:
        total += len(_spoken_text_key(segment.text))
        significant_targets.append(total)
    for index, segment in enumerate(segments):
        if index == len(segments) - 1:
            end = len(original_text)
        else:
            target = significant_targets[index]
            end = cursor
            while end < len(original_text) and significant_seen < target:
                char = original_text[end]
                end += 1
                if _spoken_text_key(char):
                    significant_seen += 1
            while end < len(original_text) and not _spoken_text_key(original_text[end]):
                end += 1
        restored.append(VoicePerformanceSegment(
            text=original_text[cursor:end],
            emotion=segment.emotion,
            style=segment.style,
            speed=segment.speed,
            pitch=segment.pitch,
            expressiveness=segment.expressiveness,
            pause_after=segment.pause_after,
            sfx=segment.sfx,
        ))
        cursor = end
    return restored
