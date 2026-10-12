; =====================================================================
; Optibook-IMS ?ъ씤??留덉뒪???ㅼ튂 ?⑦궎吏 ?ㅽ겕由쏀듃
; =====================================================================

#define MyAppName "Optibook-IMS"
#define MyAppFullTitle "Optibook-IMS ?꾩꽌寃??諛??쇰꺼 異쒕젰 ?쒖뒪??
#define MyAppVersion "1.0.4"
#define MyAppPublisher "Optibook"
#define MyAppExeName "Optibook-IMS.exe"
#define MyAppIcon "app_icon.ico"

[Setup]
AppId={{8F5B1A2C-901E-4B2A-B981-D9F0E1D2C3B4}}
AppName={#MyAppFullTitle}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; ??Program Files ???C:\Optibook-IMS ??吏곸젒 ?ㅼ튂?섎룄濡?蹂寃?(沅뚰븳 臾몄젣 洹쇰낯 李⑤떒)
DefaultDirName=C:\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=.\Installer_Output
OutputBaseFilename=Optibook-IMS_Setup_v{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; 愿由ъ옄 沅뚰븳 ?뱀씤 媛뺤젣
PrivilegesRequired=admin

; ?ㅽ뻾 以묒씤 ?꾨줈洹몃옩 ?먮룞 醫낅즺 ?덈궡
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}

; ???ㅼ튂 ?대뜑???쇰컲 ?ъ슜???뚯씪 ?곌린/?섏젙 沅뚰븳 遺??[Dirs]
Name: "{app}"; Permissions: users-modify

[Files]
; 1. 鍮뚮뱶??dist ?대뜑 ??紐⑤뱺 ?뚯씪 ?ы븿 (?? 濡쒓렇?????곹깭 ?뚯씪? ?ㅼ닔濡?臾띠씠吏 ?딅룄濡??쒖쇅)
Source: "dist\Optibook-IMS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "login_state.json, app_state.json, offline_auth.json"

; 2. MS Visual C++ Runtime 臾댁냼???ㅼ튂 ?뚯씪
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

; 3. 湲곕낯 ?곗씠???ㅼ젙 ?뚯씪??議댁옱?섎뒗 寃쎌슦留??ы븿 (??뼱?곌린 諛⑹?)
Source: "bookst_db.csv"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: "graphic_template.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist

; 4. env?뚯씪 留뚮뱾湲?Source: ".env"; DestDir: "{app}"; Flags: ignoreversion

; 5. 鍮낆넄濡?BIXOLON) ?덈룄???쒕씪?대쾭 ?ㅼ튂 ?뚯씪 ?ы븿
Source: "drivers\Software_POS_Windows_Driver_V5.2.3.exe"; DestDir: "{app}\drivers"; Flags: ignoreversion skipifsourcedoesntexist
Source: "Software_POS_Windows_Driver_V5.2.3.exe"; DestDir: "{app}\drivers"; Flags: ignoreversion skipifsourcedoesntexist

; 6. ???꾩슜 ?꾩씠肄??뚯씪 蹂듭궗 (諛붾줈媛湲??섏? ?꾩씠肄?諛⑹?)
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; ?쒖옉 硫붾돱 諛붾줈媛湲?Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0
Name: "{group}\{#MyAppName} ??젣"; Filename: "{uninstallexe}"

; 諛뷀깢?붾㈃??諛붾줈媛湲?100% ?먮룞 ?앹꽦 (EXE ?댁옣 ?꾩씠肄?吏곸젒 異붿텧)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0

[Run]
; C++ ?고???諛깃렇?쇱슫??臾댁냼???ㅼ튂
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/q /norestart"; StatusMsg: "?쒖뒪???꾩닔 ?고???Visual C++ Runtime) ?먮룞 寃利?諛??ㅼ튂 以?.."; Flags: waituntilterminated

; ?ㅼ튂 ?꾨즺 ??利됱떆 ?ㅽ뻾 泥댄겕諛뺤뒪
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} ?쒖뒪??吏湲??ㅽ뻾?섍린"; Flags: postinstall nowait

; 鍮낆넄濡?BIXOLON) ?꾨┛???쒕씪?대쾭 ?④퍡 ?ㅼ튂 (?ъ슜???좏깮 ?듭뀡)
Filename: "{app}\drivers\Software_POS_Windows_Driver_V5.2.3.exe"; Description: "鍮낆넄濡?BIXOLON) ?쇰꺼/?곸닔利??꾨┛???쒕씪?대쾭 吏湲??ㅼ튂?섍린"; Flags: postinstall skipifsilent nowait skipifdoesntexist

[Code]
// ??젣(Uninstall) ??濡쒖뺄 DB 蹂댁〈 ?щ? 吏덉쓽
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  mResult: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    mResult := MsgBox('?꾨줈洹몃옩 ??젣 ??濡쒖뺄 ?곗씠???꾩꽌 DB 諛??ㅼ젙媛????④퍡 ??젣?섏떆寃좎뒿?덇퉴?' + #13#10 + #13#10 +
                      '[?? : 紐⑤뱺 ?곗씠???꾩쟾????젣' + #13#10 +
                      '[?꾨땲?? : ?곗씠?곕뒗 ?④꺼?먭퀬 ?꾨줈洹몃옩留???젣 (?ъ꽕移???蹂듦뎄 媛??', 
                      mbConfirmation, MB_YESNO);
  end;
end;
