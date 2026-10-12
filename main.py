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
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import qInstallMessageHandler, Qt

# 0. ★ 전역 오류 감시기 및 로깅 초기화
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

def suppress_qt_font_warnings(msg_type, context, message):
    if "setPointSize" in message or "point size <= 0" in message.lower():
        return

qInstallMessageHandler(suppress_qt_font_warnings)

def global_excepthook(exc_type, exc_value, exc_traceback):
    import traceback
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        with open("optibook_error.log", "a", encoding="utf-8") as f:
            f.write("\n[" + str(datetime.now()) + "] [UNHANDLED EXCEPTION]\n" + tb + "\n")
    except Exception:
        pass
    print("오류 발생:\n" + tb, file=sys.stderr)
    try:
        QMessageBox.critical(None, "프로그램 오류 안내", f"작업 중 오류가 발생했습니다:\n\n{exc_value}\n\n상세 내역은 optibook_error.log 파일을 확인해 주세요.")
    except Exception:
        pass

sys.excepthook = global_excepthook


if __name__ == "__main__":
    try:
        myappid = 'optibook.ims.scanner.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    try:
        app = QApplication(sys.argv)
        app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        if os.path.exists("app_icon.ico"):
            app.setWindowIcon(QIcon("app_icon.ico"))

        # ★ [전역 드래그바/드롭다운 불투명 화이트 배경 및 고시인성 스타일 강제 적용]
        app.setStyleSheet("""
            QComboBox, QFontComboBox {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #94A3B8;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QComboBox:hover, QFontComboBox:hover {
                border: 1px solid #007ACC;
            }
            QComboBox::drop-down, QFontComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid #CBD5E1;
                background-color: #F1F5F9;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {
                background-color: #FFFFFF;
                color: #0F172A;
                selection-background-color: #007ACC;
                selection-color: #FFFFFF;
                border: 1px solid #64748B;
                border-radius: 4px;
                outline: 0px;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item, QFontComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 4px 8px;
                color: #0F172A;
                background-color: #FFFFFF;
            }
            QComboBox QAbstractItemView::item:hover, QFontComboBox QAbstractItemView::item:hover {
                background-color: #E0F2FE;
                color: #0369A1;
            }
            QComboBox QAbstractItemView::item:selected, QFontComboBox QAbstractItemView::item:selected {
                background-color: #007ACC;
                color: #FFFFFF;
            }
            QSlider::groove:horizontal {
                height: 8px;
                background: #CBD5E1;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #007ACC;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #007ACC;
                border: 2px solid #FFFFFF;
                width: 18px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #005999;
            }
            QScrollBar:vertical {
                border: none;
                background: #F1F5F9;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #94A3B8;
                min-height: 24px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #64748B;
            }
            QScrollBar:horizontal {
                border: none;
                background: #F1F5F9;
                height: 12px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #94A3B8;
                min-width: 24px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #64748B;
            }
        """)
        
        # 2. ★ 로그인창 뜨기 전 최신 버전 자동 체크 및 업데이트 실행
        check_and_run_update(APP_VERSION)
        
        login_dialog = LoginDialog()
        if login_dialog.exec() == QDialog.DialogCode.Accepted:
            user_info = login_dialog.user_info
            set_user_context(user_info.get('company_id', 'UNKNOWN'), user_info.get('user_id', 'UNKNOWN'))
            
            window = BookSTScannerApp()
            window.init_user_session(user_info)
            
            # ★ [모든 PC 해상도/화면 크기 완벽 대응] 작업표시줄 제외 가용 영역에 자동 맞춤 및 전체화면 실행
            screen = app.primaryScreen()
            if screen:
                window.setGeometry(screen.availableGeometry())
            window.setWindowState(Qt.WindowState.WindowMaximized)
            window.showMaximized()
            sys.exit(app.exec())
        else:
            sys.exit(0)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            with open("optibook_error.log", "a", encoding="utf-8") as f:
                f.write("\n[STARTUP CRASH] " + str(e) + "\n" + tb + "\n")
        except Exception:
            pass
        print("치명적 오류 발생:\n" + tb, file=sys.stderr)
        try:
            QMessageBox.critical(None, "프로그램 실행 오류", f"프로그램 실행 중 오류가 발생했습니다:\n\n{e}\n\n상세 내역은 optibook_error.log 파일을 확인해 주세요.")
        except Exception:
            pass
        sys.exit(1)
