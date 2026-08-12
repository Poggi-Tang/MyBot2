from __future__ import annotations

import subprocess
from pathlib import Path


def _powershell_literal(value: str | Path) -> str:
    return str(value).replace("'", "''")


def restart_helper_command(process_id: int, app_root: Path) -> list[str]:
    root = app_root.resolve()
    escaped_root = _powershell_literal(root)
    escaped_log = _powershell_literal(root / "logs" / "restart-helper.log")
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$root='{escaped_root}'; $log='{escaped_log}'; "
        "try { "
        "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null; "
        f"Add-Content -LiteralPath $log -Value ('{{0:o}} waiting for PID {int(process_id)}' -f [DateTime]::Now); "
        f"while (Get-Process -Id {int(process_id)} -ErrorAction SilentlyContinue) "
        "{ Start-Sleep -Milliseconds 200 }; "
        "Start-Sleep -Milliseconds 300; "
        "$exe=Join-Path $root 'MyBot2.exe'; $cmd=Join-Path $root 'run.cmd'; "
        "if (Test-Path -LiteralPath $exe -PathType Leaf) { "
        "$child=Start-Process -FilePath $exe -WorkingDirectory $root -WindowStyle Hidden -PassThru; "
        "$entry='MyBot2.exe' "
        "} elseif (Test-Path -LiteralPath $cmd -PathType Leaf) { "
        "$child=Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d','/c',$cmd) "
        "-WorkingDirectory $root -WindowStyle Hidden -PassThru; $entry='run.cmd' "
        "} else { throw 'MyBot2.exe and run.cmd are both missing' }; "
        "Add-Content -LiteralPath $log -Value ('{0:o} launched {1}, PID {2}' -f [DateTime]::Now,$entry,$child.Id) "
        "} catch { "
        "Add-Content -LiteralPath $log -Value ('{0:o} restart failed: {1}' -f [DateTime]::Now,$_.Exception.Message); "
        "exit 1 }"
    )
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle",
        "Hidden",
        "-Command",
        script,
    ]


def launch_restart_helper(process_id: int, app_root: Path) -> subprocess.Popen:
    root = app_root.resolve()
    return subprocess.Popen(
        restart_helper_command(process_id, root),
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
