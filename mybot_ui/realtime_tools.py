from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .operation_log import operations


_WEATHER_SUBJECT = re.compile(r"天气|气温|降雨|空气质量")
_WEATHER_QUERY_CONTEXT = re.compile(r"天气|气温")
_WEATHER_FOLLOW_UP = re.compile(
    r"^(?:那|那查查|查查|看看)?(?:明天|后天|大后天|未来(?:几天|\d+天))(?:的)?(?:呢|怎么样|如何|天气呢?)?[？?。！!]*$"
)
_TIME_SUBJECT = re.compile(r"几点|当前时间|实时时间|现在时间")
_TOOL_FOLLOW_UP = re.compile(r"agent|智能体|代理|工具|codex|联网|上网", re.IGNORECASE)
_LOCATION_NOISE = re.compile(
    r"^(?:请|麻烦|你|帮我|给我|用agent|使用agent|查|查询|搜|搜索|看看|看下|告诉我)+"
    r"|(?:今天|明天|现在|当前|实时|最新|的)+$",
    re.IGNORECASE,
)

_WEATHER_DESCRIPTIONS = {
    "113": "晴",
    "116": "晴间多云",
    "119": "多云",
    "122": "阴",
    "143": "有雾",
    "176": "附近有零星降雨",
    "179": "附近有零星降雪",
    "182": "雨夹雪",
    "185": "冻毛毛雨",
    "200": "局部雷雨",
    "227": "风吹雪",
    "230": "暴风雪",
    "248": "有雾",
    "260": "冻雾",
    "263": "零星小雨",
    "266": "小雨",
    "281": "冻雨",
    "284": "较强冻雨",
    "293": "局部小雨",
    "296": "小雨",
    "299": "局部中雨",
    "302": "中雨",
    "305": "局部大雨",
    "308": "大雨",
    "311": "冻雨",
    "314": "强冻雨",
    "317": "雨夹雪",
    "320": "较强雨夹雪",
    "323": "局部小雪",
    "326": "小雪",
    "329": "局部中雪",
    "332": "中雪",
    "335": "局部大雪",
    "338": "大雪",
    "350": "冰粒",
    "353": "零星阵雨",
    "356": "中到大阵雨",
    "359": "暴雨",
    "362": "零星雨夹雪",
    "365": "中到大雨夹雪",
    "368": "零星阵雪",
    "371": "中到大阵雪",
    "374": "零星冰粒",
    "377": "强冰粒",
    "386": "局部雷阵雨",
    "389": "强雷阵雨",
    "392": "局部雷阵雪",
    "395": "强雷阵雪",
}


@dataclass(frozen=True)
class RealtimeToolRequest:
    kind: str
    query: str


def detect_realtime_request(content: str, conversation_context: str = "") -> RealtimeToolRequest | None:
    text = content.strip()
    if _WEATHER_SUBJECT.search(text):
        return RealtimeToolRequest("weather", text)
    if _TIME_SUBJECT.search(text):
        return RealtimeToolRequest("time", text)
    if _WEATHER_FOLLOW_UP.fullmatch(text):
        prior = _latest_context_subject(conversation_context, _WEATHER_QUERY_CONTEXT)
        if prior:
            return RealtimeToolRequest("weather", f"{prior} {text}")
    if not _TOOL_FOLLOW_UP.search(text):
        return None
    prior = _latest_context_subject(conversation_context, _WEATHER_QUERY_CONTEXT)
    if prior:
        return RealtimeToolRequest("weather", prior)
    prior = _latest_context_subject(conversation_context, _TIME_SUBJECT)
    if prior:
        return RealtimeToolRequest("time", prior)
    return None


def _latest_context_subject(conversation_context: str, pattern: re.Pattern[str]) -> str:
    for line in reversed(conversation_context.splitlines()):
        prior = re.sub(r"^[^:：]{1,20}[:：]\s*", "", line).strip()
        if pattern.search(prior):
            return prior
    return ""


