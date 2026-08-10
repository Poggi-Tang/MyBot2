from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


INDEX_VERSION = 1
MAX_ABILITIES = 200
MAX_FILE_BYTES = 200_000
WORD_PATTERN = re.compile(r"[a-zA-Z0-9_.-]{2,}|[\u3400-\u9fff]{2,}")
SECRET_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9_.-]{12,}|"
    r"api[_-]?key\s*[:=]\s*['\"]?[^\s'\"]{8,})",
    re.IGNORECASE,
)
ABSOLUTE_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\(?:Users|AIWorkspace)\\|/(?:home|Users)/)", re.IGNORECASE)
SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


@dataclass(frozen=True)
class AbilityMatch:
    ability_id: str
    name: str
    description: str
    triggers: tuple[str, ...]
    recipe_path: str
    skill_path: str
    script_paths: tuple[str, ...]
    score: int

    def prompt(self) -> str:
        return (
            f"快捷能力：{self.name}（{self.ability_id}）\n"
            f"用途：{self.description}\n"
            f"触发词：{'、'.join(self.triggers) or '[无]'}\n"
            f"已验证配方：{self.recipe_path}\n"
            f"技能包：{self.skill_path}\n"
            f"脚本入口：{'、'.join(self.script_paths)}\n"
            "先读取 SKILL.md 和配方并优先运行已验证脚本；只有输入契约不匹配时才重新实现。"
        )


class AbilityValidationError(ValueError):
    pass


