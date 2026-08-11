[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [int]$MyBotProcessId = 0,
    [string]$LockPath = "",
    [ValidateRange(0, 60)][int]$GracePeriodSeconds = 10
)

$ErrorActionPreference = "Stop"
$resolvedRoot = [IO.Path]::GetFullPath($InstallRoot)
if ([string]::IsNullOrWhiteSpace($LockPath)) {
    $LockPath = Join-Path $env:TEMP "mybot-2.0-ui.lock"
}

$targetId = $MyBotProcessId
$explicitTarget = $targetId -gt 0
if (-not $explicitTarget -and (Test-Path -LiteralPath $LockPath)) {
    $firstLine = Get-Content -LiteralPath $LockPath -TotalCount 1 -ErrorAction SilentlyContinue
    $parsedId = 0
    if ([int]::TryParse([string]$firstLine, [ref]$parsedId)) {
        $targetId = $parsedId
    }
}
if ($targetId -le 0) {
    return
}

$cimProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $targetId" -ErrorAction SilentlyContinue
if (-not $cimProcess) {
    return
}

$process = Get-Process -Id $targetId -ErrorAction SilentlyContinue
if (-not $process) {
    return
}

if (-not $explicitTarget) {
    $name = [IO.Path]::GetFileNameWithoutExtension([string]$cimProcess.Name)
    $commandLine = [string]$cimProcess.CommandLine
    $embeddedPython = [IO.Path]::GetFullPath((Join-Path $resolvedRoot "runtime\python\python.exe"))
    $processPath = if ($cimProcess.ExecutablePath) {
        [IO.Path]::GetFullPath([string]$cimProcess.ExecutablePath)
    } else {
        ""
    }
    $lockItem = Get-Item -LiteralPath $LockPath -ErrorAction SilentlyContinue
    $lockMatchesStart = $lockItem -and (
        $lockItem.LastWriteTimeUtc -ge $process.StartTime.ToUniversalTime().AddSeconds(-5)
    )
    $pythonProcess = $name -in @("python", "pythonw")
    $myBotCommand = $commandLine -match '(?i)(^|[\\/"''\s])main\.py(["''\s]|$)'
    $embeddedProcess = $processPath.Equals($embeddedPython, [StringComparison]::OrdinalIgnoreCase)
    if (-not ($lockMatchesStart -and $pythonProcess -and ($myBotCommand -or $embeddedProcess))) {
        return
    }
}

$null = $process.CloseMainWindow()
$deadline = [DateTime]::UtcNow.AddSeconds($GracePeriodSeconds)
while ((Get-Process -Id $targetId -ErrorAction SilentlyContinue) -and [DateTime]::UtcNow -lt $deadline) {
    Start-Sleep -Milliseconds 200
}
if (Get-Process -Id $targetId -ErrorAction SilentlyContinue) {
    Stop-Process -Id $targetId -Force -ErrorAction Stop
}

$forceDeadline = [DateTime]::UtcNow.AddSeconds(5)
while ((Get-Process -Id $targetId -ErrorAction SilentlyContinue) -and [DateTime]::UtcNow -lt $forceDeadline) {
    Start-Sleep -Milliseconds 100
}
if (Get-Process -Id $targetId -ErrorAction SilentlyContinue) {
    throw "MyBot process $targetId did not exit."
}

if (Test-Path -LiteralPath $LockPath) {
    $lockOwner = Get-Content -LiteralPath $LockPath -TotalCount 1 -ErrorAction SilentlyContinue
    if ([string]$lockOwner -eq [string]$targetId) {
        Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
    }
}
