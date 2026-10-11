import sys
import os
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
try:
    import pandas as pd
    pd.set_option('future.no_silent_downcasting', True)
except Exception:
    pass
import ctypes
import pymysql  # ★ PyInstaller 빌드 패키징 누락 방지용 명시적 import
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtGui import QIcon

# 0. ★ 전역 오류 감시기 및 로깅 초기화 (파일 누락 시에도 안전하게 실행되는 무결점 Fallback)
try:
    from error_handler import init_error_handler, set_user_context
    init_error_handler()
except ImportError:
    def init_error_handler():
        pass
    def set_user_context(company_id, user_id):
        pass

# 1. 버전 정보 및 자동 업데이트 모듈 불러오기
from config import APP_VERSION
from updater import check_and_run_update

from dialogs.auth_dialogs import LoginDialog
from preview_ui import BookSTScannerApp
from PyQt6.QtCore import qInstallMessageHandler

def suppress_qt_font_warnings(msg_type, context, message):
    if "setPointSize" in message or "point size <= 0" in message.lower():
        return

qInstallMessageHandler(suppress_qt_font_warnings)


if __name__ == "__main__":
    try:
        myappid = 'optibook.ims.scanner.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    try:
        app = QApplication(sys.argv)
        if os.path.exists("app_icon.ico"):
            app.setWindowIcon(QIcon("app_icon.ico"))
        
        # 2. ★ 로그인창 뜨기 전 최신 버전 자동 체크 및 업데이트 실행
        check_and_run_update(APP_VERSION)
        
        login_dialog = LoginDialog()
        if login_dialog.exec() == QDialog.DialogCode.Accepted:
            user_info = login_dialog.user_info
            set_user_context(user_info.get('company_id', 'UNKNOWN'), user_info.get('user_id', 'UNKNOWN'))
            
            window = BookSTScannerApp()
            window.init_user_session(user_info)
            window.showMaximized()  # ★ 전체화면 기준으로 켜지도록 설정
            sys.exit(app.exec())
        else:
            sys.exit(0)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            with open("optibook_error.log", "a", encoding="utf-8") as f:
                f.write(f"\n[STARTUP CRASH] {e}\n{tb}\n")
        except Exception:
            pass
        print(f"치명적 오류 발생:\n{tb}", file=sys.stderr)
        try:
            QMessageBox.critical(None, "프로그램 실행 오류", f"프로그램 실행 중 오류가 발생했습니다:\n\n{e}\n\n상세 내역은 optibook_error.log 파일을 확인해 주세요.")
        except Exception:
            pass
        sys.exit(1)