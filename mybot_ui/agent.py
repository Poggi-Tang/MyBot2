from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .catalog import TOOL_MAP, missing_arguments


@dataclass
class ToolCall:
    function: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class AgentPlan:
    calls: list[ToolCall] = field(default_factory=list)
    reply: str = ""
    missing: list[str] = field(default_factory=list)


class DialogueAgent:
    """Small local planner that turns Chinese dialogue into SDK tool calls.

    It deliberately emits structured calls instead of directly touching WeChat,
    so the UI can show plans, enforce confirmations and record every result.
    """

    def __init__(self) -> None:
        self.last_target = ""

    def plan(self, text: str) -> AgentPlan:
        text = text.strip()
        if not text:
            return AgentPlan(reply="请输入要执行的操作。")

        direct = re.fullmatch(r"(?:执行|调用)\s*([A-Za-z0-9_]+)\s*(\{.*\})?", text, re.S)
        if direct:
            function = direct.group(1)
            if function not in TOOL_MAP:
                return AgentPlan(reply=f"功能目录中没有 {function}。")
            try:
                arguments = json.loads(direct.group(2) or "{}")
            except json.JSONDecodeError as exc:
                return AgentPlan(reply=f"JSON 参数格式错误：{exc}")
            return self._finish([ToolCall(function, arguments, "按函数名直接执行")])

        parts = [part.strip() for part in re.split(r"(?:然后|接着|并且|；|;)", text) if part.strip()]
        calls: list[ToolCall] = []
        unknown: list[str] = []
        for part in parts:
            call = self._plan_one(part)
            if call:
                calls.append(call)
            else:
                unknown.append(part)
        if not calls:
            return AgentPlan(reply="我还无法确定要调用哪个功能。可以说“列出群聊”“给 MyBot测试群2 发消息：你好”或直接输入“执行 SendMessage {...}”。")
        plan = self._finish(calls)
        if unknown:
            plan.reply += f"\n未识别片段：{'；'.join(unknown)}"
        return plan

    def _finish(self, calls: list[ToolCall]) -> AgentPlan:
        missing: list[str] = []
        for call in calls:
            missing.extend(f"{call.function}.{name}" for name in missing_arguments(call.function, call.arguments))
        if missing:
            return AgentPlan(calls=calls, reply="还需要补充参数：" + "、".join(missing), missing=missing)
        summary = " → ".join(TOOL_MAP[call.function].name for call in calls)
        return AgentPlan(calls=calls, reply=f"已生成执行计划：{summary}")

    def _plan_one(self, text: str) -> ToolCall | None:
        if re.search(r"(?:列出|查看|获取|刷新).*(?:群聊|群列表)", text):
            return ToolCall(
                "GetAllConversations",
                reason="用户要查看会话；群聊分类由 MyBot Python UIA 扫描器维护",
            )
        if re.search(r"(?:列出|查看|获取).*(?:好友|联系人)", text):
            return ToolCall("GetAllFriendNames", reason="用户要查看联系人")
        if re.search(r"(?:列出|查看|获取).*(?:会话|聊天列表)", text):
            return ToolCall("GetAllConversations", reason="用户要查看会话")
        if re.search(r"(?:账号|本人|当前微信).*(?:信息|资料)", text):
            return ToolCall("GetOwerInfo", reason="用户要查看账号信息")

        match = re.search(r"(?:给|向)\s*(.+?)\s*(?:发送|发)(?:一条)?(?:消息)?[：:,，\s]+(.+)", text, re.S)
        if match:
            target, message = match.group(1).strip(), match.group(2).strip()
            self.last_target = target
            return ToolCall("SendMessage", {"who": target, "message": message}, "发送对话消息")
        match = re.search(r"(?:再发|继续发)(?:一条)?[：:,，\s]+(.+)", text, re.S)
        if match and self.last_target:
            return ToolCall("SendMessage", {"who": self.last_target, "message": match.group(1).strip()}, "沿用上一目标")
        match = re.search(r"(?:给|向)\s*(.+?)\s*发(?:送)?表情(?:[：:,，\s]+(.+))?", text)
        if match:
            target = match.group(1).strip()
            self.last_target = target
            return ToolCall("SendEmoji", {"who": target, "emoji": (match.group(2) or "微笑").strip()}, "发送表情")

        match = re.search(r"(?:查看|获取|读取)\s*(.+?)\s*(?:的)?群成员", text)
        if match:
            target = match.group(1).strip()
            self.last_target = target
            return ToolCall("GetChatGroupMemberList", {"group_name": target}, "读取群成员")
        match = re.search(r"(?:查看|获取|读取)\s*(.+?)\s*(?:的)?群主", text)
        if match:
            target = match.group(1).strip()
            self.last_target = target
            return ToolCall("GetGroupOwner", {"group_name": target}, "读取群主")

        if "打开朋友圈" in text:
            return ToolCall("OpenMoments", reason="打开朋友圈窗口")
        if "关闭朋友圈" in text:
            return ToolCall("CloseMoments", reason="关闭朋友圈窗口")
        match = re.search(r"删除朋友圈[：:,，\s]+(.+)", text, re.S)
        if match:
            return ToolCall("RemoveMoments", {"content": match.group(1).strip()}, "删除指定朋友圈")
        match = re.search(r"发布朋友圈[：:,，\s]+(.+?)(?:\s+图片[：:]\s*(.+))?$", text, re.S)
        if match:
            images = [item.strip() for item in (match.group(2) or "").split(";") if item.strip()]
            return ToolCall("AddMoments", {"content": match.group(1).strip(), "images": images}, "发布朋友圈")

        match = re.search(r"(?:搜索|定位|打开会话)\s*[：:,，]?\s*(.+)", text)
        if match:
            target = match.group(1).strip()
            self.last_target = target
            return ToolCall("SearchFriend", {"who": target}, "定位会话")
        match = re.search(r"(?:读取|查看)\s*(.+?)\s*(?:的)?聊天记录", text)
        if match:
            target = match.group(1).strip()
            return ToolCall("GetChatHistory_Who", {"who": target, "fetch_date": date.today().isoformat()}, "读取今天的聊天记录")
        match = re.search(r"(置顶|取消置顶)\s*(.+)", text)
        if match:
            return ToolCall("SetTopMost", {"who": match.group(2).strip(), "setting": match.group(1) == "置顶"}, "调整会话置顶")
        match = re.search(r"(开启免打扰|关闭免打扰)\s*(.+)", text)
        if match:
            return ToolCall("SetDoNotDisturb", {"who": match.group(2).strip(), "setting": match.group(1) == "开启免打扰"}, "调整免打扰")
        return None
