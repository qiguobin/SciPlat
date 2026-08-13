; SciPlat 安装包脚本（Inno Setup 6）
; 编译：ISCC.exe scripts\sciplat.iss
; 产物：desktop\release\SciPlatSetup-0.4.0.exe
#define MyAppName "SciPlat"
#define MyAppVersion "0.7.1"
#define MyAppExeName "SciPlat.exe"

[Setup]
AppId={{8E6F2A11-9B3C-4D5E-A1F2-0F1E2D3C4B5A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=SciPlat
DefaultDirName={autopf}\SciPlat
DefaultGroupName=SciPlat
AllowNoIcons=yes
OutputDir=..\desktop\release
OutputBaseFilename=SciPlatSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\desktop\build\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; 升级时自行关闭运行中的 SciPlat.exe（消除静默安装时文件锁导致的安装中止）
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "..\backend\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 无 skipifsilent：静默升级（/SILENT）完成后也自动启动新版
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait

[UninstallDelete]
Type: dirifempty; Name: "{app}"
