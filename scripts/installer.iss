; ReelForge's Windows installer (Inno Setup 6). GitHub Actions builds it on every version tag:
;   python scripts/package.py --stage-only
;   ISCC.exe /DMyAppVersion=1.0.0 scripts\installer.iss      -> dist\ReelForge-1.0.0-Windows-Setup.exe
; It copies ReelForge into your user folder (no admin rights needed), adds Start-menu and desktop shortcuts and the
; reelforge command, then runs setup.bat (the first-run screens). Uninstalling removes ReelForge, the tools setup
; downloaded, the hourly stats job and the reelforge command, but keeps your channel (my-studio, episodes,
; completed videos) and the dashboard's data. ReelForge's Updates tab runs a newer copy of this installer silently.
; Once code signing is set up (.github/SIGNING.md), the workflow also passes /DSign and /Sreelforge=<sign command>.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.2"
#endif
#define MyAppName "ReelForge"
#define Stage "..\dist\stage\ReelForge"

[Setup]
AppId={{39D29FF3-A243-4140-8CD2-E69CC877A496}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=ReelForge
AppPublisherURL=https://github.com/dan2756/ReelForge
AppSupportURL=https://github.com/dan2756/ReelForge/issues
AppUpdatesURL=https://github.com/dan2756/ReelForge/releases
AppCopyright=Copyright (c) 2026 the ReelForge authors
; The installer's Properties > Details tab (company, description, product name and copyright come from the App* lines)
VersionInfoVersion={#MyAppVersion}
VersionInfoOriginalFileName=ReelForge-{#MyAppVersion}-Windows-Setup.exe
#ifdef Sign
; Signs the installer, the setup.tmp it unpacks while running and the uninstaller with the workflow's sign command
SignTool=reelforge
#endif
DefaultDirName={%USERPROFILE}\ReelForge
DisableProgramGroupPage=yes
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
ChangesEnvironment=yes
OutputDir=..\dist
OutputBaseFilename=ReelForge-{#MyAppVersion}-Windows-Setup
SetupIconFile=..\assets\icon\reelforge.ico
UninstallDisplayIcon={app}\assets\icon\reelforge.ico
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DirExistsWarning=no

[Messages]
SelectDirDesc=ReelForge keeps your channel, your videos and its tools in this folder. Pick a place with plenty of free space and a short path.

[Tasks]
Name: "desktopicon"; Description: "Put ReelForge on the desktop"
Name: "addtopath"; Description: "Add the reelforge command (type reelforge in any terminal to open ReelForge)"

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}\ReelForge"; Filename: "{app}\ReelForge.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon\reelforge.ico"
Name: "{autoprograms}\{#MyAppName}\ReelForge setup"; Filename: "{app}\setup.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon\reelforge.ico"
Name: "{autoprograms}\{#MyAppName}\Change my channel answers"; Filename: "{app}\onboard.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon\reelforge.ico"
Name: "{autoprograms}\{#MyAppName}\ReelForge folder"; Filename: "{app}"
Name: "{autodesktop}\ReelForge"; Filename: "{app}\ReelForge.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon\reelforge.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}\bin"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}\bin'))

[Run]
Filename: "{app}\setup.bat"; WorkingDir: "{app}"; Description: "Set up ReelForge now (downloads Blender, ffmpeg and the sound effects, then a short interview)"; Flags: postinstall shellexec skipifsilent

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""ReelForge stats"" /F"; Flags: runhidden; RunOnceId: "RemoveStatsJob"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\tools"
Type: filesandordirs; Name: "{app}\assets\sfx\_cache"
Type: filesandordirs; Name: "{app}\assets\sfx\mixkit"
Type: files; Name: "{userdesktop}\ReelForge.lnk"

[Code]
function NeedsAddPath(Dir: string): Boolean;
var
  Paths: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths) then
    Result := True
  else
    Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') = 0;
end;

procedure RemovePath(Dir: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths) then
    exit;
  P := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then
    exit;
  if P = 1 then
    Delete(Paths, 1, Length(Dir) + 1)
  else
    Delete(Paths, P - 1, Length(Dir) + 1);
  RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemovePath(ExpandConstant('{app}\bin'));
end;
