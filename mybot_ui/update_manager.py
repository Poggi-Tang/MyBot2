from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen


GITHUB_LATEST_RELEASE_API = "https://api.github.com/repos/Poggi-Tang/MyBot2/releases/latest"
INSTALLER_NAME_PATTERN = re.compile(r"^MyBot2-Setup-(\d+\.\d+\.\d+)-x64\.exe$", re.IGNORECASE)
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

ProgressCallback = Callable[[int, str], None]


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True, order=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        match = VERSION_PATTERN.fullmatch(str(value).strip())
        if match is None:
            raise ValueError(f"无效的版本号：{value}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str = ""
    release_notes: str = ""
    installer_name: str = ""
    installer_url: str = ""
    installer_sha256: str = ""
    checksum_url: str = ""

    @property
    def installable(self) -> bool:
        return bool(self.update_available and self.installer_url and (
            self.installer_sha256 or self.checksum_url
        ))


class UpdateManager:
    def __init__(self, project_root: str | Path, current_version: str) -> None:
        self.project_root = Path(project_root).resolve()
        self.current_version = str(SemanticVersion.parse(current_version))
        self.download_dir = self.project_root / "data" / "updates"

    def check(self) -> UpdateInfo:
        request = Request(
            GITHUB_LATEST_RELEASE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "MyBot-Updater",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise UpdateError(f"无法检查 GitHub 最新版本：{exc}") from exc
        try:
            latest = SemanticVersion.parse(str(payload["tag_name"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise UpdateError("GitHub 最新 Release 的版本号不是有效的 2.x.x 格式。") from exc
        current = SemanticVersion.parse(self.current_version)
        assets = payload.get("assets", [])
        assets = assets if isinstance(assets, list) else []
        installer = next(
            (
                asset
                for asset in assets
                if isinstance(asset, dict)
                and INSTALLER_NAME_PATTERN.fullmatch(str(asset.get("name", "")))
                and SemanticVersion.parse(
                    INSTALLER_NAME_PATTERN.fullmatch(str(asset.get("name", ""))).group(1)
                ) == latest
            ),
            None,
        )
        installer_name = str(installer.get("name", "")) if installer else ""
        checksum_name = installer_name + ".sha256" if installer_name else ""
        checksum_asset = next(
            (
                asset for asset in assets
                if isinstance(asset, dict) and str(asset.get("name", "")) == checksum_name
            ),
            None,
        )
        digest = str(installer.get("digest", "")) if installer else ""
        installer_sha256 = digest.removeprefix("sha256:") if digest.startswith("sha256:") else ""
        return UpdateInfo(
            current_version=str(current),
            latest_version=str(latest),
            update_available=latest > current,
            release_url=str(payload.get("html_url", "")),
            release_notes=str(payload.get("body", "")),
            installer_name=installer_name,
            installer_url=str(installer.get("browser_download_url", "")) if installer else "",
            installer_sha256=installer_sha256,
            checksum_url=(
                str(checksum_asset.get("browser_download_url", ""))
                if checksum_asset else ""
            ),
        )

    def download(self, info: UpdateInfo, progress: ProgressCallback | None = None) -> Path:
        if not info.installable:
            raise UpdateError("最新 Release 没有可校验的 MyBot2 Windows 安装包。")
        callback = progress or (lambda _percent, _message: None)
        expected_sha256 = info.installer_sha256 or self._download_checksum(
            info.checksum_url,
            info.installer_name,
        )
        self.download_dir.mkdir(parents=True, exist_ok=True)
        destination = self.download_dir / info.installer_name
        temporary = destination.with_suffix(destination.suffix + ".part")
        callback(1, "准备下载更新")
        request = Request(info.installer_url, headers={"User-Agent": "MyBot-Updater"})
        try:
            with urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
                total = int(response.headers.get("Content-Length", "0") or 0)
                downloaded = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    stream.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        callback(
                            min(95, max(1, int(downloaded * 95 / total))),
                            f"下载 MyBot {info.latest_version} {downloaded // (1024 * 1024)} MB",
                        )
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise UpdateError(f"安装包下载失败：{exc}") from exc
        callback(96, "校验安装包")
        actual_sha256 = self._sha256(temporary)
        if actual_sha256.lower() != expected_sha256.lower():
            temporary.unlink(missing_ok=True)
            raise UpdateError("安装包 SHA256 校验失败，更新已取消。")
        os.replace(temporary, destination)
        callback(100, "更新包下载完成")
        return destination

    @staticmethod
    def _download_checksum(url: str, installer_name: str) -> str:
        request = Request(url, headers={"User-Agent": "MyBot-Updater"})
        try:
            with urlopen(request, timeout=20) as response:
                content = response.read().decode("utf-8")
        except Exception as exc:
            raise UpdateError(f"无法下载安装包校验文件：{exc}") from exc
        match = re.search(
            rf"^([0-9a-fA-F]{{64}})\s+\*?{re.escape(installer_name)}$",
            content,
            re.MULTILINE,
        )
        if match is None:
            raise UpdateError("安装包校验文件内容无效。")
        return match.group(1)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
