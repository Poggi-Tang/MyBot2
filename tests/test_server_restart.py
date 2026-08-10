import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from mybot_ui.app_v2 import MainWindow


class ServerRestartTests(unittest.TestCase):
    @patch.object(MainWindow, "_server_pids", return_value=[42])
    @patch("mybot_ui.app_v2.socket.create_connection")
    @patch("mybot_ui.app_v2.subprocess.Popen")
    @patch("mybot_ui.app_v2.subprocess.run")
    def test_worker_stops_old_process_starts_server_and_waits_for_port(
        self,
        run,
        popen,
        create_connection,
        _server_pids,
    ):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        process = MagicMock(pid=1234)
        process.poll.return_value = None
        popen.return_value = process
        create_connection.return_value = MagicMock(
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )

        result = MainWindow._restart_server_worker(
            Path(r"F:\server\Server.exe"),
            "ws://127.0.0.1:5177/ws",
        )

        self.assertTrue(result.ok)
        self.assertEqual(1234, result.value["pid"])
        run.assert_called_once_with(
            ["taskkill.exe", "/PID", "42", "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        popen.assert_called_once()
        self.assertEqual("http://127.0.0.1:5177", popen.call_args.kwargs["env"]["ASPNETCORE_URLS"])
        create_connection.assert_called_once_with(("127.0.0.1", 5177), timeout=0.4)

    @patch.object(MainWindow, "_server_pids", return_value=[42])
    @patch("mybot_ui.app_v2.subprocess.Popen")
    @patch("mybot_ui.app_v2.subprocess.run")
    def test_worker_does_not_start_when_old_server_cannot_be_stopped(
        self,
        run,
        popen,
        _server_pids,
    ):
        run.return_value = subprocess.CompletedProcess([], 1, "", "Access denied")

        result = MainWindow._restart_server_worker(
            Path(r"F:\server\Server.exe"),
            "ws://127.0.0.1:5177/ws",
        )

        self.assertFalse(result.ok)
        self.assertIn("Access denied", result.error)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
