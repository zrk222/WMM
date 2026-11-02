#ifndef MyAppId
  #define MyAppId "WizeMarketingMachine"
#endif
#ifndef MyAppName
  #define MyAppName "Wize Marketing Machine"
#endif
#ifndef BundleDir
  #define BundleDir "..\..\dist\desktop\WMM"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\installer"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion=1.0.0
AppPublisher=Wize Marketing Machine
DefaultDirName={localappdata}\Programs\Wize Marketing Machine
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=WMM-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Open WMM.vbs"""; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Open WMM.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\Open WMM.vbs"""; WorkingDir: "{app}"; Description: "Open Wize Marketing Machine"; Flags: postinstall nowait skipifsilent unchecked

[Messages]
WelcomeLabel2=Close the WMM controller and any running WMM worker before installing or upgrading. Your separate workspace is retained.
