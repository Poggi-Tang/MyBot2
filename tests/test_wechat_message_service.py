import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from mybot_ui.wechat_message_analysis import ConversationContext, MESSAGE_AUTOMATION_ID
from mybot_ui.wechat_message_service import (
    ConversationNotReadyError,
    WeChatMessageService,
)


class Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class Control:
    def __init__(
        self,
        *,
        name="",
        automation_id="",
        class_name="",
        rect=(0, 0, 400, 50),
        children=None,
        exists=True,
    ):
        self.Name = name
        self.AutomationId = automation_id
        self.ClassName = class_name
        self.BoundingRectangle = Rect(*rect)
        self._children = list(children or [])
        self._exists = exists
        self.clicks = 0
        self.right_clicks = []
        self.wheels = []

    def Exists(self, *_args):
        return self._exists

    def GetChildren(self):
        return list(self._children)

    def Click(self, **_kwargs):
        self.clicks += 1

    def RightClick(self, **kwargs):
        self.right_clicks.append(kwargs)

    def WheelUp(self, **kwargs):
        self.wheels.append(("up", kwargs))

    def WheelDown(self, **kwargs):
        self.wheels.append(("down", kwargs))


class PagedMessageList(Control):
    def __init__(self, pages):
        super().__init__(name="消息", class_name="mmui::RecyclerListView")
        self.pages = pages
        self.page = 0

    def GetChildren(self):
        return list(self.pages[self.page])

    def WheelUp(self, **kwargs):
        super().WheelUp(**kwargs)
        self.page = min(self.page + 1, len(self.pages) - 1)


class Automation:
    def __init__(self, *, session_list=None, message_list=None, menu=None, root_menu=None):
        self.session_list = session_list
        self.message_list = message_list
        self.menu = menu
        self.root_menu = root_menu
        self.calls = []
        self.screen_clicks = []
        self.keys = []

    def ListControl(self, **kwargs):
        self.calls.append(("ListControl", kwargs))
        return self.session_list if kwargs.get("AutomationId") == "session_list" else self.message_list

    def WindowControl(self, **kwargs):
        self.calls.append(("WindowControl", kwargs))
        return self.menu or Control(exists=False)

    def GetRootControl(self):
        menu = self.root_menu
        return SimpleNamespace(WindowControl=lambda **kwargs: self._root_window(kwargs, menu))

    def _root_window(self, kwargs, menu):
        self.calls.append(("Root.WindowControl", kwargs))
        return menu or Control(exists=False)

    def Click(self, x, y, **kwargs):
        self.screen_clicks.append((x, y, kwargs))

    def SendKeys(self, keys, **kwargs):
        self.keys.append((keys, kwargs))


def bubble(name):
    return Control(
        name=name,
        automation_id=MESSAGE_AUTOMATION_ID,
        class_name="mmui::ChatTextItemView",
        rect=(0, 0, 500, 60),
    )


