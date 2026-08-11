import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows packaged launcher")
class PackagedLaunchTests(unittest.TestCase):
    def test_first_launch_applies_installer_options_before_config_check(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(project_root / "run.ps1", root / "run.ps1")
            shutil.copy2(project_root / "config.example.json", root / "config.example.json")
            package = root / "mybot_ui"
            package.mkdir()
            shutil.copy2(project_root / "mybot_ui" / "__init__.py", package / "__init__.py")
            shutil.copy2(
                project_root / "mybot_ui" / "install_options.py",
                package / "install_options.py",
            )
            (root / "install-options.ini").write_text(
                """[install]
defer_api=1
packaged_server=1
sdk_catalog=1
abilities=1
""",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(root / "run.ps1"),
                    "-PrepareOnly",
                    "-NoEnvironmentCheck",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse((root / "install-options.ini").exists())
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual("runtime/server/Server.exe", config["server"]["exe_path"])
            self.assertEqual(
                {"sdk_catalog": True, "abilities": True},
                config["features"],
            )


if __name__ == "__main__":
    unittest.main()
