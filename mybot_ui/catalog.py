from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .api import encode_upload


@dataclass(frozen=True)
class ToolSpec:
    function: str
    name: str
    category: str
    description: str
    risk: str = "只读"
    required: tuple[str, ...] = ()
    test_kind: str = "safe"


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("GetOwerInfo", "读取账号信息", "账号", "读取当前微信昵称、wxid 与头像信息"),
    ToolSpec("GetAllConversations", "列出全部会话", "会话", "扫描全部可见会话标题"),
    ToolSpec("GetVisibleConversations", "读取可见会话", "会话", "读取当前会话列表及未读、置顶状态"),
    ToolSpec("GetAllChatGroups", "自动检索群聊", "群管理", "逐个识别会话类型并返回全部群聊"),
    ToolSpec("GetAllFriendNames", "列出联系人", "通讯录", "读取全部联系人名称"),
    ToolSpec("GetAllFriends", "读取联系人详情", "通讯录", "读取联系人资料与头像", required=("with_avatar",)),
    ToolSpec("SearchFriend", "定位联系人或群", "会话", "搜索并打开指定好友或群聊", "可逆", ("who",), "configured"),
    ToolSpec("GetTitle", "读取当前会话信息", "会话", "读取当前聊天标题、类型和群人数"),
    ToolSpec("GetChatHistory_Who", "读取聊天记录", "消息", "读取指定对象从某日开始的聊天记录", required=("who", "fetch_date"), test_kind="configured"),
    ToolSpec("GetVisibleChatMessages", "读取可见消息", "消息", "读取指定会话当前屏幕内的消息气泡", required=("who",), test_kind="configured"),
    ToolSpec("SendMessage", "发送文本消息", "消息", "向好友或群聊发送文本", "写入", ("who", "message"), "configured"),
    ToolSpec("SendEmoji", "发送表情", "消息", "向好友或群聊发送微信表情", "写入", ("who", "emoji"), "configured"),
    ToolSpec("ScanAllStickers", "扫描表情包", "消息", "扫描所有表情分类；普通表情按控件名称建目录，自定义表情按视觉哈希建目录"),
    ToolSpec("SendSticker", "发送表情包", "消息", "从已扫描目录发送表情包", "写入", ("who", "sticker"), "configured"),
    ToolSpec("SendFile", "发送文件", "消息", "向好友或群聊上传并发送文件", "写入", ("who", "files"), "configured"),
    ToolSpec("SendVoiceChat", "发起语音通话", "消息", "向指定联系人发起语音通话", "高风险", ("who",), "manual"),
    ToolSpec("SendVedioChat", "发起视频通话", "消息", "向指定联系人发起视频通话", "高风险", ("who",), "manual"),
    ToolSpec("TapWho", "拍一拍", "消息", "在指定聊天中拍一拍联系人", "写入", ("who",), "configured"),
    ToolSpec("SetTopMost", "设置会话置顶", "会话", "设置或取消会话置顶", "可逆", ("who", "setting"), "configured"),
    ToolSpec("SetDoNotDisturb", "设置消息免打扰", "会话", "设置或取消消息免打扰", "可逆", ("who", "setting"), "configured"),
    ToolSpec("GetGroupOwner", "读取群主", "群管理", "读取指定群聊群主", required=("group_name",), test_kind="configured"),
    ToolSpec("GetChatGroupMemberList", "读取群成员", "群管理", "读取指定群聊成员名单", required=("group_name",), test_kind="configured"),
    ToolSpec("IsOwnerChatGroup", "判断自有群", "群管理", "判断当前账号是否为群主", required=("group_name",), test_kind="configured"),
    ToolSpec("ChangeOwnerChatGroupName", "修改群名", "群管理", "修改自有群名称", "写入", ("old_group_name", "new_group_name"), "manual"),
    ToolSpec("ChangeChatGroupNickName", "修改群昵称", "群管理", "修改自己在群里的昵称", "写入", ("group_name", "nick_name"), "manual"),
    ToolSpec("UpdateGroupNotice", "发布群公告", "群管理", "更新自有群公告", "高风险", ("group_name", "group_notice"), "manual"),
    ToolSpec("AddOwnerChatGroupMember", "添加群成员", "群管理", "向自有群添加联系人", "高风险", ("group_name", "members"), "manual"),
    ToolSpec("RemoveOwnerChatGroupMember", "移除群成员", "群管理", "从自有群移除成员", "高风险", ("group_name", "members"), "manual"),
    ToolSpec("InviteChatGroupMember", "邀请群成员", "群管理", "邀请联系人加入外部群", "高风险", ("group_name", "members"), "manual"),
    ToolSpec("QuitChatGroup", "退出群聊", "群管理", "退出指定群聊并可清理记录", "高风险", ("group_name",), "manual"),
    ToolSpec("OpenMoments", "打开朋友圈", "朋友圈", "打开朋友圈窗口", "可逆"),
    ToolSpec("CloseMoments", "关闭朋友圈", "朋友圈", "关闭朋友圈窗口", "可逆"),
    ToolSpec("AddMoments", "发布朋友圈", "朋友圈", "发布带图片的朋友圈", "写入", ("content", "images"), "configured"),
    ToolSpec("RemoveMoments", "删除朋友圈", "朋友圈", "按文字内容删除自己发布的朋友圈", "高风险", ("content",), "configured"),
    ToolSpec("AddMessageListener", "启动消息监听", "监听", "监听指定对象或开放式监听消息", "可逆", test_kind="configured"),
    ToolSpec("PauseMessageListener", "暂停消息监听", "监听", "暂停当前消息监听", "可逆"),
    ToolSpec("ResumeMessageListener", "恢复消息监听", "监听", "恢复当前消息监听", "可逆"),
    ToolSpec("AddFriendRequestAutoAcceptListener", "自动通过好友申请", "监听", "监听并自动通过好友申请", "高风险", test_kind="manual"),
    ToolSpec("AddGroupSystemMessageListener", "监听群系统消息", "监听", "监听入群、退群等群系统事件", "可逆", test_kind="configured"),
    ToolSpec("Max", "最大化微信", "窗口", "最大化微信主窗口", "可逆"),
    ToolSpec("Restore", "恢复微信窗口", "窗口", "恢复微信主窗口", "可逆"),
    ToolSpec("Focus", "聚焦微信窗口", "窗口", "将微信主窗口切换到前台", "可逆"),
    ToolSpec("Pinned", "窗口置顶", "窗口", "将微信主窗口置顶", "可逆"),
    ToolSpec("UnPinned", "取消窗口置顶", "窗口", "取消微信主窗口置顶", "可逆"),
    ToolSpec("CloseSearchWindow", "关闭聊天搜索窗", "窗口", "关闭指定聊天的搜索窗口", "可逆", ("who",), "manual"),
    ToolSpec("OpenSubWin", "打开独立聊天窗", "窗口", "将指定会话打开为独立窗口", "可逆", ("who",), "manual"),
    ToolSpec("GetHandler", "读取窗口句柄", "系统", "读取当前微信原生窗口句柄"),
    ToolSpec("GetProcessId", "读取进程 ID", "系统", "读取当前微信进程 ID"),
    ToolSpec("SwitchNavigation", "切换微信导航", "窗口", "切换到通讯录、朋友圈等导航项", "可逆", ("navigation_type",), "manual"),
    ToolSpec("CloseNavWin", "关闭导航窗口", "窗口", "关闭由导航栏打开的独立窗口", "可逆", ("navigation_type",), "manual"),
    ToolSpec("ClickNotifyIcon", "点击通知图标", "窗口", "点击微信通知区域图标", "可逆", ("icon",), "manual"),
    ToolSpec("GetVisibleConversationTitles", "列出可见会话标题", "会话", "只读取当前屏幕可见的会话标题"),
    ToolSpec("LocateConversation", "滚动定位会话", "会话", "滚动会话列表，使目标会话可见", "可逆", ("who",), "manual"),
    ToolSpec("FocuseSenderInput", "聚焦输入框", "消息", "将焦点移动到当前聊天输入框", "可逆"),
    ToolSpec("GetOnlyTitle", "读取当前标题", "会话", "仅读取当前聊天标题"),
    ToolSpec("SendVoiceChats", "发起多人语音", "消息", "在群聊中发起多人语音通话", "高风险", ("who", "partners"), "manual"),
    ToolSpec("SendVoiceMessage", "发送语音文件", "消息", "上传音频并作为语音消息发送", "写入", ("who", "file_path"), "manual"),
    ToolSpec("SendStreamingVoiceMessage", "发送流式语音", "消息", "根据流式语音请求生成并发送语音", "写入", ("who", "request"), "manual"),
    ToolSpec("GetChatHistory_Current_Window", "读取当前聊天记录", "消息", "按日期读取当前窗口聊天记录", required=("fetch_date",), test_kind="manual"),
    ToolSpec("ForwardMultipleMessage", "合并转发消息", "消息", "将多条消息合并转发给多个目标", "高风险", ("who", "to"), "manual"),
    ToolSpec("ForwardSingleMessage", "转发单条消息", "消息", "按内容定位并转发单条消息", "高风险", ("who", "message", "to"), "manual"),
    ToolSpec("OpenAddFriensWin", "打开添加好友窗口", "通讯录", "打开添加好友窗口", "可逆", test_kind="manual"),
    ToolSpec("CloseAddFriendWin", "关闭添加好友窗口", "通讯录", "关闭添加好友窗口", "可逆", test_kind="manual"),
    ToolSpec("AddFriends", "批量添加好友", "通讯录", "按昵称或微信号批量发起好友申请", "高风险", ("friends",), "manual"),
    ToolSpec("RemoveFriend", "删除好友", "通讯录", "删除指定好友", "高风险", ("who",), "manual"),
    ToolSpec("PassedAllNewFriend", "通过全部好友申请", "通讯录", "处理当前全部新好友申请", "高风险", test_kind="manual"),
    ToolSpec("CreateOwnerChatGroup", "创建群聊", "群管理", "选择联系人创建自有群聊", "高风险", ("group_name", "first_who", "members"), "manual"),
    ToolSpec("ChangeChatGroupMemo", "修改群备注", "群管理", "修改群聊在会话列表中的备注", "写入", ("group_name", "new_memo"), "manual"),
    ToolSpec("AddChatGroupMemberToFriends", "添加群成员为好友", "群管理", "从群成员列表批量发起好友申请", "高风险", ("group_name", "members"), "manual"),
    ToolSpec("AddMessageListener_With_Time", "定时消息监听", "监听", "仅在指定起止时间内监听消息", "可逆", ("start_time", "end_time"), "manual"),
    ToolSpec("AddMessageListener_With_Range", "分时段消息监听", "监听", "按多个时间段监听消息", "可逆", ("ranges",), "manual"),
    ToolSpec("AddListeningFriend", "增加监听对象", "监听", "向运行中的监听器添加好友或群聊", "可逆", ("who",), "manual"),
    ToolSpec("RemoveListeningFriend", "移除监听对象", "监听", "从运行中的监听器移除好友或群聊", "可逆", ("who",), "manual"),
    ToolSpec("PauseNewFriendListener", "暂停好友申请监听", "监听", "暂停新好友申请监听", "可逆", test_kind="manual"),
    ToolSpec("ResumeNewFriendListener", "恢复好友申请监听", "监听", "恢复新好友申请监听", "可逆", test_kind="manual"),
)

