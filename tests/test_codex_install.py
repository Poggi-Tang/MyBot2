import hashlib
import io
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mybot_ui.codex_install import (
    CODEX_EXECUTABLE_NAME,
    CODEX_PACKAGE_NAME,
    CODEX_PROXY_NAME,
    CodexInstallError,
    CodexRuntimeManager,
)


class CodexRuntimeManagerTests(unittest.TestCase):
    @staticmethod
    def _package(path: Path, *, unsafe: bool = False) -> None:
        with tarfile.open(path, mode="w:gz") as archive:
            entries = {
                f"codex/{CODEX_EXECUTABLE_NAME}": b"codex",
                f"codex/{CODEX_PROXY_NAME}": b"proxy",
                "codex/codex-code-mode-host.exe": b"host",
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

    def test_install_verifies_and_activates_official_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "source.tar.gz"
            self._package(package)
            checksum = hashlib.sha256(package.read_bytes()).hexdigest()
            manager = CodexRuntimeManager(root / "project")
            progress = []

            def download(destination: Path, callback) -> None:
                shutil.copy2(package, destination)
                callback(50, "下载中")

            with patch.object(
                manager,
                "_download_text",
                return_value=f"{checksum}  {CODEX_PACKAGE_NAME}\n",
            ), patch.object(manager, "_download_package", side_effect=download), patch.object(
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
                "_download_package",
                side_effect=lambda destination, _progress: shutil.copy2(package, destination),
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


if __name__ == "__main__":
    unittest.main()
