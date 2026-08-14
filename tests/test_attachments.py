import base64
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from mybot_ui.attachments import (
    ConversationAttachmentStore,
    IncomingAttachment,
    WeChatAttachmentResolver,
    attachment_name_from_message,
    is_image_edit_followup,
    is_image_edit_request,
    stage_task_inputs,
)


class AttachmentTests(unittest.TestCase):
    def test_extracts_wechat_file_name(self):
        self.assertEqual("report.docx", attachment_name_from_message("文件\nreport.docx\n18 KB"))
        self.assertEqual("资料.zip", attachment_name_from_message("[文件] 资料.zip"))
        self.assertEqual("report.docx", attachment_name_from_message("文件 report.docx 18 KB"))

    def test_resolver_uses_recent_exact_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older = root / "old" / "report.docx"
            newer = root / "new" / "report.docx"
            older.parent.mkdir()
            newer.parent.mkdir()
            older.write_bytes(b"old")
            newer.write_bytes(b"new")
            newer.touch()
            resolved = WeChatAttachmentResolver([root]).resolve(
                IncomingAttachment("report.docx"),
                received_at=datetime.now().isoformat(),
            )
            self.assertEqual(newer.resolve(), Path(resolved.path))
            self.assertEqual(3, resolved.size)
            self.assertTrue(resolved.sha256)

    def test_store_materializes_image_and_stages_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ConversationAttachmentStore(root / "inbox")
            encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode("ascii")
            remembered = store.remember("测试会话", (), image_base64=encoded, message_kind="sticker")
            self.assertEqual("sticker", remembered[0].kind)
            recent = store.recent("测试会话")
            self.assertEqual(1, len(recent))
            staged = stage_task_inputs(root / "task", recent)
            self.assertEqual(1, len(staged))
            self.assertTrue(Path(staged[0].path).is_file())
            self.assertIn("inputs", Path(staged[0].path).parts)

    def test_store_imports_file_into_private_inbox_and_persists_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat" / "资料.zip"
            source.parent.mkdir()
            source.write_bytes(b"zip-data")
            store_root = root / "attachments"
            store = ConversationAttachmentStore(
                store_root,
                WeChatAttachmentResolver([source.parent]),
            )
            remembered = store.remember(
                "芝士圆子",
                (IncomingAttachment("资料.zip", str(source)),),
                received_at=datetime.now().isoformat(),
            )
            self.assertEqual(1, len(remembered))
            imported = Path(remembered[0].path)
            self.assertNotEqual(source.resolve(), imported)
            self.assertEqual("资料.zip", imported.name)
            self.assertIn("inbox", imported.parts)
            self.assertIn("zip", remembered[0].mime_type)
            self.assertTrue((store_root / "index.json").is_file())

            reloaded = ConversationAttachmentStore(store_root)
            self.assertEqual(imported, Path(reloaded.all("芝士圆子")[0].path))

    def test_file_request_discovers_nearby_wechat_file_and_excludes_old_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat" / "壁纸.zip"
            source.parent.mkdir()
            source.write_bytes(b"wallpaper")
            received = datetime.now()
            os.utime(source, (received.timestamp() - 20, received.timestamp() - 20))
            store = ConversationAttachmentStore(
                root / "attachments",
                WeChatAttachmentResolver([source.parent]),
            )
            encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nold-image").decode("ascii")
            store.remember("芝士圆子", (), image_base64=encoded)

            with patch("mybot_ui.attachments.Path.home", return_value=root / "home"):
                attachments = store.for_request(
                    "芝士圆子",
                    "你把壁纸解压后发给我",
                    received_at=received.isoformat(),
                )
            self.assertEqual(1, len(attachments))
            self.assertEqual("file", attachments[0].kind)
            self.assertEqual("壁纸.zip", attachments[0].name)

    def test_implicit_image_edit_uses_latest_conversation_image(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationAttachmentStore(Path(directory) / "attachments")
            encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nrestaurant").decode("ascii")
            remembered = store.remember("芝士圆子", (), image_base64=encoded)

            attachments = store.for_request(
                "芝士圆子",
                "把必胜客修改成肯德基发给我",
                received_at=datetime.now().isoformat(),
            )

            self.assertTrue(is_image_edit_request("把必胜客修改成肯德基发给我"))
            self.assertEqual(remembered, attachments)
            self.assertEqual("image", attachments[0].kind)

            typo_request = "我在等你吧必胜客改成肯德基"
            self.assertTrue(is_image_edit_request(typo_request))
            self.assertEqual(
                remembered,
                store.for_request(
                    "芝士圆子",
                    typo_request,
                    received_at=datetime.now().isoformat(),
                ),
            )

    def test_image_edit_followup_recognizes_contextual_retry(self):
        self.assertTrue(is_image_edit_followup("我上面不是发了吗，你瞎啊"))
        self.assertTrue(is_image_edit_followup("你再试一次"))
        self.assertFalse(is_image_edit_followup("今天晚上吃什么"))

    def test_code_edit_is_not_mistaken_for_image_edit(self):
        self.assertFalse(is_image_edit_request("把代码里的必胜客修改成肯德基"))

    def test_moments_copywriting_is_not_mistaken_for_image_edit(self):
        self.assertFalse(is_image_edit_request("把这张图片发朋友圈，编辑一个宣传文案"))


if __name__ == "__main__":
    unittest.main()
