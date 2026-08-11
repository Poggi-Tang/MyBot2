import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows environment checker")
class EnvironmentScriptTests(unittest.TestCase):
    def _workspace(self, websocket_url: str):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        scripts = root / "scripts"
        scripts.mkdir()
        project_root = Path(__file__).resolve().parents[1]
        shutil.copy2(
            project_root / "scripts" / "check-environment.ps1",
            scripts / "check-environment.ps1",
        )
        server = root / "runtime" / "server" / "Server.exe"
        server.parent.mkdir(parents=True)
        server.write_bytes(b"test")
        config = {
            "wechat": {"websocket_url": websocket_url},
            "server": {"exe_path": "runtime/server/Server.exe"},
            "primary": {"api_key": "replace-me"},
            "backup": {"api_key": "replace-me"},
            "image": {"api_key": "replace-me"},
        }
        (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        return temporary, root, scripts / "check-environment.ps1"

    @staticmethod
    def _run(script: Path, root: Path):
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_deferred_api_and_configured_local_port_are_allowed(self):
        temporary, root, script = self._workspace("ws://127.0.0.1:54321/ws")
        with temporary:
            completed = self._run(script, root)
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("[INFO] Primary model credential", completed.stdout)
            self.assertIn("Environment checks passed", completed.stdout)

    def test_non_local_websocket_endpoint_is_rejected(self):
        temporary, root, script = self._workspace("ws://example.com:5177/ws")
        with temporary:
            completed = self._run(script, root)
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("[FAIL] WebSocket contract", completed.stdout)


if __name__ == "__main__":
    unittest.main()
