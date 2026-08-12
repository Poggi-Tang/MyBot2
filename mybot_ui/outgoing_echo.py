from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


OUTGOING_ECHO_TTL_SECONDS = 15 * 60


@dataclass(frozen=True)
class OutgoingEcho:
    row_id: int
    conversation: str
    content: str
    kind: str
    process_id: int


class OutgoingEchoJournal:
    """Cross-process journal for SDK sends that can reappear as inbound UIA bubbles."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def record(self, conversation: str, content: str, *, kind: str = "text") -> None:
        conversation = str(conversation or "").strip()
        content = str(content or "").strip()
        if not conversation or not content:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO outgoing_echoes "
                    "(created_at, conversation, content, kind, process_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        time.time(),
                        conversation,
                        content,
                        str(kind or "text"),
                        os.getpid(),
                    ),
                )
                connection.execute(
                    "DELETE FROM outgoing_echoes WHERE created_at < ?",
                    (time.time() - OUTGOING_ECHO_TTL_SECONDS,),
                )

    def read_after(self, row_id: int) -> tuple[int, tuple[OutgoingEcho, ...]]:
        if not self.path.is_file():
            return max(0, int(row_id)), ()
        cutoff = time.time() - OUTGOING_ECHO_TTL_SECONDS
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, conversation, content, kind, process_id FROM outgoing_echoes "
                "WHERE id > ? AND created_at >= ? ORDER BY id",
                (max(0, int(row_id)), cutoff),
            ).fetchall()
        echoes = tuple(
            OutgoingEcho(
                int(item[0]),
                str(item[1]),
                str(item[2]),
                str(item[3]),
                int(item[4]),
            )
            for item in rows
        )
        return (echoes[-1].row_id if echoes else max(0, int(row_id))), echoes

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS outgoing_echoes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "created_at REAL NOT NULL, "
            "conversation TEXT NOT NULL, "
            "content TEXT NOT NULL, "
            "kind TEXT NOT NULL, "
            "process_id INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        columns = {
            str(item[1])
            for item in connection.execute("PRAGMA table_info(outgoing_echoes)")
        }
        if "process_id" not in columns:
            connection.execute(
                "ALTER TABLE outgoing_echoes "
                "ADD COLUMN process_id INTEGER NOT NULL DEFAULT 0"
            )
        return connection


def default_outgoing_echo_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "outgoing-echoes.sqlite3"
