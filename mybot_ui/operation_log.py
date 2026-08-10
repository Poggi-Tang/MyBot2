from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


_SENSITIVE_KEYS = (
    "api_key", "authorization", "password", "secret", "token",
    "upload", "base64", "b64_json", "image_base64", "audio_data",
)


def summarize(value: Any, key: str = "", depth: int = 0) -> Any:
    if depth > 6:
        return {"truncated": True, "reason": "max_depth"}
    lowered = key.lower()
    if isinstance(value, str):
        encoded = value.encode("utf-8", errors="replace")
        if any(marker in lowered for marker in _SENSITIVE_KEYS) or ";base64," in value[:120].lower():
            return {
                "redacted": True,
                "length": len(value),
                "sha256": hashlib.sha256(encoded).hexdigest()[:16],
            }
        if len(value) > 600:
            return {
                "length": len(value),
                "sha256": hashlib.sha256(encoded).hexdigest()[:16],
                "preview": value[:240],
            }
        return value
    if isinstance(value, dict):
        return {str(item_key): summarize(item, str(item_key), depth + 1) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = [summarize(item, key, depth + 1) for item in value[:20]]
        if len(value) > 20:
            items.append({"truncated": True, "remaining": len(value) - 20})
        return items
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return summarize(str(value), key, depth + 1)


@dataclass(frozen=True)
class OperationSpan:
    operation_id: str
    layer: str
    operation: str
    started_at: str
    started_monotonic: float


class OperationLog:
    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory else Path(__file__).resolve().parent.parent / "logs"
        self._lock = threading.Lock()

    def start(
        self,
        layer: str,
        operation: str,
        *,
        operation_id: str | None = None,
        details: Any = None,
    ) -> OperationSpan:
        now = datetime.now().astimezone()
        span = OperationSpan(
            operation_id=operation_id or uuid.uuid4().hex,
            layer=layer,
            operation=operation,
            started_at=now.isoformat(timespec="milliseconds"),
            started_monotonic=time.perf_counter(),
        )
        self._write({
            "timestamp": span.started_at,
            "event": "started",
            "operation_id": span.operation_id,
            "layer": layer,
            "operation": operation,
            "details": summarize(details),
        })
        return span

    def finish(
        self,
        span: OperationSpan,
        *,
        success: bool,
        result: Any = None,
        error: Any = None,
        details: Any = None,
    ) -> None:
        finished = datetime.now().astimezone().isoformat(timespec="milliseconds")
        self._write({
            "timestamp": finished,
            "event": "finished",
            "operation_id": span.operation_id,
            "layer": span.layer,
            "operation": span.operation,
            "success": success,
            "duration_ms": round((time.perf_counter() - span.started_monotonic) * 1000, 3),
            "result": summarize(result, "result"),
            "error": summarize(error, "error"),
            "details": summarize(details),
        })

    def event(self, layer: str, operation: str, details: Any = None) -> None:
        now = datetime.now().astimezone().isoformat(timespec="milliseconds")
        self._write({
            "timestamp": now,
            "event": "event",
            "operation_id": uuid.uuid4().hex,
            "layer": layer,
            "operation": operation,
            "duration_ms": 0,
            "details": summarize(details),
        })

    def _write(self, entry: dict[str, Any]) -> None:
        try:
            with self._lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                path = self.directory / f"client-operations-{datetime.now():%Y%m%d}.jsonl"
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass


operations = OperationLog()
