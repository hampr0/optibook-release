; =====================================================================
; Optibook-IMS 올인원 마스터 설치 패키지 스크립트
; =====================================================================

#define MyAppName "Optibook-IMS"
#define MyAppFullTitle "Optibook-IMS 도서검수 및 라벨 출력 시스템"
#define MyAppVersion "1.0.4"
#define MyAppPublisher "Optibook"
#define MyAppExeName "Optibook-IMS.exe"
#define MyAppIcon "app_icon.ico"

[Setup]
AppId={{8F5B1A2C-901E-4B2A-B981-D9F0E1D2C3B4}}
AppName={#MyAppFullTitle}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=.\Installer_Output
OutputBaseFilename=Optibook-IMS_Setup_v{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}

[Dirs]
Name: "{app}"; Permissions: users-modify

[Files]
Source: "dist\Optibook-IMS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "login_state.json, app_state.json, offline_auth.json"
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "bookst_db.csv"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: "graphic_template.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: ".env"; DestDir: "{app}"; Flags: ignoreversion
Source: "drivers\Software_POS_Windows_Driver_V5.2.3.exe"; DestDir: "{app}\drivers"; Flags: ignoreversion skipifsourcedoesntexist
Source: "Software_POS_Windows_Driver_V5.2.3.exe"; DestDir: "{app}\drivers"; Flags: ignoreversion skipifsourcedoesntexist
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0
Name: "{group}\{#MyAppName} 삭제"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/q /norestart"; StatusMsg: "시스템 필수 런타임(Visual C++ Runtime) 자동 검증 및 설치 중..."; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 시스템 지금 실행하기"; Flags: postinstall nowait
Filename: "{app}\drivers\Software_POS_Windows_Driver_V5.2.3.exe"; Description: "빅솔론(BIXOLON) 라벨/영수증 프린터 드라이버 지금 설치하기"; Flags: postinstall skipifsilent nowait skipifdoesntexist

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  mResult: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    mResult := MsgBox('프로그램 삭제 시 로컬 데이터(도서 DB 및 설정값)도 함께 삭제하시겠습니까?' + #13#10 + #13#10 +
                      '[예] : 모든 데이터 완전히 삭제' + #13#10 +
                      '[아니오] : 데이터는 남겨두고 프로그램만 삭제 (재설치 시 복구 가능)', 
                      mbConfirmation, MB_YESNO);
  end;
end;