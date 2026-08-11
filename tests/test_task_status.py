import unittest

from mybot_ui.task_status import TaskStatusPool


class TaskStatusPoolTests(unittest.TestCase):
    def test_reports_queued_working_and_completed_counts(self):
        pool = TaskStatusPool()
        pool.enqueue("one", conversation="测试群", sender="甲", request="第一个问题", now=10)
        pool.enqueue("two", conversation="测试群", sender="乙", request="第二个问题", now=11)
        pool.update("one", state="working", stage="生成回复", kind="模型", now=12)

        self.assertEqual(
            {"active": 2, "queued": 1, "working": 1, "failed": 0, "completed": 0},
            pool.counts(),
        )
        pool.finish("one", success=True, now=15)
        self.assertEqual(5, pool.snapshots()[-1].elapsed())
        self.assertEqual(1, pool.counts()["active"])

    def test_fail_active_keeps_visible_failure_reason(self):
        pool = TaskStatusPool()
        pool.enqueue("one", conversation="测试群", sender="甲", request="问题", now=10)
        pool.fail_active("自动聊天已停止", now=13)

        item = pool.snapshots()[0]
        self.assertEqual("failed", item.state)
        self.assertEqual("自动聊天已停止", item.error)
        self.assertEqual(3, item.elapsed())

    def test_trims_only_finished_history(self):
        pool = TaskStatusPool(max_finished=2)
        for index in range(4):
            task_id = str(index)
            pool.enqueue(task_id, conversation="群", sender="人", request=task_id, now=index)
            pool.finish(task_id, success=True, now=index + 0.5)
        pool.enqueue("active", conversation="群", sender="人", request="还在处理", now=9)

        snapshots = pool.snapshots()
        self.assertEqual(3, len(snapshots))
        self.assertEqual("active", snapshots[0].task_id)


if __name__ == "__main__":
    unittest.main()
