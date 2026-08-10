from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .chat_engine import ChatModelClient, ModelConfig


_DELEGATE_PATTERN = re.compile(
    r"(?:"
    r"代码|项目|仓库|脚本|程序|日志|报错|bug|接口|配置文件|数据库|终端|命令行|"
    r"修改文件|创建文件|删除文件|整理文件|下载|安装|部署|编译|运行测试|"
    r"排查|调试|修复|实现功能|开发|重构|写个工具|自动化|"
    r"联网搜索|深入研究|查资料|分析文档"
    r")",
    re.IGNORECASE,
)
_EXPLICIT_AGENT_PATTERN = re.compile(
    r"(?:"
    r"(?:用|使用|让|叫|通过|调度|调用).{0,10}(?:agent|智能体|代理|工具|codex)|"
    r"(?:agent|智能体|代理|工具|codex).{0,10}(?:查|搜|执行|处理|完成|工作|做)|"
    r"联网|上网搜索|在线查询"
    r")",
    re.IGNORECASE,
)
_ATTACHMENT_TASK_PATTERN = re.compile(
    r"(?:(?:改|修改|编辑|处理|整理|转换|转成|翻译|分析|检查|修复|完善|总结|提取).{0,16}"
    r"(?:刚才|这个|那个|收到的|发的)?(?:文件|文档|表格|PPT|PDF)|"
    r"(?:刚才|这个|那个|收到的|发的)?(?:文件|文档|表格|PPT|PDF).{0,16}"
    r"(?:改|修改|编辑|处理|整理|转换|转成|翻译|分析|检查|修复|完善|总结|提取))",
    re.IGNORECASE,
)
_FILE_CREATION_PATTERN = re.compile(
    r"(?:"
    r"(?:写|生成|创建|整理|导出|做).{0,20}(?:md|markdown|txt|word|pdf|文档|文件).{0,20}(?:发给我|给我|发送)|"
    r"(?:写到|保存到|导出成|生成成).{0,8}(?:md|markdown|txt|word|pdf|文档|文件)|"
    r"(?:生成|创建|做)(?:一个|份)?文件(?:发给我|给我|发送)"
    r")",
    re.IGNORECASE,
)
_LIVE_SUBJECT = r"(?:天气|气温|降雨|空气质量|几点|当前时间|实时时间|新闻|路况|航班|汇率|股价|金价|油价)"
_LIVE_QUERY_PATTERN = re.compile(
    rf"(?:"
    rf"(?:查|搜|搜索|查询|看看|看下|获取|告诉我).{{0,24}}{_LIVE_SUBJECT}|"
    rf"{_LIVE_SUBJECT}.{{0,24}}(?:吗|么|呢|怎么样|如何|多少|有没有|会不会|是什么)|"
    rf"(?:几点了|现在几点)"
    rf")",
    re.IGNORECASE,
)
_LOCAL_MEDIA_PATTERN = re.compile(
    r"(?:发|发送|生成|画|做).{0,12}(?:图片|照片|表情|表情包|语音)",
    re.IGNORECASE,
)
MODEL_DELEGATE_MARKER = "<MYBOT_DELEGATE_CODEX>"
MODEL_DELEGATE_INSTRUCTION = (
    "你可以把需要实际工具的任务交给后台 Codex。若当前请求需要实时或最新信息、联网查询、"
    "代码/文件/终端操作、调试研究，或者用户明确要求使用 agent、工具或 Codex，"
    f"不要声称没有工具，只回复精确标记 {MODEL_DELEGATE_MARKER}，不得添加其他文字。"
    "普通聊天和仅凭已有知识即可可靠回答的问题照常直接回复；不要向用户提及这个内部标记。"
)


class CodexTaskRouter:
    @staticmethod
    def should_delegate(content: str) -> bool:
        text = content.strip()
        if not text or len(text) > 12_000:
            return False
        if _LOCAL_MEDIA_PATTERN.search(text):
            return False
        return bool(
            _DELEGATE_PATTERN.search(text)
            or _ATTACHMENT_TASK_PATTERN.search(text)
            or _FILE_CREATION_PATTERN.search(text)
            or _EXPLICIT_AGENT_PATTERN.search(text)
            or _LIVE_QUERY_PATTERN.search(text)
        )

    @staticmethod
    def model_instruction() -> str:
        return MODEL_DELEGATE_INSTRUCTION

    @staticmethod
    def model_requested_delegate(reply: str) -> bool:
        return reply.strip() == MODEL_DELEGATE_MARKER

    @staticmethod
    def acknowledgement(content: str, *, is_group: bool = False) -> str:
        if _LIVE_QUERY_PATTERN.search(content):
            choices = ("稍等，我去看一下", "等我一下，我去查查")
        elif re.search(r"日志|报错|bug|排查|调试|修复", content, re.IGNORECASE):
            choices = ("稍等，我先看一下", "我去看看，等我一会儿")
        elif re.search(r"代码|项目|脚本|程序|实现|开发|重构", content, re.IGNORECASE):
            choices = ("稍等，我去弄一下", "行，我先去看看")
        elif is_group:
            choices = ("稍等，我去看一下", "行，我先去弄一下")
        else:
            choices = ("稍等，我去看一下", "行，我先去弄一下", "等我一会儿，我去看看")
        digest = hashlib.blake2s(content.strip().encode("utf-8"), digest_size=2).digest()
        return choices[int.from_bytes(digest, "big") % len(choices)]


REVIEW_PROMPT = """判断一个已经由 Codex 完成的任务是否值得沉淀为 MyBot 通用快捷能力。
只有满足全部条件才 reusable=true：同一流程未来至少可用于三个不同请求；通过参数变化即可复用；方法稳定；不依赖当前联系人、私聊内容、密钥、一次性路径或过期实时数值；可以写成 Python 脚本并用离线单元测试验证。
普通问答、单次修复、特定项目补丁、实时查询、需要人工判断的任务必须为 false。
只输出 JSON：{"reusable":true或false,"reason":"简短原因","name":"通用能力名称","triggers":["触发短语"]}。"""


@dataclass(frozen=True)
class ReusableDecision:
    reusable: bool
    reason: str = ""
    name: str = ""
    triggers: tuple[str, ...] = ()


class ReusableTaskReviewer:
    def __init__(self, client: ChatModelClient) -> None:
        self.client = client

    def review(
        self,
        *,
        primary: ModelConfig,
        backup: ModelConfig | None,
        request: str,
        result: str,
    ) -> ReusableDecision:
        payload = json.dumps({
            "request": request[:4_000],
            "result": result[:4_000],
        }, ensure_ascii=False)
        response = self.client.generate_with_fallback(
            primary,
            backup,
            [
                {"role": "system", "content": REVIEW_PROMPT},
                {"role": "user", "content": payload},
            ],
        )
        data = _json_object(response)
        triggers = tuple(
            str(item).strip()[:80]
            for item in data.get("triggers", [])[:16]
            if str(item).strip()
        ) if isinstance(data.get("triggers"), list) else ()
        return ReusableDecision(
            reusable=data.get("reusable") is True,
            reason=str(data.get("reason", "")).strip()[:400],
            name=str(data.get("name", "")).strip()[:80],
            triggers=triggers,
        )


def _json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("通用能力审核没有返回 JSON")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("通用能力审核返回值无效")
    return data
