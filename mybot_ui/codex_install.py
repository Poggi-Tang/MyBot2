from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen


CODEX_PACKAGE_NAME = "codex-package-x86_64-pc-windows-msvc.tar.gz"
CODEX_RELEASE_BASE_URL = "https://github.com/openai/codex/releases/latest/download"
CODEX_PACKAGE_URL = f"{CODEX_RELEASE_BASE_URL}/{CODEX_PACKAGE_NAME}"
CODEX_CHECKSUM_URL = f"{CODEX_RELEASE_BASE_URL}/codex-package_SHA256SUMS"
CODEX_RELEASE_API_URL = "https://api.github.com/repos/openai/codex/releases/latest"
CODEX_EXECUTABLE_NAME = "codex-x86_64-pc-windows-msvc.exe"
CODEX_PROXY_NAME = "codex-responses-api-proxy-x86_64-pc-windows-msvc.exe"
REQUIRED_RUNTIME_FILES = (CODEX_EXECUTABLE_NAME, CODEX_PROXY_NAME)

ProgressCallback = Callable[[int, str], None]


class CodexInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexRuntimeStatus:
    installed: bool
    version: str = ""
    error: str = ""


@dataclass(frozen=True)
class CodexInstallResult:
    version: str
    runtime_dir: Path


@dataclass(frozen=True)
class CodexReleaseAssets:
    version: str
    package_url: str
    checksum_url: str
    proxy_url: str
    proxy_sha256: str


