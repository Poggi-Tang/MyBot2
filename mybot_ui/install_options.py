from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
from typing import Any


INSTALL_OPTIONS_NAME = "install-options.ini"


def apply_pending_install_options(project_root: str | Path) -> str:
    root = Path(project_root).resolve()
    options_path = root / INSTALL_OPTIONS_NAME
    if not options_path.is_file():
        return ""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(options_path, encoding="utf-8-sig")
        config_path = root / "config.json"
        example_path = root / "config.example.json"
        source_path = config_path if config_path.is_file() else example_path
        data = json.loads(source_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("配置根节点必须是 JSON 对象")

        install = parser["install"] if parser.has_section("install") else {}
        if _option_bool(install, "packaged_server", True):
            server = data.get("server", {})
            server = dict(server) if isinstance(server, dict) else {}
            server["exe_path"] = "runtime/server/Server.exe"
            data["server"] = server

        features = data.get("features", {})
        features = dict(features) if isinstance(features, dict) else {}
        features.update({
            "sdk_catalog": _option_bool(install, "sdk_catalog", True),
            "abilities": _option_bool(install, "abilities", True),
            "codex_extension": _option_bool(install, "codex_extension", False),
        })
        data["features"] = features

        defer_api = _option_bool(install, "defer_api", True)
        if not defer_api and parser.has_section("primary"):
            primary_options = parser["primary"]
            base_url = str(primary_options.get("base_url", "")).strip()
            model = str(primary_options.get("model", "")).strip()
            api_key = str(primary_options.get("api_key", "")).strip()
            if base_url and model and api_key:
                primary = data.get("primary", {})
                primary = dict(primary) if isinstance(primary, dict) else {}
                primary.update({
                    "provider": "openai",
                    "base_url": base_url,
                    "model": model,
                    "api_key": api_key,
                })
                data["primary"] = primary

        temporary = config_path.with_suffix(".json.installing")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, config_path)
        options_path.unlink(missing_ok=True)
        return "安装选项已应用"
    except Exception:
        raise


def _option_bool(section: Any, name: str, default: bool) -> bool:
    value = str(section.get(name, "1" if default else "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}