TOOL_MAP = {tool.function: tool for tool in TOOLS}


def missing_arguments(function: str, arguments: dict[str, Any]) -> list[str]:
    spec = TOOL_MAP.get(function)
    if not spec:
        return []
    return [name for name in spec.required if arguments.get(name) in (None, "", [])]


def build_message_reference(who: str, message: str, send_date: str) -> dict[str, Any] | None:
    """Build the ChatRefer payload expected by WeChatAuto4_X."""
    who = str(who or "").strip()
    message = str(message or "").strip()
    try:
        sent_at = datetime.fromisoformat(str(send_date or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if not who or not message:
        return None
    unique = hashlib.md5(
        f"{who}\0{message}\0{sent_at.isoformat()}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    return {
        "date": sent_at.date().isoformat(),
        "message": {
            "who": who,
            "message": message,
            "send_date_time": (
                f"{sent_at.year}年{sent_at.month}月{sent_at.day}日 "
                f"{sent_at.hour:02d}:{sent_at.minute:02d}"
            ),
            "date_time": sent_at.isoformat(),
            "unique_string": unique,
        },
        "is_close_search_win": True,
    }


def build_options(function: str, args: dict[str, Any]) -> Any:
    """Translate agent-friendly arguments to the legacy WebSocket payload."""
    if function in {
        "GetOwerInfo", "GetAllConversations", "GetVisibleConversations",
        "GetAllChatGroups", "GetAllFriendNames", "GetTitle", "OpenMoments",
        "CloseMoments", "PauseMessageListener", "ResumeMessageListener",
        "Max", "Restore", "Focus", "Pinned", "UnPinned", "GetHandler",
        "GetProcessId", "GetVisibleConversationTitles", "FocuseSenderInput",
        "GetOnlyTitle", "OpenAddFriensWin", "CloseAddFriendWin",
        "PauseNewFriendListener", "ResumeNewFriendListener",
    }:
        return ""
    if function == "GetAllFriends":
        return str(bool(args.get("with_avatar", False)))
    if function in {"SearchFriend", "LocateConversation", "OpenSubWin", "CloseSearchWindow", "RemoveFriend", "AddListeningFriend", "RemoveListeningFriend", "TapWho"}:
        if function == "TapWho":
            return {"who": args["who"], "prev_scroll_number": str(args.get("prev_scroll_number", 30))}
        return args["who"]
    if function in {"SwitchNavigation", "CloseNavWin"}:
        return args["navigation_type"]
    if function == "ClickNotifyIcon":
        return str(args["icon"])
    if function in {"GetGroupOwner", "GetChatGroupMemberList", "IsOwnerChatGroup", "RemoveMoments"}:
        return args.get("group_name") or args.get("content") or ""
    if function == "GetChatHistory_Who":
        return {"who": args["who"], "fetch_date": args["fetch_date"]}
    if function == "SendMessage":
        refer = args.get("refer")
        return {
            "who": args["who"],
            "message": args["message"],
            "atUser": json.dumps(args.get("at_users", []), ensure_ascii=False),
            "refer": json.dumps(refer, ensure_ascii=False) if refer else "null",
        }
    if function == "SendEmoji":
        return {"who": args["who"], "emoji": str(args.get("emoji", "微笑")), "atUser": json.dumps(args.get("at_users", []), ensure_ascii=False)}
    if function == "ScanAllStickers":
        return ""
    if function == "SendSticker":
        return {
            "who": args["who"],
            "category": str(args.get("category", "")),
            "sticker": str(args["sticker"]),
        }
    if function == "SendFile":
        files = [str(Path(path)) for path in args.get("files", [])]
        uploads = {path: encode_upload(path) for path in files}
        return {"who": args["who"], "files": json.dumps(files, ensure_ascii=False), "upload": json.dumps(uploads)}
    if function in {"SendVoiceChat", "SendVedioChat"}:
        return args["who"]
    if function == "SendVoiceChats":
        return {"who": args["who"], "partner": json.dumps(args["partners"], ensure_ascii=False)}
    if function == "SendVoiceMessage":
        file_path = str(Path(args["file_path"]))
        return {"who": args["who"], "filePath": file_path, "upload": encode_upload(file_path)}
    if function == "SendStreamingVoiceMessage":
        request = args["request"]
        return {"who": args["who"], "request": request if isinstance(request, str) else json.dumps(request, ensure_ascii=False)}
    if function == "GetChatHistory_Current_Window":
        return args["fetch_date"]
    if function == "ForwardMultipleMessage":
        return {
            "who": args["who"],
            "to": json.dumps(args["to"], ensure_ascii=False),
            "f_type": args.get("f_type", "ForwardMerge"),
            "row_count": str(args.get("row_count", 5)),
        }
    if function == "ForwardSingleMessage":
        return {
            "who": args["who"],
            "message": args["message"],
            "to": json.dumps(args["to"], ensure_ascii=False),
            "prev_scroll_number": str(args.get("prev_scroll_number", 30)),
        }
    if function in {"SetTopMost", "SetDoNotDisturb"}:
        return {"who": args["who"], "setting": bool(args.get("setting", True))}
    if function == "ChangeOwnerChatGroupName":
        return {"old_group_name": args["old_group_name"], "new_group_name": args["new_group_name"]}
    if function == "CreateOwnerChatGroup":
        return {
            "group_name": args["group_name"],
            "first_who": args["first_who"],
            "member_name": json.dumps(args["members"], ensure_ascii=False),
        }
    if function == "ChangeChatGroupNickName":
        return {"group_name": args["group_name"], "nick_name": args["nick_name"]}
    if function == "ChangeChatGroupMemo":
        return {"group_name": args["group_name"], "new_memo": args["new_memo"]}
    if function == "UpdateGroupNotice":
        return {"group_name": args["group_name"], "group_notice": args["group_notice"]}
    if function in {"AddOwnerChatGroupMember", "RemoveOwnerChatGroupMember"}:
        return {"group_name": args["group_name"], "member_name": json.dumps(args["members"], ensure_ascii=False)}
    if function == "InviteChatGroupMember":
        return {"group_name": args["group_name"], "members": json.dumps(args["members"], ensure_ascii=False), "invite_reason_if_need": args.get("reason", "")}
    if function == "AddChatGroupMemberToFriends":
        options = {"interval_time": 5, "is_close_win": True, "say_hi": "", "suffix": "", "label": ""}
        return {
            "group_name": args["group_name"],
            "member_name": json.dumps(args["members"], ensure_ascii=False),
            "options": json.dumps(args.get("options", options), ensure_ascii=False),
        }
    if function == "QuitChatGroup":
        return {"group_name": args["group_name"], "clear_history": bool(args.get("clear_history", True))}
    if function == "AddMoments":
        images = [str(Path(path)) for path in args.get("images", [])]
        uploads = {path: encode_upload(path) for path in images}
        options = {"at_usrs": [], "labels": [], "is_close_moments": True}
        return {
            "image_files": json.dumps(images, ensure_ascii=False),
            "content": args["content"],
            "upload": json.dumps(uploads),
            "options": json.dumps(options),
        }
    if function == "AddMessageListener":
        targets = args.get("targets", [])
        monitor_options = {
            "fetch_friend_info": True,
            "fetch_image": True,
            "fetch_file": True,
            "fetch_voice_chat": True,
            "click_red_envelope": False,
            "is_risk_prevention": False,
            "monitor_read_conversations": bool(args.get("monitor_read_conversations", False)),
            "file_save_directory": str(args.get("file_save_directory", "")).strip(),
        }
        return {
            "nick_names": json.dumps(targets, ensure_ascii=False),
            "is_open_monitor": bool(args.get("open", not targets)),
            "options": json.dumps(monitor_options),
        }
    if function in {"AddMessageListener_With_Time", "AddMessageListener_With_Range"}:
        targets = args.get("targets", [])
        monitor_options = {
            "fetch_friend_info": False,
            "fetch_image": False,
            "fetch_voice_chat": False,
            "click_red_envelope": False,
            "is_risk_prevention": True,
        }
        payload = {
            "nick_names": json.dumps(targets, ensure_ascii=False),
            "is_open_monitor": str(bool(args.get("open", not targets))),
            "options": json.dumps(monitor_options),
        }
        if function == "AddMessageListener_With_Time":
            payload.update({"start_time": args["start_time"], "end_time": args["end_time"]})
        else:
            payload["range"] = json.dumps(args["ranges"], ensure_ascii=False)
        return payload
    if function == "AddGroupSystemMessageListener":
        return json.dumps(args.get("targets", []), ensure_ascii=False)
    if function == "AddFriendRequestAutoAcceptListener":
        return {"passed_delete": True, "keyword": [], "suffix": "", "label": ""}
    if function == "AddFriends":
        options = {"interval_time": 5, "is_close_win": True, "say_hi": "", "suffix": "", "label": ""}
        return {"friends": json.dumps(args["friends"], ensure_ascii=False), "options": json.dumps(args.get("options", options), ensure_ascii=False)}
    if function == "PassedAllNewFriend":
        return {"passed_delete": True, "keyword": [], "suffix": "", "label": ""}
    return args
