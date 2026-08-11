import hashlib
import io
import json
import shutil
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mybot_ui.codex_install import (
    CODEX_CHECKSUM_URL,
    CODEX_EXECUTABLE_NAME,
    CODEX_PACKAGE_NAME,
    CODEX_PACKAGE_URL,
    CODEX_PROXY_NAME,
    CODEX_RELEASE_API_URL,
    CodexInstallError,
    CodexReleaseAssets,
    CodexRuntimeManager,
)


class CodexRuntimeManagerTests(unittest.TestCase):
    def test_downloads_from_openai_latest_release(self):
        expected_base = "https://github.com/openai/codex/releases/latest/download/"
        self.assertTrue(CODEX_PACKAGE_URL.startswith(expected_base))
        self.assertTrue(CODEX_CHECKSUM_URL.startswith(expected_base))
        self.assertEqual(
            "https://api.github.com/repos/openai/codex/releases/latest",
            CODEX_RELEASE_API_URL,
        )

    @staticmethod
    def _release(proxy: bytes = b"proxy") -> CodexReleaseAssets:
        return CodexReleaseAssets(
            version="0.147.0",
            package_url="https://example.test/package",
            checksum_url="https://example.test/checksum",
            proxy_url="https://example.test/proxy",
            proxy_sha256=hashlib.sha256(proxy).hexdigest(),
        )

    @staticmethod
    def _package(path: Path, *, unsafe: bool = False) -> None:
        with tarfile.open(path, mode="w:gz") as archive:
            entries = {
                "bin/codex.exe": b"codex",
                "bin/codex-code-mode-host.exe": b"host",
                "../outside.txt": b"outside" if unsafe else b"",
            }
            for name, content in entries.items():
                if name == "../outside.txt" and not unsafe:
                    continue
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))

    def test_missing_runtime_is_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CodexRuntimeManager(directory)
            self.assertFalse(manager.status().installed)
            self.assertEqual("", manager.status().error)

    def test_release_metadata_locks_assets_to_the_same_official_tag(self):
        proxy_digest = "1" * 64
        metadata = {
            "tag_name": "rust-v0.147.0",
            "assets": [{
                "name": CODEX_PROXY_NAME,
                "browser_download_url": (
                    "https://github.com/openai/codex/releases/download/"
                    f"rust-v0.147.0/{CODEX_PROXY_NAME}"
                ),
                "digest": f"sha256:{proxy_digest}",
            }],
        }
        with patch.object(
            CodexRuntimeManager,
            "_download_text",
            return_value=json.dumps(metadata),
        ):
            release = CodexRuntimeManager._latest_release_assets()

        self.assertEqual("0.147.0", release.version)
        self.assertIn("/rust-v0.147.0/", release.package_url)
        self.assertIn("/rust-v0.147.0/", release.checksum_url)
        self.assertEqual(proxy_digest, release.proxy_sha256)

    def test_install_verifies_and_activates_official_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "source.tar.gz"
            self._package(package)
            checksum = hashlib.sha256(package.read_bytes()).hexdigest()
            manager = CodexRuntimeManager(root / "project")
            progress = []

            def download(url: str, destination: Path, callback, **_kwargs) -> None:
                if url.endswith("proxy"):
                    destination.write_bytes(b"proxy")
                else:
                    shutil.copy2(package, destination)
                callback(50, "下载中")

            with patch.object(
                manager,
                "_download_text",
                return_value=f"{checksum}  {CODEX_PACKAGE_NAME}\n",
            ), patch.object(
                manager,
                "_latest_release_assets",
                return_value=self._release(),
            ), patch.object(manager, "_download_file", side_effect=download), patch.object(
                manager,
                "_cli_version",
                return_value="0.147.0",
            ):
                result = manager.install(lambda percent, message: progress.append((percent, message)))
                status = manager.status()

            self.assertEqual("0.147.0", result.version)
            self.assertTrue(manager.executable.is_file())
            self.assertTrue(manager.proxy_executable.is_file())
            self.assertTrue(manager.codex_home.is_dir())
            self.assertTrue(status.installed)
            self.assertEqual(100, progress[-1][0])

    def test_checksum_mismatch_does_not_activate_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "source.tar.gz"
            self._package(package)
            manager = CodexRuntimeManager(root / "project")

            with patch.object(
                manager,
                "_download_text",
                return_value=f"{'0' * 64}  {CODEX_PACKAGE_NAME}\n",
            ), patch.object(
                manager,
                "_latest_release_assets",
                return_value=self._release(),
            ), patch.object(
                manager,
                "_download_file",
                side_effect=lambda url, destination, _progress, **_kwargs: (
                    destination.write_bytes(b"proxy")
                    if url.endswith("proxy")
                    else shutil.copy2(package, destination)
                ),
            ):
                with self.assertRaisesRegex(CodexInstallError, "SHA256"):
                    manager.install()

            self.assertFalse(manager.runtime_dir.exists())

    def test_archive_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "unsafe.tar.gz"
            destination = root / "output"
            destination.mkdir()
            self._package(package, unsafe=True)

            with self.assertRaisesRegex(CodexInstallError, "不安全"):
                CodexRuntimeManager._safe_extract(package, destination)

            self.assertFalse((root / "outside.txt").exists())

    def test_directory_activation_retries_transient_windows_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            attempts = []

            def replace(current: Path, target: Path) -> None:
                attempts.append((current, target))
                if len(attempts) == 1:
                    raise PermissionError("temporarily locked")
                current.rename(target)

            with patch("mybot_ui.codex_install.os.replace", side_effect=replace), patch.object(
                time,
                "sleep",
                return_value=None,
            ):
                CodexRuntimeManager._replace_directory(source, destination)

            self.assertEqual(2, len(attempts))
            self.assertTrue(destination.is_dir())


if __name__ == "__main__":
    unittest.main()
