from __future__ import annotations

import json
import tempfile
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


MAX_VOICE_BYTES = 32 * 1024 * 1024
MAX_VOICE_LIST_BYTES = 1024 * 1024


@dataclass(frozen=True)
class VoiceApiConfig:
    base_url: str
    model: str
    api_key: str
    voice: str
    provider: str = "openai"
    speed: float = 1.0
    instructions: str = ""


def voice_api_endpoint(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("语音 API 地址必须是有效的 HTTP 或 HTTPS 地址。")
    if parsed.path.rstrip("/").endswith("/audio/speech"):
        return value
    if parsed.path.rstrip("/").endswith("/v1"):
        return f"{value}/audio/speech"
    return f"{value}/v1/audio/speech"


def boson_voice_list_endpoint(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("语音 API 地址必须是有效的 HTTP 或 HTTPS 地址。")
    path = parsed.path.rstrip("/")
    if path.endswith("/audio/voices"):
        return value
    if path.endswith("/audio/speech"):
        return f"{value[:-len('/audio/speech')]}/audio/voices"
    if path.endswith("/v1"):
        return f"{value}/audio/voices"
    return f"{value}/v1/audio/voices"


def list_boson_voices(
    base_url: str,
    api_key: str,
    *,
    timeout: float = 30.0,
) -> tuple[str, ...]:
    token = str(api_key or "").strip()
    if not token:
        raise ValueError("请配置 Boson API 密钥。")
    request = urllib.request.Request(
        boson_voice_list_endpoint(base_url),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "MyBot/2.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_VOICE_LIST_BYTES + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(2_000).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Boson 音色接口返回 {error.code}：{detail or error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"无法连接 Boson 音色接口：{error.reason}") from error
    if len(raw) > MAX_VOICE_LIST_BYTES:
        raise RuntimeError("Boson 音色列表响应超过 1 MB。")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Boson 音色接口返回了无效 JSON。") from error
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("Boson 音色接口响应缺少 data 列表。")
    voices: list[str] = []
    for item in data:
        voice = (
            str(item.get("voice") or item.get("voice_id") or "").strip()
            if isinstance(item, dict)
            else ""
        )
        if voice and voice not in voices:
            voices.append(voice)
    return tuple(voices)


def local_voice_stream_endpoint(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("本地语音服务地址必须是有效的 HTTP 或 HTTPS 地址。")
    if parsed.hostname.lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("本地语音服务只允许使用本机回环地址。")
    if parsed.path.rstrip("/").endswith("/audio/speech/stream"):
        return value
    if parsed.path.rstrip("/").endswith("/v1"):
        return f"{value}/audio/speech/stream"
    return f"{value}/v1/audio/speech/stream"


def synthesize_voice_file(
    config: VoiceApiConfig,
    text: str,
    output_dir: Path,
    *,
    timeout: float = 120.0,
) -> Path:
    content = str(text or "").strip()
    if not content:
        raise ValueError("语音内容不能为空。")
    if not config.model.strip():
        raise ValueError("请配置语音 API 模型。")
    if not config.voice.strip():
        raise ValueError("请选择语音 API 音色。")
    if not config.api_key.strip():
        raise ValueError("请配置语音 API 密钥。")

    payload = {
        "model": config.model.strip(),
        "input": content,
        "voice": config.voice.strip(),
        "response_format": "wav",
    }
    if config.provider.strip().lower() == "boson":
        payload["stream"] = False
    else:
        payload["speed"] = min(2.0, max(0.5, float(config.speed)))
        if config.instructions.strip():
            payload["instructions"] = config.instructions.strip()
    request = urllib.request.Request(
        voice_api_endpoint(config.base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key.strip()}",
            "Content-Type": "application/json",
            "Accept": "audio/wav, audio/mpeg, application/octet-stream",
            "User-Agent": "MyBot/2.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            audio = response.read(MAX_VOICE_BYTES + 1)
            content_type = str(response.headers.get("Content-Type", "")).lower()
    except urllib.error.HTTPError as error:
        detail = error.read(2_000).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"语音 API 返回 {error.code}：{detail or error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"无法连接语音 API：{error.reason}") from error

    if not audio:
        raise RuntimeError("语音 API 返回了空音频。")
    if len(audio) > MAX_VOICE_BYTES:
        raise RuntimeError("语音 API 返回的音频超过 32 MB。")
    if "json" in content_type or audio.lstrip().startswith((b"{", b"[")):
        detail = audio[:2_000].decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"语音 API 未返回音频：{detail}")

    suffix = ".mp3" if "mpeg" in content_type or audio.startswith(b"ID3") else ".wav"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="mybot-voice-",
        suffix=suffix,
        dir=output_dir,
        delete=False,
    ) as stream:
        stream.write(audio)
        return Path(stream.name)


def synthesize_voice_performance(
    config: VoiceApiConfig,
    inputs: tuple[str, ...] | list[str],
    output_dir: Path,
    *,
    timeout: float = 120.0,
) -> Path:
    segments = tuple(
        str(value or "").strip()
        for value in inputs
        if str(value or "").strip()
    )
    if not segments:
        raise ValueError("配音表演计划不能为空。")
    if len(segments) == 1:
        return synthesize_voice_file(
            config, segments[0], output_dir, timeout=timeout
        )

    paths: list[Path] = []
    try:
        for segment in segments:
            paths.append(
                synthesize_voice_file(
                    config, segment, output_dir, timeout=timeout
                )
            )
        return _merge_wav_files(paths, output_dir)
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def _merge_wav_files(paths: list[Path], output_dir: Path) -> Path:
    if not paths:
        raise ValueError("没有可合并的语音片段。")
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix="mybot-voice-performance-",
        suffix=".wav",
        dir=output_dir,
        delete=False,
    )
    merged = Path(temporary.name)
    temporary.close()
    expected: tuple[int, int, int, str] | None = None
    try:
        with wave.open(str(merged), "wb") as writer:
            for path in paths:
                with wave.open(str(path), "rb") as reader:
                    current = (
                        reader.getnchannels(),
                        reader.getsampwidth(),
                        reader.getframerate(),
                        reader.getcomptype(),
                    )
                    if expected is None:
                        expected = current
                        writer.setnchannels(current[0])
                        writer.setsampwidth(current[1])
                        writer.setframerate(current[2])
                        writer.setcomptype(current[3], reader.getcompname())
                    elif current != expected:
                        raise RuntimeError("语音片段格式不一致，无法合并。")
                    writer.writeframes(reader.readframes(reader.getnframes()))
        return merged
    except Exception:
        merged.unlink(missing_ok=True)
        raise
