; DuckDesk installer (docs/06 step 2): per-user, no admin, pt-BR, offline.
; Build: scripts/build_installer.ps1 (passa /DMyAppVersion=<versao do pyproject>)

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppId "{{a1df7ee3-fdf8-44da-abb6-46c21fc0e71e}"
#define SourceDir "..\dist\DuckDesk"
#define IconFile "..\assets\icons\duckdesk.ico"

[Setup]
AppId={#MyAppId}
AppName=DuckDesk
AppVersion={#MyAppVersion}
AppPublisher=DuckDesk (nao oficial)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\DuckDesk
DefaultGroupName=DuckDesk
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=out
OutputBaseFilename=DuckDesk-Setup-{#MyAppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\DuckDesk.exe
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
WizardStyle=modern
DisableDirPage=auto
LicenseFile=licenca.txt

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na &Area de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
Name: "autostart"; Description: "&Iniciar com o Windows"; GroupDescription: "Inicializacao:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DuckDesk"; Filename: "{app}\DuckDesk.exe"; IconFilename: "{app}\assets\icons\duckdesk.ico"
Name: "{group}\Desinstalar DuckDesk"; Filename: "{uninstallexe}"
Name: "{autodesktop}\DuckDesk"; Filename: "{app}\DuckDesk.exe"; Tasks: desktopicon; IconFilename: "{app}\assets\icons\duckdesk.ico"

[Registry]
; mesma chave que o app usa em 'Iniciar com o Windows' (05 section 7)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "DuckDesk"; ValueData: """{app}\DuckDesk.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\DuckDesk.exe"; Description: "Abrir o DuckDesk agora"; \
    Flags: nowait postinstall skipifsilent

[Code]
// docs/06: desinstalador remove tudo mas PERGUNTA antes de apagar as configuracoes
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  SettingsDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    SettingsDir := ExpandConstant('{userappdata}\DuckDesk');
    if DirExists(SettingsDir) then
    begin
      if MsgBox('Deseja tambem apagar as configuracoes do DuckDesk em ' + SettingsDir + ' ?',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(SettingsDir, True, True, True);
    end;
  end;
end;
