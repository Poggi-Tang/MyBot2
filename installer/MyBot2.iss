#ifndef MyAppVersion
  #define MyAppVersion "2.3.1"
#endif
#ifndef SourceRoot
  #define SourceRoot ".."
#endif

#define MyAppName "MyBot2"
#define MyAppPublisher "Poggi-Tang"
#define MyAppURL "https://github.com/Poggi-Tang/MyBot2"
#define MyAppExeName "run.cmd"

[Setup]
AppId={{6E1300B8-AB5D-45F9-8CF2-B5E9A193264D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\MyBot2
DefaultGroupName=MyBot2
DisableProgramGroupPage=yes
OutputDir={#SourceRoot}\dist
OutputBaseFilename=MyBot2-Setup-{#MyAppVersion}-x64
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName=MyBot2 {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}.0

[Types]
Name: "recommended"; Description: "推荐安装"
Name: "full"; Description: "完整安装"
Name: "custom"; Description: "自定义安装"; Flags: iscustom

[Components]
Name: "core"; Description: "MyBot 核心程序与自包含微信 Server"; Types: recommended full custom; Flags: fixed
Name: "python"; Description: "内置 Python 3.13 运行环境"; Types: full
Name: "sdkcatalog"; Description: "功能列表与 SDK 开发/完整测试资源"; Types: recommended full
Name: "abilities"; Description: "快捷能力与配音 Skill"; Types: recommended full
Name: "codex"; Description: "Codex CLI 扩展（约 370 MB，之后也可在软件内安装）"; Types: full

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked
Name: "startmenuicon"; Description: "创建开始菜单快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Dirs]
Name: "{app}\data"
Name: "{app}\logs"

[Files]
Source: "{#SourceRoot}\scripts\stop-mybot.ps1"; Flags: dontcopy
Source: "{#SourceRoot}\main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\run.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\run.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\setup.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\check-environment.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\requirements-runtime.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\VERSIONING.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\mybot_ui\*"; DestDir: "{app}\mybot_ui"; Excludes: "__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\mybot_mcp\*"; DestDir: "{app}\mybot_mcp"; Excludes: "__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\scripts\*"; DestDir: "{app}\scripts"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\build\runtime\server\*"; DestDir: "{app}\runtime\server"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\build\runtime\python\*"; DestDir: "{app}\runtime\python"; Components: python; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\sdk\*"; DestDir: "{app}\sdk"; Components: sdkcatalog; Excludes: "**\bin\*,**\obj\*,**\logs\*,**\artifacts\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\extensions\*"; DestDir: "{app}\extensions"; Components: abilities; Excludes: ".candidates\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\codex\skills\*"; DestDir: "{app}\codex\skills"; Components: abilities; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\build\runtime\codex\*"; DestDir: "{app}\data\codex\runtime"; Components: codex; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{autodesktop}\MyBot2"; Filename: "{cmd}"; Parameters: "/d /c ""{app}\run.cmd"""; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\MyBot2"; Filename: "{cmd}"; Parameters: "/d /c ""{app}\run.cmd"""; WorkingDir: "{app}"; Tasks: startmenuicon
Name: "{group}\卸载 MyBot2"; Filename: "{uninstallexe}"

[Run]
Filename: "{cmd}"; Parameters: "/d /c ""{app}\run.cmd"""; WorkingDir: "{app}"; Description: "启动 MyBot2"; Flags: nowait postinstall skipifsilent
Filename: "{cmd}"; Parameters: "/d /c ""{app}\run.cmd"""; WorkingDir: "{app}"; Flags: nowait runhidden; Check: IsUpdateMode

[Code]
var
  ApiPage: TInputQueryWizardPage;
  ApiChoicePage: TInputOptionWizardPage;
  ComponentDefaultsApplied: Boolean;

function IsUpdateMode: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;

function HasCompatibleSystemPython: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(
    ExpandConstant('{cmd}'),
    '/d /c python -c "import PySide6,websockets,PIL"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  ) and (ResultCode = 0);
end;

procedure InitializeWizard;
begin
  ApiChoicePage := CreateInputOptionPage(
    wpSelectComponents,
    '模型 API 配置',
    '选择现在配置或稍后在 MyBot 中填写',
    'API 密钥会保存到安装目录的 config.json，本页不会发送密钥。',
    True, False
  );
  ApiChoicePage.Add('稍后在 MyBot 的“系统配置 → 模型配置”中填写');
  ApiChoicePage.Add('现在配置主模型 API');
  ApiChoicePage.SelectedValueIndex := 0;

  ApiPage := CreateInputQueryPage(
    ApiChoicePage.ID,
    '主模型 API',
    '填写 OpenAI 兼容接口',
    '选择稍后配置时，本页内容不会写入配置。'
  );
  ApiPage.Add('API 地址：', False);
  ApiPage.Add('模型：', False);
  ApiPage.Add('API 密钥：', True);
  ApiPage.Values[0] := 'https://api.openai.com/v1';
  ApiPage.Values[1] := 'gpt-5.6-sol';
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Selected: String;
begin
  if (CurPageID = wpSelectComponents) and not ComponentDefaultsApplied then
  begin
    Selected := 'core,sdkcatalog,abilities';
    if not HasCompatibleSystemPython then
      Selected := Selected + ',python';
    WizardSelectComponents(Selected);
    ComponentDefaultsApplied := True;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = ApiPage.ID) and (ApiChoicePage.SelectedValueIndex = 0);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectComponents)
    and not WizardIsComponentSelected('python')
    and not HasCompatibleSystemPython then
  begin
    MsgBox('没有检测到包含 PySide6、websockets 和 Pillow 的 Python 环境。请勾选“内置 Python 3.13 运行环境”。', mbError, MB_OK);
    Result := False;
  end;
  if (CurPageID = ApiPage.ID) and (
    (Trim(ApiPage.Values[0]) = '') or
    (Trim(ApiPage.Values[1]) = '') or
    (Trim(ApiPage.Values[2]) = '')
  ) then
  begin
    MsgBox('请完整填写 API 地址、模型和密钥，或返回选择稍后配置。', mbError, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Pid, Script, ScriptPath, ScriptParams, ServerPath: String;
  ResultCode: Integer;
begin
  Result := '';
  Pid := ExpandConstant('{param:MYPID|0}');
  ExtractTemporaryFile('stop-mybot.ps1');
  ScriptPath := ExpandConstant('{tmp}\stop-mybot.ps1');
  ScriptParams := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' +
    AddQuotes(ScriptPath) + ' -InstallRoot ' + AddQuotes(ExpandConstant('{app}'));
  if Pid <> '0' then
    ScriptParams := ScriptParams + ' -MyBotProcessId ' + Pid;
  if not Exec(
    'powershell.exe', ScriptParams, '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode
  ) or (ResultCode <> 0) then
  begin
    Result := '无法停止正在运行的 MyBot。请手动退出后重试。';
    exit;
  end;
  ServerPath := ExpandConstant('{app}\runtime\server\Server.exe');
  Script := '-NoProfile -NonInteractive -WindowStyle Hidden -Command "$p=''' + ServerPath + '''; Get-CimInstance Win32_Process -Filter ''Name=''''Server.exe'''''' | Where-Object {$_.ExecutablePath -eq $p} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force}"';
  Exec('powershell.exe', Script, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OptionsPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    OptionsPath := ExpandConstant('{app}\install-options.ini');
    SetIniString('install', 'defer_api', IntToStr(Ord(ApiChoicePage.SelectedValueIndex = 0)), OptionsPath);
    SetIniString('install', 'packaged_server', '1', OptionsPath);
    SetIniString('install', 'sdk_catalog', IntToStr(Ord(WizardIsComponentSelected('sdkcatalog'))), OptionsPath);
    SetIniString('install', 'abilities', IntToStr(Ord(WizardIsComponentSelected('abilities'))), OptionsPath);
    SetIniString('install', 'codex_extension', IntToStr(Ord(WizardIsComponentSelected('codex'))), OptionsPath);
    if ApiChoicePage.SelectedValueIndex = 1 then
    begin
      SetIniString('primary', 'base_url', ApiPage.Values[0], OptionsPath);
      SetIniString('primary', 'model', ApiPage.Values[1], OptionsPath);
      SetIniString('primary', 'api_key', ApiPage.Values[2], OptionsPath);
    end;
  end;
end;
