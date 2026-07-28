; Compile with Inno Setup 6. The build script supplies MyAppVersion.
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{B6F465F0-75FB-4497-BE12-CB0A4F78FD6F}
AppName=题搭子
AppVersion={#MyAppVersion}
AppPublisher=题搭子
DefaultDirName={autopf}\题搭子
DefaultGroupName=题搭子
OutputDir=..\dist
OutputBaseFilename=题搭子-Setup-{#MyAppVersion}
SetupIconFile=..\assets\tidazi.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\题搭子.exe

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Files]
Source: "..\dist\题搭子\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\题搭子"; Filename: "{app}\题搭子.exe"
Name: "{autodesktop}\题搭子"; Filename: "{app}\题搭子.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\题搭子.exe"; Description: "启动题搭子"; Flags: nowait postinstall skipifsilent
