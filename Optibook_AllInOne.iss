; =====================================================================
; Optibook-IMS 올인원 마스터 설치 패키지 스크립트
; =====================================================================

#define MyAppName "Optibook-IMS"
#define MyAppFullTitle "Optibook-IMS 도서검수 및 라벨 출력 시스템"
#define MyAppVersion "1.0.2"
#define MyAppPublisher "Optibook"
#define MyAppExeName "Optibook-IMS.exe"
#define MyAppIcon "app_icon.ico"

[Setup]
AppId={{8F5B1A2C-901E-4B2A-B981-D9F0E1D2C3B4}}
AppName={#MyAppFullTitle}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; ★ Program Files 대신 C:\Optibook-IMS 에 직접 설치하도록 변경 (권한 문제 근본 차단)
DefaultDirName=C:\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=.\Installer_Output
OutputBaseFilename=Optibook-IMS_Setup_v{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; 관리자 권한 승인 강제
PrivilegesRequired=admin

; 실행 중인 프로그램 자동 종료 안내
CloseApplications=yes
CloseApplicationsFilter=*.exe

; ★ 설치 폴더에 일반 사용자 파일 쓰기/수정 권한 부여
[Dirs]
Name: "{app}"; Permissions: users-modify

[Files]
; 1. 빌드된 dist 폴더 내 모든 파일 포함 (단, 로그인/앱 상태 파일은 실수로 묶이지 않도록 제외)
Source: "dist\Optibook-IMS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "login_state.json, app_state.json, offline_auth.json"

; 2. MS Visual C++ Runtime 무소음 설치 파일
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

; 3. 기본 데이터/설정 파일이 존재하는 경우만 포함 (덮어쓰기 방지)
Source: "bookst_db.csv"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: "graphic_template.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist

[Icons]
; 시작 메뉴 바로가기
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcon}"
Name: "{group}\{#MyAppName} 삭제"; Filename: "{uninstallexe}"

; 바탕화면에 바로가기 100% 자동 생성
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcon}"

[Run]
; C++ 런타임 백그라운드 무소음 설치
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/q /norestart"; StatusMsg: "시스템 필수 런타임(Visual C++ Runtime) 자동 검증 및 설치 중..."; Flags: waituntilterminated

; 설치 완료 후 즉시 실행 체크박스
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 시스템 지금 실행하기"; Flags: postinstall nowait skipifsilent

[Code]
// 삭제(Uninstall) 시 로컬 DB 보존 여부 질의
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