class WeChatMessageServiceTests(unittest.TestCase):
    def service(self, automation=None):
        return WeChatMessageService(
            Path("."), automation, image_grab=lambda **_kwargs: Image.new("RGB", (400, 100), "white"), sleep=lambda _seconds: None
        )

    def test_poll_builds_baseline_then_only_clicks_changed_target(self):
        target = Control(name="芝士圆子\n旧消息")
        other = Control(name="其他人\n消息")
        sessions = Control(children=[target, other])
        automation = Automation(session_list=sessions)
        service = self.service(automation)
        service._targets = {"芝士圆子"}
        service._callback = Mock()
        service._active.set()
        service._read_current_messages = Mock(return_value={"type": "python_message"})

        service._poll_once(automation)
        self.assertEqual(0, target.clicks)
        target.Name = "芝士圆子\n[2条] 新消息"
        service._poll_once(automation)

        self.assertEqual(1, target.clicks)
        self.assertEqual(0, other.clicks)
        service._read_current_messages.assert_called_once_with(automation, "芝士圆子", 2)
        service._callback.assert_called_once_with({"type": "python_message"})

        target.Name = "芝士圆子\n新消息"
        service._poll_once(automation)
        self.assertEqual(1, target.clicks, "clearing unread metadata must not reclick")

    def test_same_preview_clicks_when_unread_count_increases(self):
        target = Control(name="芝士圆子\n重复内容\n13:36")
        sessions = Control(children=[target])
        automation = Automation(session_list=sessions)
        service = self.service(automation)
        service._targets = {"芝士圆子"}
        service._callback = Mock()
        service._active.set()
        service._read_current_messages = Mock(return_value={"type": "python_message"})
        service._poll_once(automation)

        target.Name = "芝士圆子\n[1条]\n重复内容\n13:36"
        service._poll_once(automation)

        self.assertEqual(1, target.clicks)
        service._read_current_messages.assert_called_once_with(automation, "芝士圆子", 1)

    def test_transient_chat_switch_failure_retries_same_preview(self):
        target = Control(name="芝士圆子\n旧消息")
        sessions = Control(children=[target])
        automation = Automation(session_list=sessions)
        service = self.service(automation)
        service._targets = {"芝士圆子"}
        service._callback = Mock()
        service._active.set()
        service._read_current_messages = Mock(side_effect=[
            ConversationNotReadyError("会话尚未就绪"),
            {"type": "python_message"},
        ])
        service._poll_once(automation)

        target.Name = "芝士圆子\n[1条]\n新消息"
        service._poll_once(automation)
        service._poll_once(automation)

        self.assertEqual(2, target.clicks)
        self.assertEqual(2, service._read_current_messages.call_count)
        service._callback.assert_called_once_with({"type": "python_message"})

    def test_select_conversation_waits_for_matching_title(self):
        target = Control(name="芝士圆子\n新消息")
        automation = Automation(session_list=Control(children=[target]))
        service = self.service(automation)
        contexts = (
            ConversationContext("unknown"),
            ConversationContext("unknown"),
            ConversationContext("private", "芝士圆子"),
        )

        with patch(
            "mybot_ui.wechat_message_service.read_conversation_context",
            side_effect=contexts,
        ):
            selected = service._select_conversation(automation, "芝士圆子")

        self.assertTrue(selected)
        self.assertEqual(1, target.clicks)

    def test_first_poll_detects_message_arriving_after_server_baseline(self):
        target = Control(name="芝士圆子\n[1条]\n新消息\n13:36")
        sessions = Control(children=[target])
        automation = Automation(session_list=sessions)
        service = self.service(automation)
        service._targets = {"芝士圆子"}
        service._callback = Mock()
        service._active.set()
        service._preview_baselines = {"芝士圆子": "旧消息|13:35"}
        service._read_current_messages = Mock(return_value={"type": "python_message"})

        service._poll_once(automation)

        self.assertEqual(1, target.clicks)
        service._read_current_messages.assert_called_once_with(automation, "芝士圆子", 1)

    def test_preview_fingerprint_matches_server_parser(self):
        raw = "芝士圆子\n[2条]\n消息免打扰\n第一行\n第二行\n13:36\n已置顶"
        self.assertEqual(
            "第一行\n第二行|13:36",
            WeChatMessageService._preview_fingerprint(raw),
        )

    def test_operation_lock_blocks_listener_until_send_finishes(self):
        service = self.service()
        token = service.begin_operation()
        acquired = []

        def wait_for_lock():
            with service._operation_lock:
                acquired.append(True)

        worker = threading.Thread(target=wait_for_lock)
        worker.start()
        worker.join(0.05)
        self.assertEqual([], acquired)
        service.end_operation(token)
        worker.join(1)
        self.assertEqual([True], acquired)

    def test_reference_searches_newest_first_then_scrolls_up(self):
        current_old = bubble("当前页旧消息")
        older_target = bubble("需要引用的消息")
        message_list = PagedMessageList([[current_old], [older_target]])
        automation = Automation(message_list=message_list)
        service = self.service(automation)
        service._select_conversation = Mock(return_value=True)
        service._quote_item = Mock(return_value=True)

        result = service._prepare_reference(
            automation, "芝士圆子", "需要引用的消息", "对方", 4, "token"
        )

        self.assertTrue(result.ok)
        self.assertEqual(2, result.pages_scanned)
        service._quote_item.assert_called_once_with(automation, older_target, incoming=True)
        self.assertEqual(1, len(message_list.wheels))

    def test_reference_stops_when_page_repeats(self):
        message_list = PagedMessageList([[bubble("没有目标")]])
        automation = Automation(message_list=message_list)
        service = self.service(automation)
        service._select_conversation = Mock(return_value=True)

        result = service._prepare_reference(
            automation, "芝士圆子", "需要引用的消息", "我", 40, "token"
        )

        self.assertFalse(result.ok)
        self.assertEqual(1, result.pages_scanned)
        self.assertEqual(1, len(message_list.wheels))

    def test_right_click_finds_desktop_menu_and_clicks_ocr_quote(self):
        item = bubble("目标")
        row = Control(class_name="mmui::XMenuView", rect=(124, 224, 476, 270))
        menu = Control(
            name="Weixin",
            class_name="mmui::XMenu",
            rect=(100, 200, 500, 500),
            children=[row],
        )
        automation = Automation(root_menu=menu)
        service = self.service(automation)
        service._menu_ocr.analyze = Mock(return_value={
            "items": [{"text": "引用", "rect": (180, 240, 230, 270)}],
            "error": "",
        })

        self.assertTrue(service._quote_item(automation, item, incoming=True))
        self.assertEqual(104, item.right_clicks[0]["x"])
        self.assertIn(
            ("WindowControl", {"Name": "Weixin", "ClassName": "mmui::XMenu"}),
            automation.calls,
        )
        self.assertIn(
            ("Root.WindowControl", {"Name": "Weixin", "ClassName": "mmui::XMenu"}),
            automation.calls,
        )
        self.assertEqual((205, 255), automation.screen_clicks[0][:2])

    def test_missing_quote_option_dismisses_menu(self):
        item = bubble("目标")
        menu = Control(name="Weixin", class_name="mmui::XMenu", rect=(100, 200, 500, 500))
        automation = Automation(menu=menu)
        service = self.service(automation)
        service._menu_ocr.analyze = Mock(return_value={"items": [{"text": "复制", "rect": (1, 1, 2, 2)}]})

        self.assertFalse(service._quote_item(automation, item, incoming=False))
        self.assertEqual(-104, item.right_clicks[0]["x"])
        self.assertEqual("{Esc}", automation.keys[0][0])


if __name__ == "__main__":
    unittest.main()
