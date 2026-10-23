#ifndef AppVersion
  #define AppVersion "0.7.0"
#endif
[Setup]
AppId={{C4D10547-F495-4B40-A8C8-98B31505B3D1}
AppName=ClipHarbor
AppVersion={#AppVersion}
AppPublisher=ClipHarbor
DefaultDirName={localappdata}\Programs\ClipHarbor
DefaultGroupName=ClipHarbor
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=ClipHarbor-Setup-{#AppVersion}-win-x64
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ClipHarbor.exe
CloseApplications=yes
RestartApplications=no
InfoAfterFile=FAMILY-README.txt

[Files]
Source: "..\dist\ClipHarbor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: checkedonce

[Icons]
Name: "{group}\ClipHarbor"; Filename: "{app}\ClipHarbor.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\ClipHarbor"; Filename: "{app}\ClipHarbor.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\Uninstall ClipHarbor"; Filename: "{uninstallexe}"
Name: "{group}\Set up browser extension"; Filename: "{app}\browser-extension\setup.html"

[Registry]
; Register a dedicated stdio bridge. Do not force-install an extension or grant
; it access to any websites; loading the extension is the user's browser action.
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.clipharbor.downloader"; ValueType: string; ValueName: ""; ValueData: "{app}\clipharbor-native-host.json"
Root: HKCU; Subkey: "Software\Microsoft\Edge\NativeMessagingHosts\com.clipharbor.downloader"; ValueType: string; ValueName: ""; ValueData: "{app}\clipharbor-native-host.json"

[Run]
Filename: "{app}\ClipHarbor.exe"; Description: "Open ClipHarbor"; Flags: nowait postinstall skipifsilent

; Do not delete LocalAppData\ClipHarbor on uninstall. Projects belong to the user.

[Code]
procedure RemoveOwnedBridge(const BrowserKey: String);
var
  ManifestPath: String;
begin
  if RegQueryStringValue(HKCU, BrowserKey, '', ManifestPath) then
    if CompareText(ManifestPath, ExpandConstant('{app}\clipharbor-native-host.json')) = 0 then
      RegDeleteKeyIncludingSubkeys(HKCU, BrowserKey);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RemoveOwnedBridge('Software\Google\Chrome\NativeMessagingHosts\com.clipharbor.downloader');
    RemoveOwnedBridge('Software\Microsoft\Edge\NativeMessagingHosts\com.clipharbor.downloader');
  end;
end;
