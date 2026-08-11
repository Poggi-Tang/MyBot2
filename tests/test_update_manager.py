import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mybot_ui.update_manager import SemanticVersion, UpdateError, UpdateInfo, UpdateManager


class FakeResponse:
    def __init__(self, content: bytes, *, length: bool = True) -> None:
        self._stream = io.BytesIO(content)
        self.headers = {"Content-Length": str(len(content))} if length else {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


class UpdateManagerTests(unittest.TestCase):
    def test_semantic_version_uses_three_numeric_levels(self):
        self.assertGreater(SemanticVersion.parse("v2.3.0"), SemanticVersion.parse("2.2.9"))
        self.assertGreater(SemanticVersion.parse("2.3.1"), SemanticVersion.parse("2.3.0"))
        with self.assertRaises(ValueError):
            SemanticVersion.parse("2.3")

    def test_check_finds_newer_installable_release(self):
        payload = {
            "tag_name": "v2.3.0",
            "html_url": "https://github.com/Poggi-Tang/MyBot2/releases/tag/v2.3.0",
            "body": "更新说明",
            "assets": [
                {
                    "name": "MyBot2-Setup-2.3.0-x64.exe",
                    "browser_download_url": "https://example.com/setup.exe",
                    "digest": "sha256:" + "a" * 64,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory, patch(
            "mybot_ui.update_manager.urlopen",
            return_value=FakeResponse(json.dumps(payload).encode()),
        ):
            info = UpdateManager(directory, "2.2.0").check()

        self.assertTrue(info.update_available)
        self.assertTrue(info.installable)
        self.assertEqual("2.3.0", info.latest_version)
        self.assertEqual("a" * 64, info.installer_sha256)

    def test_same_version_does_not_offer_update(self):
        payload = {"tag_name": "v2.3.0", "assets": []}
        with tempfile.TemporaryDirectory() as directory, patch(
            "mybot_ui.update_manager.urlopen",
            return_value=FakeResponse(json.dumps(payload).encode()),
        ):
            info = UpdateManager(directory, "2.3.0").check()
        self.assertFalse(info.update_available)

    def test_download_requires_and_verifies_checksum(self):
        content = b"installer"
        checksum = hashlib.sha256(content).hexdigest()
        info = UpdateInfo(
            "2.2.0",
            "2.3.0",
            True,
            installer_name="MyBot2-Setup-2.3.0-x64.exe",
            installer_url="https://example.com/setup.exe",
            installer_sha256=checksum,
        )
        progress = []
        with tempfile.TemporaryDirectory() as directory, patch(
            "mybot_ui.update_manager.urlopen",
            return_value=FakeResponse(content),
        ):
            path = UpdateManager(directory, "2.2.0").download(
                info,
                lambda percent, message: progress.append((percent, message)),
            )
            self.assertEqual(content, path.read_bytes())
        self.assertEqual(100, progress[-1][0])

    def test_bad_checksum_removes_partial_download(self):
        info = UpdateInfo(
            "2.2.0",
            "2.3.0",
            True,
            installer_name="MyBot2-Setup-2.3.0-x64.exe",
            installer_url="https://example.com/setup.exe",
            installer_sha256="0" * 64,
        )
        with tempfile.TemporaryDirectory() as directory, patch(
            "mybot_ui.update_manager.urlopen",
            return_value=FakeResponse(b"bad"),
        ):
            manager = UpdateManager(directory, "2.2.0")
            with self.assertRaisesRegex(UpdateError, "SHA256"):
                manager.download(info)
            self.assertFalse(any(manager.download_dir.glob("*.part")))


if __name__ == "__main__":
    unittest.main()
