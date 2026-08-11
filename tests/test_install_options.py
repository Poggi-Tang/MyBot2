import json
import tempfile
import unittest
from pathlib import Path

from mybot_ui.install_options import INSTALL_OPTIONS_NAME, apply_pending_install_options


class InstallOptionsTests(unittest.TestCase):
    def _write_example(self, root: Path) -> None:
        (root / "config.example.json").write_text(
            json.dumps(
                {
                    "primary": {"provider": "old", "api_key": "existing"},
                    "server": {"exe_path": "old-server.exe"},
                    "features": {"existing": True, "codex_extension": True},
                }
            ),
            encoding="utf-8",
        )

    def test_no_pending_options_is_a_noop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(apply_pending_install_options(root), "")
            self.assertFalse((root / "config.json").exists())

    def test_first_run_merges_installer_choices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_example(root)
            (root / INSTALL_OPTIONS_NAME).write_text(
                """[install]
defer_api=0
packaged_server=1
sdk_catalog=0
abilities=1

[primary]
base_url=https://example.test/v1
model=test-model
api_key=test-key
""",
                encoding="utf-8",
            )

            message = apply_pending_install_options(root)
            data = json.loads((root / "config.json").read_text(encoding="utf-8"))

            self.assertTrue(message)
            self.assertFalse((root / INSTALL_OPTIONS_NAME).exists())
            self.assertEqual(data["server"]["exe_path"], "runtime/server/Server.exe")
            self.assertEqual(
                data["primary"],
                {
                    "provider": "openai",
                    "base_url": "https://example.test/v1",
                    "model": "test-model",
                    "api_key": "test-key",
                },
            )
            self.assertEqual(
                data["features"],
                {
                    "existing": True,
                    "sdk_catalog": False,
                    "abilities": True,
                },
            )

    def test_upgrade_preserves_existing_config_and_deferred_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_example(root)
            existing = {
                "primary": {"provider": "custom", "api_key": "keep-me"},
                "private_setting": {"keep": True},
            }
            (root / "config.json").write_text(json.dumps(existing), encoding="utf-8")
            (root / INSTALL_OPTIONS_NAME).write_text(
                """[install]
defer_api=1
packaged_server=1
sdk_catalog=1
abilities=0
""",
                encoding="utf-8",
            )

            apply_pending_install_options(root)
            data = json.loads((root / "config.json").read_text(encoding="utf-8"))

            self.assertEqual(data["primary"], existing["primary"])
            self.assertEqual(data["private_setting"], {"keep": True})
            self.assertEqual(data["server"]["exe_path"], "runtime/server/Server.exe")
            self.assertEqual(
                data["features"],
                {"sdk_catalog": True, "abilities": False},
            )


if __name__ == "__main__":
    unittest.main()
