import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows process shutdown helper")
class StopMyBotScriptTests(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[1]
        self.stop_script = self.project_root / "scripts" / "stop-mybot.ps1"

    def _run_helper(self, root: Path, lock_path: Path, **options):
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.stop_script),
            "-InstallRoot",
            str(root),
            "-LockPath",
            str(lock_path),
            "-GracePeriodSeconds",
            "0",
        ]
        for name, value in options.items():
            command.extend([f"-{name}", str(value)])
        return subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)

    def test_lock_owned_by_mybot_python_process_is_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / "main.py"
            entrypoint.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
            lock_path = root / "mybot.lock"
            process = subprocess.Popen([sys.executable, str(entrypoint)])
            try:
                lock_path.write_text(f"{process.pid}\npython\ntest-host\ntest-id\n", encoding="utf-8")
                result = self._run_helper(root, lock_path)
                self.assertEqual(0, result.returncode, result.stderr)
                process.wait(timeout=5)
                self.assertFalse(lock_path.exists())
            finally:
                self._terminate(process)

    def test_stale_lock_does_not_stop_unrelated_python_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock_path = root / "mybot.lock"
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            try:
                lock_path.write_text(f"{process.pid}\npython\ntest-host\ntest-id\n", encoding="utf-8")
                result = self._run_helper(root, lock_path)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIsNone(process.poll())
            finally:
                self._terminate(process)

    def test_explicit_update_pid_is_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock_path = root / "missing.lock"
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            try:
                result = self._run_helper(root, lock_path, MyBotProcessId=process.pid)
                self.assertEqual(0, result.returncode, result.stderr)
                process.wait(timeout=5)
            finally:
                self._terminate(process)


if __name__ == "__main__":
    unittest.main()
