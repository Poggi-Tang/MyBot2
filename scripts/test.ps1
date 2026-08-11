param(
    [switch]$SkipSdkBuild,
    [switch]$LiveSdk,
    [switch]$Live,
    [string]$TestAccount = ""
)

$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $appRoot
$bundledSdkRoot = Join-Path $appRoot "sdk\WeChatAuto4_X"
$workspaceSdkRoot = Join-Path $workspaceRoot "wechatautosdk\WeChatAuto4_X"
$sdkRoot = if (Test-Path -LiteralPath $bundledSdkRoot) { $bundledSdkRoot } else { $workspaceSdkRoot }
$python = Join-Path $appRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python).Source }

if (-not $SkipSdkBuild) {
    & (Join-Path $sdkRoot "scripts\build.ps1")
    if ($LASTEXITCODE -ne 0) { throw "SDK build failed (exit code $LASTEXITCODE)." }
}
if ($LiveSdk) {
    if ([string]::IsNullOrWhiteSpace($TestAccount)) {
        throw "-LiveSdk requires -TestAccount with an explicitly approved test account."
    }
    & (Join-Path $sdkRoot "scripts\test.ps1") -LiveWeChat -TestAccount $TestAccount
    if ($LASTEXITCODE -ne 0) { throw "SDK live tests failed (exit code $LASTEXITCODE)." }
}

Push-Location $appRoot
try {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($Live) {
        & $python tests\live_preview_probe.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $python tests\live_listener_probe.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
} finally {
    Pop-Location
}
