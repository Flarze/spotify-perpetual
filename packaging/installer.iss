; Inno Setup script for Spotify Perpetual.
;
; Produces dist\SpotifyPerpetualSetup.exe — a standard double-click installer:
; the user runs it, clicks through, and gets Start Menu / Desktop shortcuts plus
; an optional "start at login" entry. No admin rights, no PowerShell, no typed
; commands. First launch opens the graphical setup form (gui_setup.py).
;
; Build the exe first (packaging\build_windows.ps1 or PyInstaller), then compile
; this with the Inno Setup compiler (ISCC.exe). build_windows.ps1 does both when
; Inno Setup is installed.

#define AppName "Spotify Perpetual"
#define AppVersion "1.0.0"
#define AppPublisher "Flarze"
#define AppExeName "Spotify Perpetual.exe"
#define AppUrl "https://github.com/Flarze/spotify-perpetual"

[Setup]
AppId={{edcaaa42-8aeb-4adb-a650-942c824cf3b1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}
; Per-user install: no admin prompt. Lives in the user's local Programs folder,
; which is writable, so the app keeps its config/cache/logs beside the exe.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\dist
OutputBaseFilename=SpotifyPerpetualSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=
; Refuse to run on non-Windows / very old Windows.
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startupicon"; Description: "Start {#AppName} automatically when I log in"; GroupDescription: "Startup:"

[Files]
; One-dir PyInstaller build: ship the whole folder (exe + dependencies).
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut (always).
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
; Optional Desktop shortcut.
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
; Optional autostart: a Startup-folder shortcut launching the exe with no args
; (open-and-run -> tray), minimized. Matches what `idle-player install` creates.
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Run]
; Offer to launch right after install; first run shows the setup form.
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The token cache and config hold secrets; remove them on uninstall so nothing
; sensitive is left behind in the install folder.
Type: files; Name: "{app}\.cache"
Type: files; Name: "{app}\config.yaml"
Type: filesandordirs; Name: "{app}\logs"
