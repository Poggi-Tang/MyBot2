import unittest
from types import SimpleNamespace

from mybot_ui.conversation_scanner import ConversationScanner


class FakeSession:
    def __init__(self, name, automation, header):
        self.Name = name
        self.automation = automation
        self.header = header

    def Click(self, **_kwargs):
        self.automation.header = self.header


class FakeList:
    def __init__(self, pages):
        self.pages = pages
        self.index = 0
        self.up_calls = []
        self.down_calls = []

    def WheelUp(self, **kwargs):
        self.up_calls.append(kwargs)
        self.index = 0

    def WheelDown(self, **kwargs):
        self.down_calls.append(kwargs)
        self.index = min(self.index + 1, len(self.pages) - 1)

    def GetChildren(self):
        return self.pages[self.index]


class FakeAutomation:
    TIME_OUT_SECOND = 10

    def __init__(self):
        self.header = ""
        self.timeouts = []
        self.list_control = None

    def SetGlobalSearchTimeout(self, value):
        self.timeouts.append(value)
        self.TIME_OUT_SECOND = value

    def ListControl(self, **_kwargs):
        return self.list_control

    def Control(self, **_kwargs):
        return SimpleNamespace(Name=self.header)


class ConversationScannerTests(unittest.TestCase):
    def test_scans_all_pages_and_classifies_from_header_count(self):
        automation = FakeAutomation()
        first = [
            FakeSession("测试群\n最后消息", automation, "测试群(3)"),
            FakeSession("芝士圆子\n最后消息", automation, "芝士圆子"),
            FakeSession("公众号\n通知", automation, "公众号"),
        ]
        second = [
            FakeSession("芝士圆子\n最后消息", automation, "芝士圆子"),
            FakeSession("AI 群\n新消息", automation, "AI 群(18)"),
        ]
        automation.list_control = FakeList([first, second, second, second])

        scan = ConversationScanner(automation, sleep=lambda _seconds: None).scan()

        self.assertEqual(("测试群", "芝士圆子", "AI 群"), scan.names)
        self.assertEqual(("测试群", "AI 群"), scan.groups)
        self.assertEqual(("芝士圆子",), scan.privates)
        self.assertEqual([0.15, 10], automation.timeouts)
        self.assertEqual(2, len(automation.list_control.up_calls))
        self.assertGreaterEqual(len(automation.list_control.down_calls), 3)

    def test_failure_returns_error_and_restores_list_position(self):
        automation = FakeAutomation()
        automation.list_control = FakeList([[FakeSession("测试群", automation, "测试群(3)")]])
        automation.Control = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))

        result = ConversationScanner(automation, sleep=lambda _seconds: None).try_scan()

        self.assertFalse(result.ok)
        self.assertIn("boom", result.error)
        self.assertEqual(2, len(automation.list_control.up_calls))
        self.assertEqual([0.15, 10], automation.timeouts)

    def test_waits_for_matching_title_before_classification(self):
        automation = FakeAutomation()
        automation.list_control = FakeList([[
            FakeSession("测试群\n最后消息", automation, "测试群(3)"),
        ]])
        reads = iter(("旧会话", "", "测试群(3)"))
        automation.Control = lambda **_kwargs: SimpleNamespace(Name=next(reads))

        scan = ConversationScanner(automation, sleep=lambda _seconds: None).scan()

        self.assertEqual(("测试群",), scan.groups)
        self.assertEqual((), scan.privates)

    def test_mismatched_title_never_defaults_to_private(self):
        automation = FakeAutomation()
        automation.list_control = FakeList([[
            FakeSession("测试群\n最后消息", automation, "其他会话"),
        ]])

        result = ConversationScanner(automation, sleep=lambda _seconds: None).try_scan()

        self.assertFalse(result.ok)
        self.assertIn("会话标题刷新超时：测试群", result.error)


if __name__ == "__main__":
    unittest.main()
