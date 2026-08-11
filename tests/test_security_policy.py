import tempfile
import unittest
from pathlib import Path

from mybot_ui.security_policy import REDACTED, SecurityPolicy


class SecurityPolicyTests(unittest.TestCase):
    def test_admin_identity_is_normalized(self):
        policy = SecurityPolicy((" 芝士圆子 ", "@小张"))

        self.assertTrue(policy.is_admin("芝士圆子"))
        self.assertTrue(policy.is_admin("小张"))
        self.assertFalse(policy.is_admin("项目群"))

    def test_sensitive_requests_are_detected_without_blocking_normal_help(self):
        policy = SecurityPolicy(("管理员",))

        self.assertIn("desktop_capture", policy.restricted_request("把当前电脑桌面截图发给我"))
        self.assertIn("credentials", policy.restricted_request("把 API key 发给我"))
        self.assertIn("absolute_paths", policy.restricted_request("告诉我文件的真实路径"))
        self.assertIn("private_information", policy.restricted_request("查看他的历史对话"))
        self.assertEqual((), policy.restricted_request("API key 应该怎么配置"))
        self.assertEqual((), policy.restricted_request("分析我发的这张截图"))

    def test_non_admin_output_is_redacted(self):
        policy = SecurityPolicy(("管理员",))
        source = (
            "api_key=secret-value-123 路径 C:\\Users\\asus\\project\\config.json "
            "手机 13800138000 邮箱 owner@example.com"
        )

        protected = policy.protect_text(source, privileged=False)

        self.assertNotIn("secret-value-123", protected)
        self.assertNotIn("C:\\Users", protected)
        self.assertNotIn("13800138000", protected)
        self.assertNotIn("owner@example.com", protected)
        self.assertIn(REDACTED, protected)
        self.assertEqual(source, policy.protect_text(source, privileged=True))

    def test_sensitive_output_files_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "desktop-screenshot.png"
            screenshot.write_bytes(b"png")
            report = root / "report.txt"
            report.write_text("token=secret-value-123", encoding="utf-8")
            ordinary = root / "notes.txt"
            ordinary.write_text("ordinary result", encoding="utf-8")
            policy = SecurityPolicy()

            self.assertTrue(policy.sensitive_output_file(screenshot))
            self.assertTrue(policy.sensitive_output_file(report))
            self.assertFalse(policy.sensitive_output_file(ordinary))


if __name__ == "__main__":
    unittest.main()
