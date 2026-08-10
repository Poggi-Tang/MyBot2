param(
    [switch]$SkipSdkBuild,
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $appRoot
$bundledSdkRoot = Join-Path $appRoot "sdk\WeChatAuto4_X"
$workspaceSdkRoot = Join-Path $workspaceRoot "wechatautosdk\WeChatAuto4_X"
$sdkRoot = if (Test-Path -LiteralPath $bundledSdkRoot) { $bundledSdkRoot } else { $workspaceSdkRoot }
$venvRoot = Join-Path $appRoot ".venv"
$configPath = Join-Path $appRoot "config.json"
$configExamplePath = Join-Path $appRoot "config.example.json"

if ($RecreateVenv -and (Test-Path -LiteralPath $venvRoot)) {
    $resolvedVenv = (Resolve-Path -LiteralPath $venvRoot).Path
    if (-not $resolvedVenv.StartsWith($appRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a virtual environment outside Mybot2.0: $resolvedVenv"
    }
    Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
}

if (-not (Test-Path -LiteralPath (Join-Path $venvRoot "Scripts\python.exe"))) {
    python -m venv $venvRoot
}

if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath $configExamplePath -Destination $configPath
    Write-Host "Created local config.json from config.example.json."
}

$python = Join-Path $venvRoot "Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip (exit code $LASTEXITCODE)." }
& $python -m pip install -r (Join-Path $appRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Failed to install Python dependencies (exit code $LASTEXITCODE)." }

if (-not $SkipSdkBuild) {
    if (-not (Test-Path -LiteralPath $sdkRoot)) {
        throw "WeChatAuto4_X not found: $sdkRoot"
    }
    & (Join-Path $sdkRoot "scripts\build.ps1")
    if ($LASTEXITCODE -ne 0) { throw "SDK build failed (exit code $LASTEXITCODE)." }
}

Write-Host "Environment ready. Add model credentials to: $configPath"
Write-Host "Then run: $appRoot\run.cmd"