class ExtensionAbilityStore:
    _lock = threading.RLock()

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.abilities_dir = self.root / "abilities"
        self.candidates_dir = self.root / ".candidates"
        self.index_path = self.root / "index.json"
        self.abilities_dir.mkdir(parents=True, exist_ok=True)
        self.candidates_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index({"version": INDEX_VERSION, "abilities": []})

    def count(self) -> int:
        return len(self.list_abilities())

    def list_abilities(self) -> tuple[dict[str, Any], ...]:
        """Return a defensive snapshot of the published ability index."""
        with self._lock:
            values = self._read_index().get("abilities", [])
            return tuple(deepcopy(value) for value in values if isinstance(value, dict))

    def record_usage(self, ability_ids: tuple[str, ...]) -> None:
        selected = {value.strip() for value in ability_ids if value.strip()}
        if not selected:
            return
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._lock:
            index = self._read_index()
            changed = False
            for item in index.get("abilities", []):
                if not isinstance(item, dict) or str(item.get("id", "")) not in selected:
                    continue
                try:
                    count = max(0, int(item.get("usage_count", 0)))
                except (TypeError, ValueError):
                    count = 0
                item["usage_count"] = count + 1
                item["last_used_at"] = timestamp
                changed = True
            if changed:
                self._write_index(index)

    def candidate_path(self, task_id: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", task_id).strip("-")[:64]
        if not safe:
            raise AbilityValidationError("候选任务 ID 无效")
        path = (self.candidates_dir / safe).resolve()
        path.relative_to(self.candidates_dir)
        return path

    def matching(self, request: str, limit: int = 3) -> tuple[AbilityMatch, ...]:
        terms = _terms(request)
        if not terms:
            return ()
        folded_request = request.casefold()
        matches: list[AbilityMatch] = []
        for item in self.list_abilities():
            triggers = tuple(str(value) for value in item.get("triggers", []) if str(value).strip())
            searchable = " ".join((str(item.get("name", "")), str(item.get("description", "")), *triggers))
            score = len(terms & _terms(searchable))
            direct_trigger = any(
                len(trigger.strip()) >= 4 and trigger.casefold() in folded_request
                for trigger in triggers
            )
            if score < 2 and not direct_trigger:
                continue
            scripts = tuple(str(value) for value in item.get("scripts", []) if str(value).strip())
            skill_path = str(item.get("skill") or "").strip()
            if not skill_path:
                skill_path = str(item.get("recipe") or "").strip()
            matches.append(AbilityMatch(
                ability_id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                triggers=triggers,
                recipe_path=str(item.get("recipe", "")),
                skill_path=skill_path,
                script_paths=scripts,
                score=score,
            ))
        return tuple(sorted(matches, key=lambda value: (-value.score, value.ability_id))[: max(1, limit)])

    def matching_context(self, request: str) -> str:
        return "\n\n".join(match.prompt() for match in self.matching(request))

    def promote_candidate(
        self,
        candidate: str | Path,
        *,
        forbidden_terms: tuple[str, ...] = (),
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        candidate_path = Path(candidate).resolve()
        candidate_path.relative_to(self.candidates_dir)
        manifest_path = candidate_path / "manifest.json"
        recipe_path = candidate_path / "recipe.md"
        skill_path = candidate_path / "SKILL.md"
        if not manifest_path.is_file() or not recipe_path.is_file() or not skill_path.is_file():
            raise AbilityValidationError("候选能力缺少 manifest.json、SKILL.md 或 recipe.md")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("reusable") is not True:
            raise AbilityValidationError("Codex 判定该任务不可沉淀")
        slug = str(manifest.get("id", "")).strip()
        if not SAFE_SLUG.fullmatch(slug):
            raise AbilityValidationError("能力 ID 必须是小写短横线格式")
        name = str(manifest.get("name", "")).strip()[:80]
        description = str(manifest.get("description", "")).strip()[:400]
        triggers = _string_list(manifest.get("triggers"), limit=16, item_limit=80)
        if not name or not description or not triggers:
            raise AbilityValidationError("能力名称、说明或触发词为空")

        scripts_dir = candidate_path / "scripts"
        tests_dir = candidate_path / "tests"
        scripts = sorted(scripts_dir.glob("*.py")) if scripts_dir.is_dir() else []
        tests = sorted(tests_dir.glob("test_*.py")) if tests_dir.is_dir() else []
        if not scripts or not tests:
            raise AbilityValidationError("候选能力必须包含 Python 脚本和自动化测试")
        skill_text = skill_path.read_text(encoding="utf-8")
        frontmatter = _skill_frontmatter(skill_text)
        if not frontmatter.get("name") or not frontmatter.get("description"):
            raise AbilityValidationError("SKILL.md 缺少 name 或 description 前置元数据")
        files = [manifest_path, skill_path, recipe_path, *scripts, *tests]
        forbidden = tuple(term.casefold() for term in forbidden_terms if len(term.strip()) >= 2)
        for path in files:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise AbilityValidationError(f"候选文件过大：{path.name}")
            content = path.read_text(encoding="utf-8")
            if SECRET_PATTERN.search(content):
                raise AbilityValidationError(f"候选文件疑似包含密钥：{path.name}")
            if ABSOLUTE_PATH_PATTERN.search(content):
                raise AbilityValidationError(f"候选文件包含用户绝对路径：{path.name}")
            lowered = content.casefold()
            if any(term in lowered for term in forbidden):
                raise AbilityValidationError(f"候选文件包含会话专属信息：{path.name}")

        compile_result = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", "scripts", "tests"],
            cwd=candidate_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        if compile_result.returncode:
            raise AbilityValidationError("候选脚本编译失败：" + _last_line(compile_result.stderr))
        test_result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            cwd=candidate_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        if test_result.returncode:
            raise AbilityValidationError("候选能力测试失败：" + _last_line(test_result.stdout + "\n" + test_result.stderr))

        destination = (self.abilities_dir / slug).resolve()
        destination.relative_to(self.abilities_dir)
        if destination.exists():
            raise AbilityValidationError(f"能力已存在，需要显式升级而不是覆盖：{slug}")
        shutil.copytree(candidate_path, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        digest = _directory_digest(destination)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        item = {
            "id": slug,
            "name": name,
            "description": description,
            "triggers": list(triggers),
            "recipe": f"abilities/{slug}/recipe.md",
            "skill": f"abilities/{slug}/SKILL.md",
            "scripts": [f"abilities/{slug}/scripts/{path.name}" for path in scripts],
            "validated_at": timestamp,
            "validation": "compileall + unittest",
            "sha256": digest,
            "usage_count": 0,
        }
        with self._lock:
            index = self._read_index()
            abilities = [value for value in index.get("abilities", []) if isinstance(value, dict)]
            abilities.append(item)
            index = {"version": INDEX_VERSION, "abilities": abilities[-MAX_ABILITIES:]}
            self._write_index(index)
        return item

    def _read_index(self) -> dict[str, Any]:
        try:
            value = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"version": INDEX_VERSION, "abilities": []}
        if not isinstance(value, dict) or value.get("version") != INDEX_VERSION:
            return {"version": INDEX_VERSION, "abilities": []}
        if not isinstance(value.get("abilities"), list):
            value["abilities"] = []
        return value

    def _write_index(self, value: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.index_path)


def _terms(text: str) -> set[str]:
    values: set[str] = set()
    for match in WORD_PATTERN.findall(text.casefold()):
        values.add(match)
        if re.fullmatch(r"[\u3400-\u9fff]+", match) and len(match) > 2:
            values.update(match[index : index + 2] for index in range(len(match) - 1))
    return values


def _string_list(value: Any, *, limit: int, item_limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result = []
    for item in value:
        text = str(item).strip()[:item_limit]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return tuple(result)


def _last_line(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return lines[-1][:500] if lines else "未知错误"


def _skill_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"name", "description"}:
            result[key.strip()] = value.strip().strip("'\"")
    return result


def _directory_digest(path: Path) -> str:
    digest = hashlib.sha256()
    files = (
        value
        for value in path.rglob("*")
        if value.is_file() and "__pycache__" not in value.parts and value.suffix != ".pyc"
    )
    for file_path in sorted(files):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(file_path.read_bytes())
    return digest.hexdigest()
