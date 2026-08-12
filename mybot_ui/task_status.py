from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, replace


ACTIVE_TASK_STATES = {"queued", "working", "sending"}


@dataclass(frozen=True)
class TaskStatus:
    task_id: str
    conversation: str
    sender: str
    request: str
    state: str
    stage: str
    kind: str
    created_at: float
    updated_at: float
    finished_at: float = 0.0
    error: str = ""

    def elapsed(self, now: float | None = None) -> float:
        end = self.finished_at or (time.monotonic() if now is None else now)
        return max(0.0, end - self.created_at)


class TaskStatusPool:
    def __init__(self, *, max_finished: int = 50) -> None:
        self.max_finished = max(1, int(max_finished))
        self._lock = threading.RLock()
        self._items: OrderedDict[str, TaskStatus] = OrderedDict()

    def enqueue(
        self,
        task_id: str,
        *,
        conversation: str,
        sender: str,
        request: str,
        now: float | None = None,
    ) -> TaskStatus:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            existing = self._items.get(task_id)
            if existing is not None:
                return existing
            item = TaskStatus(
                task_id=task_id,
                conversation=conversation,
                sender=sender,
                request=" ".join(str(request).split())[:240],
                state="queued",
                stage="等待处理",
                kind="聊天",
                created_at=timestamp,
                updated_at=timestamp,
            )
            self._items[task_id] = item
            self._trim_finished()
            return item

    def update(
        self,
        task_id: str,
        *,
        state: str | None = None,
        stage: str | None = None,
        kind: str | None = None,
        now: float | None = None,
    ) -> TaskStatus | None:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            existing = self._items.get(task_id)
            if existing is None:
                return None
            item = replace(
                existing,
                state=state or existing.state,
                stage=stage or existing.stage,
                kind=kind or existing.kind,
                updated_at=timestamp,
            )
            self._items[task_id] = item
            return item

    def finish(
        self,
        task_id: str,
        *,
        success: bool,
        error: str = "",
        now: float | None = None,
    ) -> TaskStatus | None:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            existing = self._items.get(task_id)
            if existing is None:
                return None
            if existing.state not in ACTIVE_TASK_STATES:
                return existing
            normalized_error = " ".join(str(error or "").split())[:300]
            if not success and normalized_error.casefold() in {"timeouterror", "timeout"}:
                normalized_error = f"{existing.stage}超时"
            item = replace(
                existing,
                state="completed" if success else "failed",
                stage="已完成" if success else existing.stage,
                updated_at=timestamp,
                finished_at=timestamp,
                error=normalized_error,
            )
            self._items[task_id] = item
            self._trim_finished()
            return item

    def fail_active(self, error: str, *, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            active_ids = [
                task_id for task_id, item in self._items.items()
                if item.state in ACTIVE_TASK_STATES
            ]
        for task_id in active_ids:
            self.finish(task_id, success=False, error=error, now=timestamp)

    def snapshots(self) -> tuple[TaskStatus, ...]:
        with self._lock:
            values = tuple(self._items.values())
        return tuple(sorted(
            values,
            key=lambda item: (
                0 if item.state in ACTIVE_TASK_STATES else 1,
                item.created_at if item.state in ACTIVE_TASK_STATES else -item.updated_at,
            ),
        ))

    def counts(self) -> dict[str, int]:
        with self._lock:
            values = tuple(self._items.values())
        queued = sum(item.state == "queued" for item in values)
        working = sum(item.state in {"working", "sending"} for item in values)
        failed = sum(item.state == "failed" for item in values)
        completed = sum(item.state == "completed" for item in values)
        return {
            "active": queued + working,
            "queued": queued,
            "working": working,
            "failed": failed,
            "completed": completed,
        }

    def _trim_finished(self) -> None:
        finished = [
            task_id for task_id, item in self._items.items()
            if item.state not in ACTIVE_TASK_STATES
        ]
        for task_id in finished[:-self.max_finished]:
            self._items.pop(task_id, None)
