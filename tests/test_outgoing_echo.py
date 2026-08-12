import tempfile
import unittest
from pathlib import Path

from mybot_ui.outgoing_echo import OutgoingEchoJournal


class OutgoingEchoJournalTests(unittest.TestCase):
    def test_second_instance_reads_successful_external_send(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "echoes.sqlite3"
            writer = OutgoingEchoJournal(path)
            reader = OutgoingEchoJournal(path)

            writer.record("芝士圆子", "第二轮测试已准备好")
            cursor, echoes = reader.read_after(0)

            self.assertGreater(cursor, 0)
            self.assertEqual(
                [("芝士圆子", "第二轮测试已准备好", "text")],
                [(item.conversation, item.content, item.kind) for item in echoes],
            )
            self.assertGreater(echoes[0].process_id, 0)

            next_cursor, repeated = reader.read_after(cursor)
            self.assertEqual(cursor, next_cursor)
            self.assertEqual((), repeated)


if __name__ == "__main__":
    unittest.main()
