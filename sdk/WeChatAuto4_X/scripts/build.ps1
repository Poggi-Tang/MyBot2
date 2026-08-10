param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug"
)

$ErrorActionPreference = "Stop"
$sdkRoot = Split-Path -Parent $PSScriptRoot
$serverProject = Join-Path $sdkRoot "WebSocketServer\Server\Server.csproj"

Push-Location $sdkRoot
try {
    dotnet restore $serverProject --nologo
    if ($LASTEXITCODE -ne 0) { throw "dotnet restore failed (exit code $LASTEXITCODE)." }
    dotnet build $serverProject -c $Configuration --no-restore --nologo
    if ($LASTEXITCODE -ne 0) { throw "dotnet build failed (exit code $LASTEXITCODE)." }
} finally {
    Pop-Location
}
