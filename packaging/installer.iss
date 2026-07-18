; FlipRadar — installer Inno Setup 6, per-user (fara UAC), pentru distributie (PKG-3c).
; Construit de packaging/build_exe.py:  ISCC /DAppVersion=<ver> installer.iss  (cwd=packaging/).
; Sursa = dist\FlipRadar\ (onedir-ul PyInstaller validat la PKG-3b).

#ifndef AppVersion
  #define AppVersion "0.0.0"     ; fallback daca nu vine prin /DAppVersion de la build script
#endif
#define SourceDir "dist\FlipRadar"

[Setup]
; AppId = identitatea aplicatiei pentru upgrade-uri + dezinstalare. GENERAT O DATA
; si FIXAT — NU se schimba NICIODATA (altfel upgrade-urile ar aparea ca alt program).
AppId={{601EA1D3-11A3-494B-B8B0-A66A355F485F}
AppName=FlipRadar
AppVersion={#AppVersion}
AppPublisher=FlipRadar
; Instalare per-user in LOCALAPPDATA -> ZERO UAC (public deschis, fara drepturi de admin).
DefaultDirName={localappdata}\Programs\FlipRadar
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputBaseFilename=FlipRadar-Setup-{#AppVersion}
OutputDir=dist
; Icon-ul real (din favicon-ul aplicatiei, generat de build_exe.py).
SetupIconFile=flipradar.ico
UninstallDisplayIcon={app}\FlipRadar.exe
; La upgrade cu aplicatia pornita, o inchidem automat (evita eroarea "fisier in uz").
CloseApplications=yes
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
; Romanian.isl NU e livrat cu Inno Setup 6 (traducere neoficiala) -> fallback pe engleza
; (Default.isl). App-ul in sine ramane integral in romana. Vezi raportul PKG-3c.
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Iconita pe desktop — bifata implicit (publicul tinta o vrea).
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Tot onedir-ul (FlipRadar.exe + _internal\ + frontend_out\), recursiv.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; Shortcut in Start Menu + pe desktop (ultimul pe task).
Name: "{autoprograms}\FlipRadar"; Filename: "{app}\FlipRadar.exe"
Name: "{autodesktop}\FlipRadar"; Filename: "{app}\FlipRadar.exe"; Tasks: desktopicon

[Run]
; Porneste aplicatia la finalul instalarii (bifat, fara sa blocheze wizard-ul).
Filename: "{app}\FlipRadar.exe"; Description: "Porneste FlipRadar"; Flags: nowait postinstall skipifsilent
