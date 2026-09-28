import sys
import ctypes
import pymysql  # ★ PyInstaller 빌드 패키징 누락 방지용 명시적 import
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtGui import QIcon

# 1. 버전 정보 및 자동 업데이트 모듈 불러오기
APP_VERSION = "1.0.2"
from updater import check_and_run_update

from dialogs.auth_dialogs import LoginDialog
from preview_ui import BookSTScannerApp

if __name__ == "__main__":
    try:
        myappid = 'optibook.ims.scanner.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("app_icon.ico"))
    
    # 2. ★ 로그인창 뜨기 전 최신 버전 자동 체크 및 업데이트 실행
    check_and_run_update(APP_VERSION)
    
    login_dialog = LoginDialog()
    if login_dialog.exec() == QDialog.DialogCode.Accepted:
        user_info = login_dialog.user_info
        
        window = BookSTScannerApp()
        window.init_user_session(user_info)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)
