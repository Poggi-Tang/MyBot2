import json
import tempfile
import unittest
from pathlib import Path

from mybot_ui.attachments import IncomingAttachment
from mybot_ui.chat_engine import ModelConfig
from mybot_ui.fast_file_tasks import FastTextTaskExecutor


class StubClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    def generate_with_fallback(self, primary, backup, messages, *, timeout=120):
        self.calls.append((primary, backup, messages, timeout))
        return json.dumps({"content": self.content}, ensure_ascii=False)


class FastTextTaskTests(unittest.TestCase):
    def test_single_text_edit_creates_delivery_without_overwriting_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "test.txt"
            source.write_text("123", encoding="utf-8")
            attachment = IncomingAttachment(
                name=source.name,
                path=str(source),
                kind="file",
                size=source.stat().st_size,
            )
            client = StubClient("123\n\n今天写代码，结果挺可靠。")
            executor = FastTextTaskExecutor(client)

            result = executor.run(
                project_root=root,
                task_id="task-1",
                request="把这个文档改一下，在里面加一首打油诗",
                attachments=(attachment,),
                primary=ModelConfig(provider="openai", model="primary"),
                backup=ModelConfig(provider="openai", model="backup"),
            )

            self.assertIsNotNone(result)
            output = Path(result.output_files[0])
            self.assertEqual("test_已修改.txt", output.name)
            self.assertEqual("123", source.read_text(encoding="utf-8"))
            self.assertIn("今天写代码", output.read_text(encoding="utf-8"))
            self.assertEqual(15, client.calls[0][3])

    def test_fast_path_rejects_code_and_non_edit_requests(self):
        source = IncomingAttachment("app.py", "app.py", "file", size=10)
        document = IncomingAttachment("notes.txt", "notes.txt", "file", size=10)
        self.assertFalse(FastTextTaskExecutor.supports("修改这个文件", (source,)))
        self.assertFalse(FastTextTaskExecutor.supports("分析这个文档", (document,)))
        self.assertTrue(FastTextTaskExecutor.supports("修改这个文档", (document,)))


if __name__ == "__main__":
    unittest.main()
