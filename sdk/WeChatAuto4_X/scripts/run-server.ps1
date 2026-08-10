param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug",
    [int]$Port = 5177,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$sdkRoot = Split-Path -Parent $PSScriptRoot
if (-not $NoBuild) { & (Join-Path $PSScriptRoot "build.ps1") -Configuration $Configuration }

$serverExe = Join-Path $sdkRoot "WebSocketServer\Server\bin\$Configuration\net10.0-windows\Server.exe"
if (-not (Test-Path -LiteralPath $serverExe)) { throw "Server executable not found: $serverExe" }

$existing = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) {
    $ownerPid = [int]$existing[0].OwningProcess
    $owner = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    if ($null -ne $owner -and $owner.ProcessName -eq "Server") {
        Write-Host "WeChatAuto4_X Server is already running at 127.0.0.1:$Port (PID=$ownerPid)."
        Write-Host "No second process was started. Stop the existing Server first to load a new build."
        exit 0
    }
    $ownerName = if ($null -ne $owner) { $owner.ProcessName } else { "unknown" }
    throw "Port $Port is occupied by another process: PID=$ownerPid, process=$ownerName."
}

$env:ASPNETCORE_URLS = "http://127.0.0.1:$Port"
Push-Location (Split-Path -Parent $serverExe)
try {
    Write-Host "Starting WeChatAuto4_X Server at http://127.0.0.1:$Port"
    & $serverExe
} finally {
    Pop-Location
}
