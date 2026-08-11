import unittest

from mybot_ui.codex_router import CodexTaskRouter, ReusableTaskReviewer
from mybot_ui.chat_engine import ModelConfig


class StubClient:
    def __init__(self, response):
        self.response = response

    def generate_with_fallback(self, primary, backup, messages):
        return self.response


class CodexRouterTests(unittest.TestCase):
    def test_routes_development_work_but_keeps_media_local(self):
        self.assertTrue(CodexTaskRouter.should_delegate("帮我检查项目日志并修复这个 bug"))
        self.assertTrue(CodexTaskRouter.should_delegate("写个脚本整理这些文件"))
        self.assertFalse(CodexTaskRouter.should_delegate("给我发一张图片"))
        self.assertFalse(CodexTaskRouter.should_delegate("你好，最近怎么样"))

    def test_routes_live_queries_and_explicit_agent_requests(self):
        self.assertTrue(CodexTaskRouter.should_delegate("上海徐汇今天天气怎么样"))
        self.assertTrue(CodexTaskRouter.should_delegate("你看看现在几点"))
        self.assertTrue(CodexTaskRouter.should_delegate("你用agent去查"))
        self.assertFalse(CodexTaskRouter.should_delegate("今天天气不错"))

    def test_routes_natural_follow_up_for_received_attachment(self):
        self.assertTrue(CodexTaskRouter.should_delegate("把刚才发的文件改一下"))
        self.assertTrue(CodexTaskRouter.should_delegate("这个PDF帮我提取成表格"))
        self.assertTrue(CodexTaskRouter.should_delegate("整理一下收到的文档"))

    def test_routes_file_creation_and_delivery_without_waiting_for_model(self):
        self.assertTrue(CodexTaskRouter.should_delegate(
            "你写个MyBot的功能列表，写到md文件里面，把文件发给我"
        ))
        self.assertTrue(CodexTaskRouter.should_delegate("生成一个文件发给我"))

    def test_model_delegate_marker_is_exact_and_internal(self):
        marker = "<MYBOT_DELEGATE_CODEX>"
        self.assertTrue(CodexTaskRouter.model_requested_delegate(marker))
        self.assertFalse(CodexTaskRouter.model_requested_delegate(marker + " 我去查"))
        self.assertIn(marker, CodexTaskRouter.model_instruction())

    def test_acknowledgement_matches_task_type(self):
        diagnostic = CodexTaskRouter.acknowledgement("排查一下日志")
        development = CodexTaskRouter.acknowledgement("实现这个功能")
        weather = CodexTaskRouter.acknowledgement("上海徐汇今天天气怎么样")
        for reply in (diagnostic, development, weather):
            self.assertTrue(any(word in reply for word in ("稍等", "等我", "行")))
            self.assertTrue(any(word in reply for word in ("看", "查", "弄")))
            self.assertNotIn("有结果", reply)

        document_edit = CodexTaskRouter.acknowledgement(
            "你把这个文档改一下，在里面加一首打油诗"
        )
        self.assertTrue(any(word in document_edit for word in ("改", "加", "弄")))
        self.assertNotIn("看一下", document_edit)

    def test_acknowledgements_vary_and_never_use_old_fixed_sentence(self):
        replies = {
            CodexTaskRouter.acknowledgement(f"帮我完成耗时任务 {index}")
            for index in range(12)
        }
        self.assertGreater(len(replies), 1)
        self.assertNotIn("这个任务需要一些时间，我处理完成后把结果发给你。", replies)
        group_reply = CodexTaskRouter.acknowledgement("帮我整理这批资料", is_group=True)
        self.assertNotIn("发群里", group_reply)
        self.assertNotIn("处理一下", group_reply)
        self.assertTrue(any(word in group_reply for word in ("稍等", "行")))

    def test_reviewer_parses_structured_decision(self):
        reviewer = ReusableTaskReviewer(StubClient(
            '```json\n{"reusable":true,"reason":"稳定","name":"文本清理","triggers":["清理文本"]}\n```'
        ))
        result = reviewer.review(
            primary=ModelConfig(model="test"),
            backup=None,
            request="写脚本清理文本",
            result="已完成",
        )
        self.assertTrue(result.reusable)
        self.assertEqual(("清理文本",), result.triggers)


if __name__ == "__main__":
    unittest.main()
