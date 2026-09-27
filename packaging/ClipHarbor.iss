#ifndef AppVersion
  #define AppVersion "0.5.0"
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

[Run]
Filename: "{app}\ClipHarbor.exe"; Description: "Open ClipHarbor"; Flags: nowait postinstall skipifsilent

; Do not delete LocalAppData\ClipHarbor on uninstall. Projects belong to the user.
