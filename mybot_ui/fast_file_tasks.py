from __future__ import annotations

import json
import re
from pathlib import Path

from .attachments import IncomingAttachment, MAX_ATTACHMENT_BYTES
from .chat_engine import ChatModelClient, ModelConfig
from .codex_runner import CodexResult
from .operation_log import operations


_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
_EDIT_REQUEST = re.compile(
    r"(?:改|修改|编辑|添加|加一|追加|写入|补充|删除|删掉|替换|润色|翻译|整理|完善|改写)",
    re.IGNORECASE,
)


class FastTextTaskError(RuntimeError):
    pass


class FastTextTaskExecutor:
    def __init__(self, client: ChatModelClient) -> None:
        self.client = client

    @staticmethod
    def supports(request: str, attachments: tuple[IncomingAttachment, ...]) -> bool:
        if len(attachments) != 1 or not _EDIT_REQUEST.search(request):
            return False
        attachment = attachments[0]
        path = Path(attachment.path)
        return (
            attachment.kind == "file"
            and path.suffix.casefold() in _TEXT_EXTENSIONS
            and 0 < attachment.size <= min(MAX_ATTACHMENT_BYTES, 512 * 1024)
        )

    def run(
        self,
        *,
        project_root: Path,
        task_id: str,
        request: str,
        attachments: tuple[IncomingAttachment, ...],
        primary: ModelConfig,
        backup: ModelConfig | None,
    ) -> CodexResult | None:
        if not self.supports(request, attachments):
            return None
        attachment = attachments[0]
        span = operations.start("fast_task", "text_file_edit", operation_id=task_id, details={
            "input_name": attachment.name,
            "input_size": attachment.size,
            "request_length": len(request),
        })
        try:
            source = self._read_text(Path(attachment.path))
            payload = json.dumps({
                "filename": attachment.name,
                "instruction": request,
                "original_content": source,
            }, ensure_ascii=False)
            response = self.client.generate_with_fallback(
                primary,
                backup,
                [
                    {
                        "role": "system",
                        "content": (
                            "你负责修改一个纯文本文件。严格执行 instruction，保留未要求修改的原文。"
                            "只返回 JSON 对象，格式为 {\"content\":\"修改后的完整文件内容\"}，"
                            "不要返回 Markdown 代码块、解释、文件名或其他字段。"
                        ),
                    },
                    {"role": "user", "content": payload},
                ],
                timeout=15,
            )
            content = self._response_content(response)
            if not content or content == source:
                raise FastTextTaskError("模型没有生成有效的修改内容")
            output_dir = project_root / "data" / "codex" / "tasks" / task_id / "outputs"
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / self._output_name(attachment.name)
            output.write_text(content, encoding="utf-8")
            size = output.stat().st_size
            if size <= 0 or size > MAX_ATTACHMENT_BYTES:
                raise FastTextTaskError("修改后的文件大小无效")
            result = CodexResult(
                text="文本文件已经按要求修改并完成检查。",
                thread_id="",
                task_id=task_id,
                output_files=(str(output.resolve()),),
            )
            operations.finish(span, success=True, result={
                "output_name": output.name,
                "output_size": size,
            })
            return result
        except Exception as exc:
            operations.finish(span, success=False, error=f"{type(exc).__name__}: {exc}")
            raise

    @staticmethod
    def _read_text(path: Path) -> str:
        raw = path.read_bytes()
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                text = raw.decode(encoding)
            except UnicodeDecodeError:
                continue
            if "\x00" not in text:
                return text
        raise FastTextTaskError("附件不是受支持的纯文本编码")

    @staticmethod
    def _response_content(response: str) -> str:
        text = response.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FastTextTaskError("模型没有返回有效 JSON") from exc
        content = value.get("content") if isinstance(value, dict) else None
        if not isinstance(content, str):
            raise FastTextTaskError("模型返回内容缺少 content")
        return content

    @staticmethod
    def _output_name(name: str) -> str:
        path = Path(name)
        return f"{path.stem}_已修改{path.suffix.casefold()}"
