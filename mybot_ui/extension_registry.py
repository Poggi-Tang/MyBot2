from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_BUILTIN_MCPS = {
    "mybot": {
        "name": "MyBot",
        "description": "任务进度与成果文件登记",
        "module": "mybot_mcp.server",
    },
    "autowx": {
        "name": "AutoWX",
        "description": "受控读取和操作微信 SDK",
        "module": "autowx_mcp.server",
    },
}


class ExtensionRegistryError(ValueError):
    pass


class ExtensionRegistry:
    """Project-local MCP and Skill inventory with persistent enable state."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_root = self.project_root / "data" / "extensions"
        self.path = self.data_root / "registry.json"
        self.imported_skills_root = self.data_root / "skills"

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExtensionRegistryError(f"扩展注册表读取失败：{exc}") from exc
        if not isinstance(value, dict):
            raise ExtensionRegistryError("扩展注册表根节点必须是 JSON 对象")
        return value

    def _save(self, value: dict[str, Any]) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    @staticmethod
    def _identifier(value: str, *, kind: str) -> str:
        identifier = str(value).strip()
        if not _IDENTIFIER.fullmatch(identifier):
            raise ExtensionRegistryError(f"{kind} 标识只能包含字母、数字、连字符和下划线")
        return identifier

    def list_mcps(self) -> tuple[dict[str, Any], ...]:
        data = self._load()
        enabled = data.get("mcp_enabled", {})
        enabled = enabled if isinstance(enabled, dict) else {}
        rows: list[dict[str, Any]] = []
        for identifier, definition in _BUILTIN_MCPS.items():
            rows.append({
                "id": identifier,
                **definition,
                "enabled": bool(enabled.get(identifier, True)),
                "builtin": True,
            })
        imported = data.get("mcps", {})
        imported = imported if isinstance(imported, dict) else {}
        for identifier in sorted(imported):
            definition = imported[identifier]
            if not isinstance(definition, dict):
                continue
            rows.append({
                "id": identifier,
                **definition,
                "enabled": bool(enabled.get(identifier, True)),
                "builtin": False,
            })
        return tuple(rows)

    def enabled_mcps(self) -> tuple[dict[str, Any], ...]:
        return tuple(item for item in self.list_mcps() if item["enabled"])

    def mcp_enabled(self, identifier: str) -> bool:
        return any(item["id"] == identifier and item["enabled"] for item in self.list_mcps())

    def set_mcp_enabled(self, identifier: str, enabled: bool) -> None:
        identifier = self._identifier(identifier, kind="MCP")
        if not any(item["id"] == identifier for item in self.list_mcps()):
            raise ExtensionRegistryError(f"MCP 不存在：{identifier}")
        data = self._load()
        states = data.get("mcp_enabled", {})
        states = dict(states) if isinstance(states, dict) else {}
        states[identifier] = bool(enabled)
        data["mcp_enabled"] = states
        self._save(data)

    def import_mcp(self, config_path: str | Path) -> tuple[str, ...]:
        path = Path(config_path).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExtensionRegistryError(f"MCP 配置读取失败：{exc}") from exc
        if not isinstance(payload, dict):
            raise ExtensionRegistryError("MCP 配置根节点必须是 JSON 对象")
        servers = payload.get("mcpServers")
        if servers is None:
            name = payload.get("name") or payload.get("id")
            servers = {str(name): payload} if name else {}
        if not isinstance(servers, dict) or not servers:
            raise ExtensionRegistryError("没有找到可导入的 mcpServers")

        data = self._load()
        imported = data.get("mcps", {})
        imported = dict(imported) if isinstance(imported, dict) else {}
        identifiers: list[str] = []
        for raw_identifier, raw_definition in servers.items():
            identifier = self._identifier(str(raw_identifier), kind="MCP")
            if identifier in _BUILTIN_MCPS or identifier in imported:
                raise ExtensionRegistryError(f"MCP 已存在：{identifier}")
            if not isinstance(raw_definition, dict):
                raise ExtensionRegistryError(f"MCP {identifier} 的配置必须是 JSON 对象")
            command = str(raw_definition.get("command", "")).strip()
            url = str(raw_definition.get("url", "")).strip()
            if not command and not url:
                raise ExtensionRegistryError(f"MCP {identifier} 缺少 command 或 url")
            args = raw_definition.get("args", [])
            env = raw_definition.get("env", {})
            if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
                raise ExtensionRegistryError(f"MCP {identifier} 的 args 必须是字符串数组")
            if not isinstance(env, dict):
                raise ExtensionRegistryError(f"MCP {identifier} 的 env 必须是对象")
            imported[identifier] = {
                "name": str(raw_definition.get("displayName") or identifier),
                "description": str(raw_definition.get("description", "导入的 MCP 服务")),
                "command": command,
                "url": url,
                "args": args,
                "env": {str(key): str(value) for key, value in env.items()},
            }
            identifiers.append(identifier)
        data["mcps"] = imported
        self._save(data)
        return tuple(identifiers)

    def remove_mcp(self, identifier: str) -> None:
        identifier = self._identifier(identifier, kind="MCP")
        if identifier in _BUILTIN_MCPS:
            raise ExtensionRegistryError("内置 MCP 只能禁用，不能移除")
        data = self._load()
        imported = data.get("mcps", {})
        imported = dict(imported) if isinstance(imported, dict) else {}
        if identifier not in imported:
            raise ExtensionRegistryError(f"MCP 不存在：{identifier}")
        imported.pop(identifier)
        data["mcps"] = imported
        states = data.get("mcp_enabled", {})
        if isinstance(states, dict):
            states.pop(identifier, None)
            data["mcp_enabled"] = states
        self._save(data)

    def _skill_sources(self) -> dict[str, tuple[Path, bool]]:
        result: dict[str, tuple[Path, bool]] = {}
        bundled = self.project_root / "codex" / "skills"
        if bundled.is_dir():
            for source in bundled.iterdir():
                if source.is_dir() and (source / "SKILL.md").is_file():
                    result[source.name] = (source, True)
        data = self._load()
        imported = data.get("skills", {})
        imported = imported if isinstance(imported, dict) else {}
        for identifier in sorted(imported):
            source = self.imported_skills_root / identifier
            if source.is_dir() and (source / "SKILL.md").is_file():
                result[identifier] = (source, False)
        return result

    def list_skills(self) -> tuple[dict[str, Any], ...]:
        data = self._load()
        disabled = data.get("disabled_skills", [])
        disabled = {str(item) for item in disabled} if isinstance(disabled, list) else set()
        rows = []
        for identifier, (source, builtin) in sorted(self._skill_sources().items()):
            metadata = self._skill_metadata(source / "SKILL.md")
            rows.append({
                "id": identifier,
                "name": metadata.get("name", identifier),
                "description": metadata.get("description", ""),
                "path": source,
                "enabled": identifier not in disabled,
                "builtin": builtin,
            })
        return tuple(rows)

    def set_skill_enabled(self, identifier: str, enabled: bool) -> None:
        identifier = self._identifier(identifier, kind="Skill")
        if identifier not in self._skill_sources():
            raise ExtensionRegistryError(f"Skill 不存在：{identifier}")
        data = self._load()
        disabled = data.get("disabled_skills", [])
        disabled_set = {str(item) for item in disabled} if isinstance(disabled, list) else set()
        if enabled:
            disabled_set.discard(identifier)
        else:
            disabled_set.add(identifier)
        data["disabled_skills"] = sorted(disabled_set)
        self._save(data)
        self.sync_skills()

    def import_skill(self, source_directory: str | Path) -> str:
        source = Path(source_directory).resolve()
        skill_file = source / "SKILL.md"
        if not source.is_dir() or not skill_file.is_file():
            raise ExtensionRegistryError("所选目录根部没有 SKILL.md")
        metadata = self._skill_metadata(skill_file)
        identifier = self._identifier(metadata.get("name", source.name), kind="Skill")
        if identifier in self._skill_sources():
            raise ExtensionRegistryError(f"Skill 已存在：{identifier}")
        destination = self.imported_skills_root / identifier
        self.imported_skills_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
        )
        data = self._load()
        skills = data.get("skills", {})
        skills = dict(skills) if isinstance(skills, dict) else {}
        skills[identifier] = {"imported_from": str(source)}
        data["skills"] = skills
        self._save(data)
        self.sync_skills()
        return identifier

    def remove_skill(self, identifier: str) -> None:
        identifier = self._identifier(identifier, kind="Skill")
        sources = self._skill_sources()
        if identifier not in sources:
            raise ExtensionRegistryError(f"Skill 不存在：{identifier}")
        if sources[identifier][1]:
            raise ExtensionRegistryError("内置 Skill 只能禁用，不能移除")
        shutil.rmtree(self.imported_skills_root / identifier)
        mirror = self.project_root / ".agents" / "skills" / identifier
        if mirror.is_dir():
            shutil.rmtree(mirror)
        data = self._load()
        skills = data.get("skills", {})
        if isinstance(skills, dict):
            skills.pop(identifier, None)
            data["skills"] = skills
        disabled = data.get("disabled_skills", [])
        if isinstance(disabled, list):
            data["disabled_skills"] = [item for item in disabled if item != identifier]
        self._save(data)

    def sync_skills(self) -> None:
        mirror_root = self.project_root / ".agents" / "skills"
        mirror_root.mkdir(parents=True, exist_ok=True)
        for item in self.list_skills():
            destination = mirror_root / item["id"]
            if destination.is_dir():
                shutil.rmtree(destination)
            if item["enabled"]:
                shutil.copytree(
                    item["path"],
                    destination,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
                )

    @staticmethod
    def _skill_metadata(path: Path) -> dict[str, str]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
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
