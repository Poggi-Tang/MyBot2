param(
    [string]$Version = "",
    [switch]$SkipPythonRuntime,
    [switch]$SkipServerPublish
)

$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $appRoot "build\runtime"
$pythonRoot = Join-Path $buildRoot "python"
$serverRoot = Join-Path $buildRoot "server"
$launcherRoot = Join-Path $appRoot "build\launcher"
$pyInstallerRoot = Join-Path $appRoot "build\pyinstaller"
$launcherVersionPath = Join-Path $pyInstallerRoot "version.txt"
$iconPath = Join-Path $appRoot "assets\MyBot2.ico"
$distRoot = Join-Path $appRoot "dist"

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = & python -c "from mybot_ui import __version__; print(__version__)"
}
if ($Version -notmatch '^2\.\d+\.\d+$') {
    throw "Installer version must use 2.x.x: $Version"
}

New-Item -ItemType Directory -Force -Path $buildRoot, $launcherRoot, $pyInstallerRoot, $distRoot | Out-Null

& python (Join-Path $appRoot "scripts\generate-app-icon.py") `
    (Join-Path $appRoot "assets\logo.svg") $iconPath
if ($LASTEXITCODE -ne 0) { throw "Application icon generation failed." }
& python (Join-Path $appRoot "scripts\generate_windows_version.py") `
    $Version $launcherVersionPath
if ($LASTEXITCODE -ne 0) { throw "Launcher version resource generation failed." }

python -m pip install --disable-pip-version-check -r (Join-Path $appRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed." }
python -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --name MyBot2 `
    --icon $iconPath `
    --version-file $launcherVersionPath `
    --distpath $launcherRoot `
    --workpath $pyInstallerRoot `
    --specpath $pyInstallerRoot `
    (Join-Path $appRoot "launcher.py")
if ($LASTEXITCODE -ne 0) { throw "MyBot2 launcher compilation failed." }

if (-not $SkipServerPublish) {
    if (Test-Path -LiteralPath $serverRoot) { Remove-Item -LiteralPath $serverRoot -Recurse -Force }
    dotnet publish `
        (Join-Path $appRoot "sdk\WeChatAuto4_X\WebSocketServer\Server\Server.csproj") `
        -c Release -r win-x64 --self-contained true `
        -p:PublishSingleFile=true -p:DebugType=None -p:DebugSymbols=false `
        -o $serverRoot
    if ($LASTEXITCODE -ne 0) { throw "Server publish failed." }
}

if (-not $SkipPythonRuntime) {
    $pythonVersion = "3.13.14"
    $pythonArchive = Join-Path $env:TEMP "python-$pythonVersion-embed-amd64.zip"
    if (-not (Test-Path -LiteralPath $pythonArchive)) {
        Invoke-WebRequest `
            -Uri "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip" `
            -OutFile $pythonArchive
    }
    if (Test-Path -LiteralPath $pythonRoot) { Remove-Item -LiteralPath $pythonRoot -Recurse -Force }
    Expand-Archive -LiteralPath $pythonArchive -DestinationPath $pythonRoot
    New-Item -ItemType Directory -Force -Path (Join-Path $pythonRoot "Lib\site-packages") | Out-Null
    python -m pip install `
        --disable-pip-version-check `
        --no-compile `
        --target (Join-Path $pythonRoot "Lib\site-packages") `
        -r (Join-Path $appRoot "requirements-runtime.txt")
    if ($LASTEXITCODE -ne 0) { throw "Embedded Python dependencies failed." }
    Remove-Item -LiteralPath (Join-Path $pythonRoot "Lib\site-packages\bin") -Recurse -Force -ErrorAction SilentlyContinue
    $pysideRoot = Join-Path $pythonRoot "Lib\site-packages\PySide6"
    @("doc", "glue", "include", "lib", "qml", "scripts", "support", "typesystems") | ForEach-Object {
        Remove-Item -LiteralPath (Join-Path $pysideRoot $_) -Recurse -Force -ErrorAction SilentlyContinue
    }
    @(
        "python313.zip"
        "."
        "Lib\site-packages"
        "..\.."
        "import site"
    ) | Set-Content -LiteralPath (Join-Path $pythonRoot "python313._pth") -Encoding ASCII
    & (Join-Path $pythonRoot "python.exe") -c "import PySide6, websockets, PIL; print('embedded runtime ok')"
    if ($LASTEXITCODE -ne 0) { throw "Embedded Python validation failed." }
}

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 is not installed." }

& $iscc "/DMyAppVersion=$Version" "/DSourceRoot=$appRoot" (Join-Path $appRoot "installer\MyBot2.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }

$installer = Join-Path $distRoot "MyBot2-Setup-$Version-x64.exe"
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer output not found: $installer" }
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($installer))" | Set-Content -LiteralPath "$installer.sha256" -Encoding ASCII
Write-Host "Installer ready: $installer"