class CodexRuntimeManager:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_root = self.project_root / "data" / "codex"
        self.runtime_dir = self.data_root / "runtime"
        self.legacy_runtime_dir = self.project_root / "tools" / "codex"
        self.codex_home = self.data_root / "home"
        self.project_skills_dir = self.project_root / ".agents" / "skills"
        self._sync_project_skills()

    def _sync_project_skills(self) -> None:
        bundled = self.project_root / "codex" / "skills"
        if not bundled.is_dir():
            return
        self.project_skills_dir.mkdir(parents=True, exist_ok=True)
        for source in bundled.iterdir():
            if source.is_dir() and (source / "SKILL.md").is_file():
                shutil.copytree(
                    source,
                    self.project_skills_dir / source.name,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )

    @property
    def active_runtime_dir(self) -> Path:
        if self._runtime_complete(self.runtime_dir):
            return self.runtime_dir
        if self._runtime_complete(self.legacy_runtime_dir):
            return self.legacy_runtime_dir
        return self.runtime_dir if self.runtime_dir.exists() else self.legacy_runtime_dir

    @property
    def executable(self) -> Path:
        return self.active_runtime_dir / CODEX_EXECUTABLE_NAME

    @property
    def proxy_executable(self) -> Path:
        return self.active_runtime_dir / CODEX_PROXY_NAME

    @staticmethod
    def _runtime_complete(root: Path) -> bool:
        return all((root / name).is_file() for name in REQUIRED_RUNTIME_FILES)

    def status(self) -> CodexRuntimeStatus:
        runtime_files = {
            CODEX_EXECUTABLE_NAME: self.executable,
            CODEX_PROXY_NAME: self.proxy_executable,
        }
        missing = [name for name, path in runtime_files.items() if not path.is_file()]
        if missing:
            has_runtime = self.runtime_dir.exists() or self.legacy_runtime_dir.exists()
            error = "安装不完整" if has_runtime else ""
            return CodexRuntimeStatus(False, error=error)
        try:
            version = self._cli_version(self.executable)
        except CodexInstallError as exc:
            return CodexRuntimeStatus(False, error=str(exc))
        return CodexRuntimeStatus(True, version=version)

    def install(self, progress: ProgressCallback | None = None) -> CodexInstallResult:
        report = progress or (lambda _percent, _message: None)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.codex_home.mkdir(parents=True, exist_ok=True)
        report(2, "读取官方校验信息")
        release = self._latest_release_assets()
        checksum_text = self._download_text(release.checksum_url)
        expected_sha256 = self._package_checksum(checksum_text)

        with tempfile.TemporaryDirectory(prefix="install-", dir=self.data_root) as directory:
            temporary_root = Path(directory)
            package_path = temporary_root / CODEX_PACKAGE_NAME
            proxy_path = temporary_root / CODEX_PROXY_NAME
            extracted_dir = temporary_root / "extracted"
            prepared_dir = temporary_root / "runtime"
            report(5, "下载 OpenAI Codex CLI")
            self._download_file(
                release.package_url,
                package_path,
                report,
                progress_start=5,
                progress_end=70,
                label="Codex CLI",
            )
            report(71, "下载 Codex Responses 代理")
            self._download_file(
                release.proxy_url,
                proxy_path,
                report,
                progress_start=71,
                progress_end=75,
                label="Responses 代理",
            )
            report(76, "校验下载文件")
            actual_sha256 = self._sha256(package_path)
            if actual_sha256.lower() != expected_sha256.lower():
                raise CodexInstallError("Codex 官方包 SHA256 校验失败，安装已取消。")
            if self._sha256(proxy_path).lower() != release.proxy_sha256.lower():
                raise CodexInstallError("Codex 官方代理 SHA256 校验失败，安装已取消。")

            report(82, "解压 Codex CLI")
            extracted_dir.mkdir()
            self._safe_extract(package_path, extracted_dir)
            self._prepare_runtime(extracted_dir, prepared_dir)
            shutil.copy2(proxy_path, prepared_dir / CODEX_PROXY_NAME)
            report(92, "验证 Codex CLI")
            version = self._cli_version(prepared_dir / CODEX_EXECUTABLE_NAME)
            self._activate_runtime(prepared_dir)

        report(100, f"Codex CLI {version} 安装完成")
        return CodexInstallResult(version, self.runtime_dir)

    @classmethod
    def _latest_release_assets(cls) -> CodexReleaseAssets:
        try:
            release = json.loads(cls._download_text(CODEX_RELEASE_API_URL))
            tag = str(release["tag_name"]).strip()
            assets = {
                str(asset["name"]): asset
                for asset in release["assets"]
                if isinstance(asset, dict) and asset.get("name")
            }
            proxy = assets[CODEX_PROXY_NAME]
            proxy_url = str(proxy["browser_download_url"])
            proxy_digest = str(proxy["digest"])
            if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", proxy_digest):
                raise ValueError("官方代理没有有效 SHA256")
            expected_base = f"https://github.com/openai/codex/releases/download/{tag}/"
            if proxy_url != expected_base + CODEX_PROXY_NAME:
                raise ValueError("官方代理下载地址无效")
        except (KeyError, TypeError, ValueError) as exc:
            raise CodexInstallError(f"无法解析 OpenAI 官方 Codex Release：{exc}") from exc
        return CodexReleaseAssets(
            version=tag.removeprefix("rust-v"),
            package_url=expected_base + CODEX_PACKAGE_NAME,
            checksum_url=expected_base + "codex-package_SHA256SUMS",
            proxy_url=proxy_url,
            proxy_sha256=proxy_digest.removeprefix("sha256:"),
        )

    @staticmethod
    def _download_text(url: str) -> str:
        request = Request(url, headers={"User-Agent": "MyBot-Codex-Installer"})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            raise CodexInstallError(f"无法读取 OpenAI 官方 Codex Release：{exc}") from exc

    @staticmethod
    def _package_checksum(checksum_text: str) -> str:
        pattern = re.compile(
            rf"^([0-9a-fA-F]{{64}})\s+\*?{re.escape(CODEX_PACKAGE_NAME)}$",
            re.MULTILINE,
        )
        match = pattern.search(checksum_text)
        if match is None:
            raise CodexInstallError("OpenAI 官方校验清单中没有 Windows x64 Codex 包。")
        return match.group(1)

    @staticmethod
    def _download_file(
        url: str,
        destination: Path,
        progress: ProgressCallback,
        *,
        progress_start: int,
        progress_end: int,
        label: str,
    ) -> None:
        request = Request(url, headers={"User-Agent": "MyBot-Codex-Installer"})
        try:
            with urlopen(request, timeout=60) as response, destination.open("wb") as stream:
                total = int(response.headers.get("Content-Length", "0") or 0)
                downloaded = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    stream.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        span = max(0, progress_end - progress_start)
                        percent = progress_start + min(span, int(downloaded * span / total))
                        progress(percent, f"下载 {label} {downloaded // (1024 * 1024)} MB")
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise CodexInstallError(f"无法从 OpenAI 官方地址下载 {label}：{exc}") from exc

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe_extract(package_path: Path, destination: Path) -> None:
        destination = destination.resolve()
        try:
            with tarfile.open(package_path, mode="r:gz") as archive:
                for member in archive.getmembers():
                    target = (destination / member.name).resolve()
                    try:
                        target.relative_to(destination)
                    except ValueError as exc:
                        raise CodexInstallError("Codex 官方包包含不安全的文件路径。") from exc
                    if member.issym() or member.islnk():
                        raise CodexInstallError("Codex 官方包包含不支持的链接文件。")
                archive.extractall(destination, filter="data")
        except CodexInstallError:
            raise
        except (OSError, tarfile.TarError) as exc:
            raise CodexInstallError(f"Codex 官方包解压失败：{exc}") from exc

    @staticmethod
    def _prepare_runtime(extracted_dir: Path, prepared_dir: Path) -> None:
        prepared_dir.mkdir()
        discovered: dict[str, Path] = {}
        for path in extracted_dir.rglob("*"):
            if path.is_file():
                discovered.setdefault(path.name, path)
        cli_source = discovered.get(CODEX_EXECUTABLE_NAME) or discovered.get("codex.exe")
        if cli_source is None:
            raise CodexInstallError("Codex 官方包缺少 codex.exe。")
        for name, source in discovered.items():
            if source.suffix.lower() in {".exe", ".json"} or "SHA256SUMS" in name:
                shutil.copy2(source, prepared_dir / name)
        shutil.copy2(cli_source, prepared_dir / CODEX_EXECUTABLE_NAME)

    def _activate_runtime(self, prepared_dir: Path) -> None:
        staging_dir = self.data_root / f".runtime-{uuid.uuid4().hex}"
        backup_dir = self.data_root / f".runtime-backup-{uuid.uuid4().hex}"
        shutil.copytree(prepared_dir, staging_dir)
        try:
            if self.runtime_dir.exists():
                self._replace_directory(self.runtime_dir, backup_dir)
            self._replace_directory(staging_dir, self.runtime_dir)
        except Exception:
            if not self.runtime_dir.exists() and backup_dir.exists():
                self._replace_directory(backup_dir, self.runtime_dir)
            raise
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(backup_dir, ignore_errors=True)

    @staticmethod
    def _replace_directory(source: Path, destination: Path) -> None:
        deadline = time.monotonic() + 5
        while True:
            try:
                os.replace(source, destination)
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    @staticmethod
    def _cli_version(executable: Path) -> str:
        try:
            completed = subprocess.run(
                [str(executable), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CodexInstallError(f"无法启动已下载的 Codex CLI：{exc}") from exc
        output = (completed.stdout or completed.stderr).strip()
        if completed.returncode or not output:
            raise CodexInstallError("已下载的 Codex CLI 版本验证失败。")
        return output.removeprefix("codex-cli").strip() or output
