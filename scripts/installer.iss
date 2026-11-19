; ListenScope Inno Setup 6 Script (Windows 10/11 x64 Turnkey Installer)
; Unverified on Windows host until compiled via ISCC.exe on Windows 11.
;
; Highlights:
;   - Non-admin default (`PrivilegesRequired=lowest`) so normal users install seamlessly.
;   - Automatically defaults to non-C: fixed drive if present (D:\ListenScope / E:\ListenScope),
;     keeping app outputs, exports, and short-path `m\` MIDI runtime off C:\ and well below MAX_PATH.
;   - Bundles `dist\ListenScopeCore\*` (including optional staged `runtime\ai`, short `m\`, `tools\ffmpeg`).
;   - Preserves user `exports\` on uninstall / upgrade.

#define MyAppName "ListenScope"
#ifndef MyAppVersion
#define MyAppVersion "0.2.3"
#endif
#define MyAppPublisher "ListenScope Project"
#define MyAppExeName "ListenScope.exe"
#define MySourceDir "..\dist\ListenScopeCore"

[Setup]
AppId={{D92B6E14-9F1A-4D7E-A78A-3F6F49B8C201}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={code:GetDefaultInstallDir}
DisableDirPage=no
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=ListenScope-Setup-Windows-x64
SetupIconFile=..\ui\assets\listenscope.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/normal
SolidCompression=no
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式 (Create a desktop shortcut)"; GroupDescription: "附加选项:"

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\exports"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 ListenScope"; Flags: nowait postinstall skipifsilent

[Code]
function GetDefaultInstallDir(Param: string): string;
begin
  if DirExists('D:\') then
    Result := 'D:\ListenScope'
  else if DirExists('E:\') then
    Result := 'E:\ListenScope'
  else
    Result := ExpandConstant('{userpf}\ListenScope');
end;
