#define MyAppName "WSTPServer Manager"
#define MyAppPublisher "WSTPServer Manager contributors"
#define MyAppExeName "WSTPServerManager.exe"
#ifndef AppVersion
#define AppVersion "0.1.0"
#endif
#ifndef DistDir
#define DistDir "..\..\..\dist\WSTPServerManager"
#endif

[Setup]
AppId={{09F14A64-978A-4C56-BDA8-487974D38E26}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\WSTPServerManager
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\..\dist\installers
OutputBaseFilename=WSTPServerManager-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "WSTPServer Manager"; ValueData: """{app}\{#MyAppExeName}"" --start-hidden"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--start-hidden"; Description: "Start {#MyAppName} in the system tray"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--install-service', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      RaiseException('Could not run WSTPServer service installation.');
    end;
    if ResultCode <> 0 then
    begin
      RaiseException('WSTPServer service installation failed. Install Wolfram locally, then run WSTPServer Manager as this user and choose Install Service.');
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--uninstall-service', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
