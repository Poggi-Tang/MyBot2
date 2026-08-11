import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from mybot_ui.app_v2 import MainWindow


class ApplicationRestartTests(unittest.TestCase):
    def test_helper_waits_for_current_process_then_runs_canonical_entrypoint(self):
        args = MainWindow._restart_application_helper(
            4321,
            Path(r"C:\Projects\MyBot2"),
        )

        self.assertEqual("powershell.exe", args[0])
        command = args[-1]
        self.assertIn("$ErrorActionPreference='Stop'", command)
        self.assertIn("Get-Process -Id 4321", command)
        self.assertIn("run.cmd", command)
        self.assertIn("restart-helper.log", command)
        self.assertIn("restart failed", command)
        self.assertIn(r"C:\Projects\MyBot2", command)

    @unittest.skipUnless(os.name == "nt", "Windows restart helper")
    def test_helper_survives_the_parent_process_and_launches_run_cmd(self):
        with tempfile.TemporaryDirectory() as directory:
            app_root = Path(directory)
            marker = app_root / "restart-marker.txt"
            (app_root / "run.cmd").write_text(
                "@echo off\r\necho started>restart-marker.txt\r\n",
                encoding="ascii",
            )
            launcher = "\n".join(
                [
                    "import os, subprocess",
                    "from pathlib import Path",
                    "from mybot_ui.app_v2 import MainWindow",
                    f"root = Path({str(app_root)!r})",
                    "subprocess.Popen(",
                    "    MainWindow._restart_application_helper(os.getpid(), root),",
                    "    cwd=str(root),",
                    "    stdin=subprocess.DEVNULL,",
                    "    stdout=subprocess.DEVNULL,",
                    "    stderr=subprocess.DEVNULL,",
                    "    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),",
                    ")",
                ]
            )

            completed = subprocess.run(
                [sys.executable, "-c", launcher],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)

            deadline = time.monotonic() + 10
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            helper_log = app_root / "logs" / "restart-helper.log"
            detail = helper_log.read_text(encoding="utf-8") if helper_log.exists() else ""
            self.assertTrue(marker.exists(), detail)
            # cmd.exe creates the marker before releasing its working-directory handle.
            time.sleep(1)


if __name__ == "__main__":
    unittest.main()
