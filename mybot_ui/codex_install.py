from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen


CODEX_RELEASE_TAG = "rust-v0.147.0"
CODEX_PACKAGE_NAME = "codex-package-x86_64-pc-windows-msvc.tar.gz"
CODEX_RELEASE_BASE_URL = (
    f"https://github.com/openai/codex/releases/download/{CODEX_RELEASE_TAG}"
)
CODEX_PACKAGE_URL = f"{CODEX_RELEASE_BASE_URL}/{CODEX_PACKAGE_NAME}"
CODEX_CHECKSUM_URL = f"{CODEX_RELEASE_BASE_URL}/codex-package_SHA256SUMS"
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


class CodexRuntimeManager:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_root = self.project_root / "data" / "codex"
        self.runtime_dir = self.data_root / "runtime"
        self.codex_home = self.data_root / "home"

    @property
    def executable(self) -> Path:
        return self.runtime_dir / CODEX_EXECUTABLE_NAME

    @property
    def proxy_executable(self) -> Path:
        return self.runtime_dir / CODEX_PROXY_NAME

    def status(self) -> CodexRuntimeStatus:
        missing = [name for name in REQUIRED_RUNTIME_FILES if not (self.runtime_dir / name).is_file()]
        if missing:
            error = "" if not self.runtime_dir.exists() else "安装不完整"
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
        checksum_text = self._download_text(CODEX_CHECKSUM_URL)
        expected_sha256 = self._package_checksum(checksum_text)

        with tempfile.TemporaryDirectory(prefix="install-", dir=self.data_root) as directory:
            temporary_root = Path(directory)
            package_path = temporary_root / CODEX_PACKAGE_NAME
            extracted_dir = temporary_root / "extracted"
            prepared_dir = temporary_root / "runtime"
            report(5, "下载 OpenAI Codex CLI")
            self._download_package(package_path, report)
            report(76, "校验下载文件")
            actual_sha256 = self._sha256(package_path)
            if actual_sha256.lower() != expected_sha256.lower():
                raise CodexInstallError("Codex 官方包 SHA256 校验失败，安装已取消。")

            report(82, "解压 Codex CLI")
            extracted_dir.mkdir()
            self._safe_extract(package_path, extracted_dir)
            self._prepare_runtime(extracted_dir, prepared_dir)
            report(92, "验证 Codex CLI")
            version = self._cli_version(prepared_dir / CODEX_EXECUTABLE_NAME)
            self._activate_runtime(prepared_dir)

        report(100, f"Codex CLI {version} 安装完成")
        return CodexInstallResult(version, self.runtime_dir)

    @staticmethod
    def _download_text(url: str) -> str:
        request = Request(url, headers={"User-Agent": "MyBot-Codex-Installer"})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            raise CodexInstallError(f"无法下载 OpenAI 官方校验文件：{exc}") from exc

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
    def _download_package(destination: Path, progress: ProgressCallback) -> None:
        request = Request(CODEX_PACKAGE_URL, headers={"User-Agent": "MyBot-Codex-Installer"})
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
                        percent = 5 + min(70, int(downloaded * 70 / total))
                        progress(percent, f"下载 Codex CLI {downloaded // (1024 * 1024)} MB")
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise CodexInstallError(f"无法从 OpenAI 官方地址下载 Codex CLI：{exc}") from exc

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
        missing = [name for name in REQUIRED_RUNTIME_FILES if name not in discovered]
        if missing:
            raise CodexInstallError("Codex 官方包缺少运行文件：" + "、".join(missing))
        for name, source in discovered.items():
            if source.suffix.lower() in {".exe", ".json"} or "SHA256SUMS" in name:
                shutil.copy2(source, prepared_dir / name)

    def _activate_runtime(self, prepared_dir: Path) -> None:
        staging_dir = self.data_root / f".runtime-{uuid.uuid4().hex}"
        backup_dir = self.data_root / f".runtime-backup-{uuid.uuid4().hex}"
        shutil.copytree(prepared_dir, staging_dir)
        try:
            if self.runtime_dir.exists():
                os.replace(self.runtime_dir, backup_dir)
            os.replace(staging_dir, self.runtime_dir)
        except Exception:
            if not self.runtime_dir.exists() and backup_dir.exists():
                os.replace(backup_dir, self.runtime_dir)
            raise
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(backup_dir, ignore_errors=True)

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
