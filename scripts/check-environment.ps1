param([switch]$RequireRunningServices)

$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $appRoot
$bundledSdkRoot = Join-Path $appRoot "sdk\WeChatAuto4_X"
$workspaceSdkRoot = Join-Path $workspaceRoot "wechatautosdk\WeChatAuto4_X"
$sdkRoot = if (Test-Path -LiteralPath $bundledSdkRoot) { $bundledSdkRoot } else { $workspaceSdkRoot }
$configPath = Join-Path $appRoot "config.json"
$failures = 0

function Write-Check([string]$Name, [bool]$Ok, [string]$Detail, [bool]$Required = $true) {
    $label = if ($Ok) { "OK" } elseif ($Required) { "FAIL" } else { "INFO" }
    Write-Host ("[{0}] {1}: {2}" -f $label, $Name, $Detail)
    if (-not $Ok -and $Required) { $script:failures++ }
}

$embeddedPython = Join-Path $appRoot "runtime\python\python.exe"
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$pythonReady = (Test-Path -LiteralPath $embeddedPython) -or ($null -ne $pythonCommand)
$pythonDetail = if (Test-Path -LiteralPath $embeddedPython) {
    (& $embeddedPython --version 2>&1)
} elseif ($pythonCommand) {
    (python --version 2>&1)
} else {
    "not found"
}
Write-Check "Python" $pythonReady $pythonDetail

$packagedServer = Join-Path $appRoot "runtime\server\Server.exe"
$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
$dotnetVersion = if ($dotnetCommand) { dotnet --version } else { "not found" }
Write-Check ".NET runtime" ((Test-Path -LiteralPath $packagedServer) -or ($dotnetVersion -like "10.*")) $(
    if (Test-Path -LiteralPath $packagedServer) { "self-contained Server" } else { $dotnetVersion }
)
Write-Check "SDK source" ((Test-Path -LiteralPath $sdkRoot) -or (Test-Path -LiteralPath $packagedServer)) $(
    if (Test-Path -LiteralPath $sdkRoot) { $sdkRoot } else { "packaged runtime" }
)
Write-Check "Application config" (Test-Path -LiteralPath $configPath) $configPath

if (Test-Path -LiteralPath $configPath) {
    $config = Get-Content -Raw -Encoding UTF8 -LiteralPath $configPath | ConvertFrom-Json
    $uri = [Uri]$config.wechat.websocket_url
    Write-Check "WebSocket contract" ($uri.Host -in @("127.0.0.1", "localhost") -and $uri.AbsolutePath -eq "/ws") $uri.AbsoluteUri
    $serverExecutable = [string]$config.server.exe_path
    if ([string]::IsNullOrWhiteSpace($serverExecutable)) {
        $serverExecutable = $packagedServer
        if (-not (Test-Path -LiteralPath $serverExecutable)) {
            $serverExecutable = Join-Path $appRoot "sdk\WeChatAuto4_X\WebSocketServer\Server\bin\Debug\net10.0-windows\Server.exe"
        }
    } elseif (-not [IO.Path]::IsPathRooted($serverExecutable)) {
        $serverExecutable = Join-Path $appRoot $serverExecutable
    }
    Write-Check "Server executable" (Test-Path -LiteralPath $serverExecutable) $serverExecutable
    $primaryReady = -not [string]::IsNullOrWhiteSpace($config.primary.api_key) -and $config.primary.api_key -ne "replace-me"
    $optionalReady = @($config.backup.api_key, $config.image.api_key) | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and $_ -ne "replace-me"
    }
    Write-Check "Primary model credential" $primaryReady "value not displayed" $false
    Write-Check "Optional model credentials" ($optionalReady.Count -eq 2) ("{0}/2 configured; values not displayed" -f $optionalReady.Count) $false

    $serverListening = $null -ne (Get-NetTCPConnection -State Listen -LocalPort $uri.Port -ErrorAction SilentlyContinue)
    Write-Check "WebSocket Server" $serverListening ("127.0.0.1:{0}" -f $uri.Port) $RequireRunningServices
}

$wechatProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @("Weixin.exe", "WeChat.exe") })
$wechat = $wechatProcesses | Where-Object { $_.CommandLine -notmatch "\s--" } | Sort-Object ProcessId | Select-Object -First 1
if ($null -eq $wechat) { $wechat = $wechatProcesses | Sort-Object ProcessId | Select-Object -First 1 }
Write-Check "WeChat process" ($null -ne $wechat) $(if ($wechat) { "PID=$($wechat.ProcessId), process=$($wechat.Name), instances=$($wechatProcesses.Count)" } else { "not running" }) $RequireRunningServices

$voiceListening = $null -ne (Get-NetTCPConnection -State Listen -LocalPort 50001 -ErrorAction SilentlyContinue)
Write-Check "Voice service" $voiceListening "127.0.0.1:50001" $false

if ($failures -gt 0) {
    Write-Error "$failures required environment check(s) failed."
    exit 1
}
Write-Host "Environment checks passed."
