param(
    [switch]$SkipServer,
    [switch]$NoEnvironmentCheck
)

$ErrorActionPreference = "Stop"
$appRoot = $PSScriptRoot
$configPath = Join-Path $appRoot "config.json"

function Test-WebSocketEndpoint {
    param(
        [Parameter(Mandatory = $true)][Uri]$Uri,
        [int]$TimeoutMilliseconds = 2000
    )

    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    $timeout = [System.Threading.CancellationTokenSource]::new(
        [TimeSpan]::FromMilliseconds($TimeoutMilliseconds)
    )
    try {
        $null = $socket.ConnectAsync($Uri, $timeout.Token).GetAwaiter().GetResult()
        return $socket.State -eq [System.Net.WebSockets.WebSocketState]::Open
    } catch {
        return $false
    } finally {
        $socket.Dispose()
        $timeout.Dispose()
    }
}

function Wait-WebSocketEndpoint {
    param(
        [Parameter(Mandatory = $true)][Uri]$Uri,
        [int]$TimeoutSeconds = 20
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $consecutiveSuccesses = 0
    do {
        if (Test-WebSocketEndpoint -Uri $Uri) {
            $consecutiveSuccesses++
            if ($consecutiveSuccesses -ge 2) { return $true }
        } else {
            $consecutiveSuccesses = 0
        }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

function Get-ConfiguredServerProcesses {
    param([Parameter(Mandatory = $true)][string]$ExecutablePath)

    $expected = [IO.Path]::GetFullPath($ExecutablePath)
    return @(
        Get-CimInstance Win32_Process -Filter "Name = 'Server.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ExecutablePath -and
                [IO.Path]::GetFullPath([string]$_.ExecutablePath).Equals(
                    $expected,
                    [StringComparison]::OrdinalIgnoreCase
                )
            }
    )
}

function Assert-PortAvailableForServer {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$ServerExecutable
    )

    $expected = [IO.Path]::GetFullPath($ServerExecutable)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
        $ownerPath = if ($owner -and $owner.ExecutablePath) {
            [IO.Path]::GetFullPath([string]$owner.ExecutablePath)
        } else {
            ""
        }
        if (-not $ownerPath.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Port $Port is occupied by PID $($listener.OwningProcess) ($ownerPath); refusing to replace an unrelated process."
        }
    }
}

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Missing config.json. Start from config.example.json and add local credentials."
}

$config = Get-Content -Raw -Encoding UTF8 -LiteralPath $configPath | ConvertFrom-Json
$uri = [Uri]$config.wechat.websocket_url
if (-not $NoEnvironmentCheck) {
    & (Join-Path $appRoot "scripts\check-environment.ps1")
}

$serverExe = [string]$config.server.exe_path
if (-not [IO.Path]::IsPathRooted($serverExe)) {
    $serverExe = [IO.Path]::GetFullPath((Join-Path $appRoot $serverExe))
}
if (-not (Test-Path -LiteralPath $serverExe)) {
    throw "Server.exe is not built: $serverExe"
}
$webSocketReady = Wait-WebSocketEndpoint -Uri $uri -TimeoutSeconds 2
if (-not $webSocketReady -and $SkipServer) {
    throw "WebSocket endpoint $uri is not ready and -SkipServer was specified."
}
if (-not $webSocketReady) {
    Assert-PortAvailableForServer -Port $uri.Port -ServerExecutable $serverExe
    $staleServers = @(Get-ConfiguredServerProcesses -ExecutablePath $serverExe)
    foreach ($staleServer in $staleServers) {
        Stop-Process -Id $staleServer.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($staleServers.Count -gt 0) {
        Start-Sleep -Milliseconds 500
    }

    $previousUrls = $env:ASPNETCORE_URLS
    try {
        $env:ASPNETCORE_URLS = "http://$($uri.Host):$($uri.Port)"
        $serverProcess = Start-Process `
            -FilePath $serverExe `
            -WorkingDirectory (Split-Path -Parent $serverExe) `
            -WindowStyle Hidden `
            -PassThru
    } finally {
        $env:ASPNETCORE_URLS = $previousUrls
    }
    if (-not (Wait-WebSocketEndpoint -Uri $uri -TimeoutSeconds 20)) {
        if ($serverProcess -and -not $serverProcess.HasExited) {
            Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
        }
        throw "WebSocket Server started as PID $($serverProcess.Id) but $uri did not accept a stable WebSocket connection within 20 seconds."
    }
}

$python = Join-Path $appRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python).Source }
Push-Location $appRoot
try {
    & $python main.py
} finally {
    Pop-Location
}
