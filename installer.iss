; ──────────────────────────────────────────────────
;  PaperReader - Inno Setup Installer Script
;
;  Prerequisites:
;    1. PyInstaller build done -> dist\PaperReader\
;    2. Install Inno Setup 7 (https://jrsoftware.org/isinfo.php)
;
;  Build:
;    - Open Inno Setup Compiler -> File > Open -> select this file -> Build > Compile
;    - Or CLI: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
;  Output: installer_output\PaperReader_Setup_1.1.0.exe
; ──────────────────────────────────────────────────

#define MyAppName "PaperReader"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Myprefer"
#define MyAppURL "https://github.com/Myprefer"
#define MyAppExeName "PaperReader.exe"
#define MyAppDescription "AI-powered paper reading, management and note-taking tool"
#define MyAppCopyright "Copyright © 2026 Myprefer. All rights reserved."

[Setup]
; 应用信息
AppId={{B5A3C8E2-4F7D-4A1B-9C3E-8D2F1A6B5E4C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppCopyright={#MyAppCopyright}
AppComments={#MyAppDescription}

; 安装路径
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; 输出
OutputDir=installer_output
OutputBaseFilename=PaperReader_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes

; 图标
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; 权限
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 界面
WizardStyle=modern
WizardResizable=no

; 版本
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright={#MyAppCopyright}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppDescription}

; 架构
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional options:"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "Create a Quick Launch shortcut"; GroupDescription: "Additional options:"

[Files]
; PyInstaller 输出的所有文件
Source: "dist\PaperReader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\app.ico"; Comment: "{#MyAppDescription}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\app.ico"; Tasks: desktopicon
; Quick Launch
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; Optionally launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean runtime cache (keep user data)
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function ReadGeminiApiKey(): string;
var
  Value: string;
begin
  Result := Trim(ExpandConstant('{%GEMINI_API_KEY|}'));
  if Result <> '' then
    Exit;

  if RegQueryStringValue(HKCU, 'Environment', 'GEMINI_API_KEY', Value) then
  begin
    Result := Trim(Value);
    if Result <> '' then
      Exit;
  end;

  if RegQueryStringValue(HKLM,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'GEMINI_API_KEY', Value) then
  begin
    Result := Trim(Value);
    if Result <> '' then
      Exit;
  end;

  Result := '';
end;

function InitializeSetup(): Boolean;
var
  ApiKey: string;
begin
  ApiKey := ReadGeminiApiKey();
  if ApiKey = '' then
  begin
    MsgBox(
      '检测到未配置 Gemini API 环境变量（GEMINI_API_KEY）。' + #13#10 + #13#10 +
      '请先在系统中配置好 GEMINI_API_KEY，再重新运行安装包。' + #13#10 +
      '本次安装将立即退出。',
      mbCriticalError,
      MB_OK
    );
    Result := False;
    Exit;
  end;

  Result := True;
end;

// Create data directory after install
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    DataDir := ExpandConstant('{userdocs}\PaperReader');
    if not DirExists(DataDir) then
      ForceDirectories(DataDir);
  end;
end;