class RealtimeToolExecutor:
    def execute(self, request: RealtimeToolRequest) -> str:
        span = operations.start("tool", "realtime_tool_run", details={
            "kind": request.kind,
            "query": request.query,
        })
        try:
            if request.kind == "weather":
                result = self._weather(request.query)
            elif request.kind == "time":
                result = self._time()
            else:
                raise ValueError(f"未知实时工具：{request.kind}")
            operations.finish(span, success=True, result={"kind": request.kind, "reply_length": len(result)})
            return result
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def _weather(self, query: str) -> str:
        location = _weather_location(query)
        encoded = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded}?format=j1"
        request = urllib.request.Request(url, headers={"User-Agent": "MyBot/2.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        current = (payload.get("current_condition") or [{}])[0]
        operations.event("tool", "weather_source_observation", {
            "location": location,
            "observation": _observation_text(current),
        })
        return _weather_reply(payload, location, query=query)

    @staticmethod
    def _time() -> str:
        shanghai = timezone(timedelta(hours=8), name="Asia/Shanghai")
        now = datetime.now(shanghai)
        weekdays = "一二三四五六日"
        period = (
            "凌晨" if now.hour < 6 else
            "早上" if now.hour < 11 else
            "中午" if now.hour < 14 else
            "下午" if now.hour < 18 else
            "晚上"
        )
        minute = f"{now.minute}分" if now.minute else "整"
        return f"现在{period}{now.hour % 12 or 12}点{minute}，今天星期{weekdays[now.weekday()]}"


def _weather_location(query: str) -> str:
    match = _WEATHER_SUBJECT.search(query)
    prefix = query[: match.start()] if match else query
    # WeChat group mentions can contain a narrow/em space (U+2005) between
    # the mentioned name and the actual request.  Remove those mention tokens
    # before extracting the location so replies never echo ``@圆子``.
    prefix = re.sub(r"^(?:@[^\s\u2005，,。！？!?]{1,20}[\s\u2005]+)+", "", prefix)
    prefix = re.sub(r"^[^:：]{1,20}[:：]\s*", "", prefix).strip(" ，,。！？!?：:")
    previous = None
    while prefix and prefix != previous:
        previous = prefix
        prefix = _LOCATION_NOISE.sub("", prefix).strip(" ，,。！？!?：:")
    prefix = re.sub(r"今天|明天|后天|大后天|未来(?:几天|\d+天)", "", prefix).strip()
    return prefix[-30:] if len(prefix) >= 2 else "上海"


def _weather_reply(payload: dict[str, Any], location: str, *, query: str = "") -> str:
    current_values = payload.get("current_condition") or []
    weather_values = payload.get("weather") or []
    if not current_values or not weather_values:
        raise ValueError("天气服务没有返回当前天气或今日预报")
    day_offset, day_label = _forecast_day(query)
    if day_offset:
        if len(weather_values) <= day_offset:
            raise ValueError(f"天气服务没有返回{day_label}预报")
        forecast = weather_values[day_offset]
        hourly = forecast.get("hourly") or []
        rain_chances = _rain_chances(hourly)
        description = _forecast_description(hourly)
        chance = max(rain_chances) if rain_chances else 0
        return (
            f"我刚看了下，{location}{day_label}大概 {forecast.get('mintempC', '?')} 到 "
            f"{forecast.get('maxtempC', '?')} 度，{_natural_weather_description(description)}"
            f"{_rain_comment(chance)}"
        )
    current = current_values[0]
    today = weather_values[0]
    hourly = today.get("hourly") or []
    rain_chances = _rain_chances(hourly)
    description = _WEATHER_DESCRIPTIONS.get(str(current.get("weatherCode", "")))
    if not description:
        values = current.get("weatherDesc") or []
        description = str(values[0].get("value", "天气状况未知")) if values else "天气状况未知"
    chance = max(rain_chances) if rain_chances else 0
    temperature = str(current.get("temp_C", "?"))
    feels_like = str(current.get("FeelsLikeC", "?"))
    feels = "体感也差不多" if feels_like == temperature else f"体感大概 {feels_like} 度"
    humidity = _humidity_comment(current.get("humidity"))
    return (
        f"我刚看了下，{location}现在 {temperature} 度，{feels}，"
        f"{_natural_weather_description(description)}{humidity}，"
        f"今天大概 {today.get('mintempC', '?')} 到 {today.get('maxtempC', '?')} 度"
        f"{_rain_comment(chance)}"
    )


def _forecast_day(query: str) -> tuple[int, str]:
    if "大后天" in query:
        return 3, "大后天"
    if "后天" in query:
        return 2, "后天"
    if "明天" in query:
        return 1, "明天"
    return 0, "今天"


def _rain_chances(hourly: list[dict[str, Any]]) -> list[int]:
    return [
        int(str(item.get("chanceofrain", "0")))
        for item in hourly
        if str(item.get("chanceofrain", "0")).isdigit()
    ]


def _forecast_description(hourly: list[dict[str, Any]]) -> str:
    if not hourly:
        return "天气情况暂不明确"
    item = hourly[len(hourly) // 2]
    description = _WEATHER_DESCRIPTIONS.get(str(item.get("weatherCode", "")))
    if description:
        return description
    values = item.get("weatherDesc") or []
    return str(values[0].get("value", "天气情况暂不明确")) if values else "天气情况暂不明确"


def _natural_weather_description(description: str) -> str:
    replacements = {
        "附近有零星降雨": "附近可能会飘点雨",
        "附近有零星降雪": "附近可能会飘点雪",
        "天气情况暂不明确": "天气变化还不太确定",
    }
    value = replacements.get(description, description)
    if value.startswith(("有", "可能", "附近")):
        return value
    return f"会有{value}" if value not in {"晴", "多云", "阴"} else value


def _rain_comment(chance: int) -> str:
    if chance >= 70:
        return "，下雨概率挺高的，出门记得带伞"
    if chance >= 35:
        return "，可能会下雨，最好顺手带把伞"
    return ""


def _humidity_comment(value: Any) -> str:
    try:
        humidity = int(str(value))
    except (TypeError, ValueError):
        return ""
    if humidity >= 85:
        return "，湿度挺高，会有点闷"
    return ""


def _observation_text(current: dict[str, Any]) -> str:
    local_value = str(current.get("localObsDateTime") or "").strip()
    if local_value:
        try:
            value = datetime.strptime(local_value, "%Y-%m-%d %I:%M %p")
            return f"当地时间 {value:%m月%d日 %H:%M} 的实时观测"
        except ValueError:
            return f"在当地时间 {local_value} 的实时观测"
    utc_value = str(current.get("observation_time") or "").strip()
    if utc_value:
        try:
            value = datetime.strptime(utc_value, "%I:%M %p").replace(tzinfo=timezone.utc)
            beijing = value.astimezone(timezone(timedelta(hours=8)))
            return f"在北京时间 {beijing:%H:%M} 的实时观测"
        except ValueError:
            return f"刚刚返回的实时观测（原始时间 {utc_value} UTC）"
    return ""
