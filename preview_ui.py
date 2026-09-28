import sys
import json
import os
import traceback
import urllib.request
import subprocess
import pandas as pd
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QSlider, QFormLayout, QGroupBox, QPushButton,
                             QScrollArea, QSpinBox, QFontComboBox, QMessageBox,
                             QTableWidget, QTableWidgetItem, QTabWidget, QLineEdit,
                             QHeaderView, QComboBox, QDialog, QDateEdit, QTextEdit,
                             QCheckBox, QCompleter)
from PyQt6.QtCore import Qt, QDate, QSizeF, QStringListModel, QTimer
from PyQt6.QtGui import (QFont, QPainter, QColor, QPageSize, QPixmap, QPen, 
                         QImage, QTransform, QFontMetrics, QIcon)
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo

from config import (CURRENT_APP_VERSION, TEMPLATE_FILE, DB_FILE, 
                    APP_STATE_FILE, DB_NAME)
from db import get_db_connection
from utils import force_korean_ime, play_beep_error, play_beep_success
from dialogs.admin_dialogs import UserApprovalDialog, ErrorLogDialog
from dialogs.data_dialogs import JobListDialog, BookEditDialog

class BookSTScannerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.df = pd.DataFrame()
        self.selected_jobs = set()
        self.known_clients = set()
        self.recent_scans = []
        self.is_online = False
        self.is_saving = False
        self.current_user = None
        self.target_printer_name = "BIXOLON SRP-350III"
        self.short_scan_count = 0  # ★ 짧은 바코드 연속 감지 카운터
        self.store_mode = False    # ★ 매장 입고 모드 활성화 여부
        self.store_vendor = "북센" # ★ 매장 입고 기본 거래처

        self.init_ui()

    def ensure_barcode_focus(self):
        """[스마트 포커스] 2. 검수 탭에 있고, 검색창에 포커스가 없을 때만 바코드 입력창으로 포커스 복원"""
        if self.tabs.currentIndex() == 1:
            if hasattr(self, 'line_search') and not self.line_search.hasFocus():
                self.line_barcode.setFocus()

    def init_user_session(self, user_info):
        self.current_user = user_info
        
        user_disp = f"{self.current_user['user_name']} [{self.current_user['company_id']}] 로그인됨"
        self.lbl_user_info.setText(user_disp)

        # ★ [실시간 DB 연동 매장 입고 모드 권한 확인]
        has_store_perm = False
        if self.current_user.get('role') == 'MASTER':
            has_store_perm = True
        else:
            # 중앙 DB app_settings 테이블에서 허용 목록 실시간 확인
            try:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT setting_val FROM app_settings WHERE setting_key='store_allowed_companies'")
                    s_row = cursor.fetchone()
                    conn.close()
                    if s_row and s_row['setting_val']:
                        allowed_list = [c.strip() for c in s_row['setting_val'].split(',') if c.strip()]
                        if self.current_user.get('company_id') in allowed_list:
                            has_store_perm = True
            except Exception:
                has_store_perm = (self.current_user.get('company_id') == 'COMP_A')

        if hasattr(self, 'mode_bar_widget'):
            if has_store_perm:
                self.mode_bar_widget.show()
            else:
                # 일반 회원사는 모드 전환 바를 완전히 숨겨 기존 납품 검수 화면만 유지
                self.mode_bar_widget.hide()
                if hasattr(self, 'store_vendor_group'):
                    self.store_vendor_group.hide()
                self.set_inspect_mode(False)
        
        if self.current_user['role'] == 'MASTER':
            self.combo_master_company = QComboBox()
            self.combo_master_company.setStyleSheet("font-size: 13px; padding: 4px; font-weight: bold;")
            self.combo_master_company.addItem("전체 회원사 데이터 보기", "ALL")
            self.load_company_list_to_combo()
            self.combo_master_company.currentIndexChanged.connect(self.on_company_filter_changed)
            self.status_bar_layout.insertWidget(2, self.combo_master_company)
            
            btn_approval = QPushButton("회원 승인 관리")
            btn_approval.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
            btn_approval.clicked.connect(lambda: UserApprovalDialog(self).exec())
            self.status_bar_layout.insertWidget(3, btn_approval)
            
            btn_error_logs = QPushButton("원격 오류 로그")
            btn_error_logs.setStyleSheet("background-color: #C62828; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
            btn_error_logs.clicked.connect(lambda: ErrorLogDialog(self).exec())
            self.status_bar_layout.insertWidget(4, btn_error_logs)

            # ★ [신규] 관리자 전용 실시간 클라우드 DB 용량 확인 버튼
            btn_db_storage = QPushButton("📊 DB 용량 모니터링")
            btn_db_storage.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
            btn_db_storage.clicked.connect(self.show_db_storage_dialog)
            self.status_bar_layout.insertWidget(5, btn_db_storage)

            # ★ [신규] 총괄관리자 직관적 매장 기능 권한 토글 버튼
            btn_store_perm = QPushButton("🏪 매장권한 설정")
            btn_store_perm.setStyleSheet("background-color: #E65100; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
            btn_store_perm.clicked.connect(lambda: StorePermissionDialog(self).exec())
            self.status_bar_layout.insertWidget(6, btn_store_perm)
            
            self.log_group.show()
        else:
            self.log_group.hide()

        self.check_for_auto_updates()
        self.load_database() 
        self.load_app_state()
        self.refresh_all_tables()

    def check_for_auto_updates(self):
        try:
            conn = get_db_connection()
            if not conn: return
            cursor = conn.cursor()
            cursor.execute("SELECT version, download_url, release_notes FROM app_versions ORDER BY id DESC LIMIT 1")
            latest_version_row = cursor.fetchone()
            conn.close()
            
            if latest_version_row:
                latest_ver = str(latest_version_row['version']).strip()
                if latest_ver > CURRENT_APP_VERSION:
                    notes = str(latest_version_row.get('release_notes', ''))
                    download_url = str(latest_version_row.get('download_url', '')).strip()
                    
                    msg = f"새로운 프로그램 업데이트가 발견되었습니다!\n\n현재 버전: v{CURRENT_APP_VERSION}\n최신 버전: v{latest_ver}\n\n[업데이트 내용]\n{notes}\n\n지금 업데이트를 진행하시겠습니까?"
                    reply = QMessageBox.question(self, "원격 자동 업데이트 안내", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    
                    if reply == QMessageBox.StandardButton.Yes and download_url:
                        self.perform_auto_update(download_url)
        except Exception as e:
            self.log(f"업데이트 확인 중 오류: {e}", is_error=True)

    def perform_auto_update(self, download_url):
        try:
            current_exe = sys.executable
            exe_dir = os.path.dirname(current_exe)
            setup_installer = os.path.join(exe_dir, "Optibook_Setup_Update.exe")
            
            QMessageBox.information(self, "업데이트 다운로드", "최신 버전 다운로드를 시작합니다.\n다운로드 완료 후 자동으로 설치 및 재실행됩니다.")
            urllib.request.urlretrieve(download_url, setup_installer)
            
            bat_path = os.path.join(exe_dir, "updater.bat")
            bat_script = f"""@echo off
timeout /t 2 /nobreak > NUL
"{setup_installer}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
start "" "{current_exe}"
del "{setup_installer}"
del "%~f0"
"""
            with open(bat_path, "w", encoding="cp949") as f:
                f.write(bat_script)
                
            subprocess.Popen([bat_path], shell=True)
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(self, "업데이트 실패", f"자동 업데이트 처리 중 오류 발생:\n{e}")

    def show_db_storage_dialog(self):
        """[관리자 전용] TiDB Cloud 스토리지 사용량 및 잔여 용량 실시간 확인 다이얼로그"""
        conn = get_db_connection()
        if not conn:
            QMessageBox.critical(self, "연결 실패", "중앙 DB 서버에 연결할 수 없습니다.")
            return

        try:
            cursor = conn.cursor()
            sql = """
                SELECT 
                    table_name AS tbl_name,
                    table_rows AS tbl_rows,
                    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
                FROM information_schema.TABLES
                WHERE table_schema = %s
                ORDER BY (data_length + index_length) DESC;
            """
            cursor.execute(sql, (DB_NAME,))
            rows = cursor.fetchall()
            conn.close()

            total_used_mb = sum(float(r['size_mb'] or 0) for r in rows)
            total_quota_mb = 5120.0
            remain_mb = max(0.0, total_quota_mb - total_used_mb)
            usage_pct = (total_used_mb / total_quota_mb) * 100

            dialog = QDialog(self)
            dialog.setWindowTitle("중앙 TiDB Cloud 실시간 스토리지 용량 보고서")
            dialog.resize(600, 420)
            layout = QVBoxLayout(dialog)

            lbl_summary = QLabel(
                f"총 할당 용량 : {total_quota_mb / 1024:.1f} GB (5,120 MB)\n"
                f"현재 사용량 : {total_used_mb:.2f} MB ({usage_pct:.3f}% 사용 중)\n"
                f"남은 여유 공간 : {remain_mb / 1024:.2f} GB ({remain_mb:.1f} MB)"
            )
            lbl_summary.setStyleSheet(
                "font-size: 15px; font-weight: bold; background-color: #E1F5FE; "
                "color: #01579B; padding: 15px; border-radius: 6px; border: 1px solid #81D4FA;"
            )
            layout.addWidget(lbl_summary)

            table = QTableWidget()
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["테이블명", "보관 데이터 수(행)", "사용 용량 (MB)"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setRowCount(len(rows))

            for i, r in enumerate(rows):
                table.setItem(i, 0, QTableWidgetItem(str(r['tbl_name'])))
                table.setItem(i, 1, QTableWidgetItem(f"{int(r['tbl_rows'] or 0):,} 건"))
                table.setItem(i, 2, QTableWidgetItem(f"{float(r['size_mb'] or 0):.2f} MB"))

            layout.addWidget(table)

            btn_close = QPushButton("확 인")
            btn_close.setStyleSheet("padding: 10px; font-weight: bold; background-color: #0288D1; color: white;")
            btn_close.clicked.connect(dialog.accept)
            layout.addWidget(btn_close)

            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "오류", f"용량 정보 조회 중 오류가 발생했습니다:\n{e}")

    def load_company_list_to_combo(self):
        try:
            conn = get_db_connection()
            if not conn: return
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT company_id, user_name FROM users WHERE company_id != 'ALL' AND company_id != ''")
            companies = cursor.fetchall()
            conn.close()
            
            for c in companies:
                self.combo_master_company.addItem(f"{c['user_name']} ({c['company_id']})", c['company_id'])
        except Exception as e:
            print(f"회원사 목록 로드 실패: {e}")

    def on_company_filter_changed(self):
        self.load_database()
        self.refresh_all_tables()

    def get_active_company_id(self):
        if not self.current_user: return 'COMP_A'
        if self.current_user['role'] == 'MASTER' and hasattr(self, 'combo_master_company'):
            return self.combo_master_company.currentData()
        return self.current_user['company_id']

    def log(self, message, is_error=False):
        now = datetime.now().strftime("[%H:%M:%S]")
        formatted_msg = f"{now} {message}"
        if hasattr(self, 'txt_log'):
            self.txt_log.append(formatted_msg)
            self.txt_log.verticalScrollBar().setValue(self.txt_log.verticalScrollBar().maximum())
            
        if is_error:
            self.send_error_log_to_db(message)

    def send_error_log_to_db(self, error_msg):
        try:
            tb_str = traceback.format_exc()
            comp_id = self.get_active_company_id() if self.current_user else "UNKNOWN"
            user_id = self.current_user['user_id'] if self.current_user else "UNKNOWN"
            
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                sql = "INSERT INTO error_logs (company_id, user_id, error_msg, traceback) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (comp_id, user_id, str(error_msg), tb_str))
                conn.close()
        except Exception:
            pass

    def load_app_state(self):
        if os.path.exists(APP_STATE_FILE):
            try:
                with open(APP_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    raw_jobs = data.get("selected_jobs", [])
                    self.selected_jobs = set(tuple(j) for j in raw_jobs)
                    raw_clients = data.get("known_clients", [])
                    self.known_clients = set(raw_clients)
            except Exception as e:
                self.log(f"app_state.json 로드 실패: {e}", is_error=True)
                self.selected_jobs = set()
                self.known_clients = set()

    def save_app_state(self):
        try:
            data = {
                "selected_jobs": [list(j) for j in self.selected_jobs],
                "known_clients": list(self.known_clients)
            }
            with open(APP_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.log(f"app_state.json 저장 실패: {e}", is_error=True)

    def refresh_client_completer(self):
        clients = set(self.known_clients)
        if not self.df.empty and '거래처' in self.df.columns:
            for c in self.df['거래처'].dropna().unique():
                c_str = str(c).strip()
                if c_str and c_str != '거래처':
                    clients.add(c_str)
        client_list = sorted(list(clients))
        if hasattr(self, 'client_completer'):
            model = QStringListModel(client_list, self.client_completer)
            self.client_completer.setModel(model)

    def init_ui(self):
        self.setWindowTitle(f"신성미래서적-도서검수시스템 v{CURRENT_APP_VERSION}")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.resize(1350, 920)
        main_layout = QVBoxLayout(self)
        
        self.status_bar_layout = QHBoxLayout()
        self.lbl_db_status = QLabel("🟢 네트워크 연결 확인 중...")
        self.lbl_db_status.setStyleSheet("font-size: 13px; font-weight: bold; padding: 6px; background-color: #ECEFF1; color: #333;")
        self.status_bar_layout.addWidget(self.lbl_db_status, 4)

        self.lbl_user_info = QLabel("로그인 정보 없음")
        self.lbl_user_info.setStyleSheet("font-size: 13px; font-weight: bold; padding: 6px; background-color: #E3F2FD; color: #1565C0;")
        self.status_bar_layout.addWidget(self.lbl_user_info, 2)

        self.btn_manual_sync = QPushButton("DB 수동 새로고침")
        self.btn_manual_sync.setStyleSheet("font-size: 13px; font-weight: bold; padding: 6px 15px; background-color: #007ACC; color: white; border-radius: 4px;")
        self.btn_manual_sync.clicked.connect(self.manual_refresh_action)
        self.status_bar_layout.addWidget(self.btn_manual_sync, 1)

        main_layout.addLayout(self.status_bar_layout)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { font-size: 16px; font-weight: bold; padding: 12px 25px; margin-right: 5px; } QTabBar::tab:selected { background-color: #007ACC; color: white; }")
        
        self.tab_register = QWidget(); self.init_register_tab(); self.tabs.addTab(self.tab_register, "1. 등록")
        self.tab_inspect = QWidget(); self.init_inspect_tab(); self.tabs.addTab(self.tab_inspect, "2. 검수")
        self.tab_list = QWidget(); self.init_list_tab(); self.tabs.addTab(self.tab_list, "3. 목록")
        self.tab_history = QWidget(); self.init_history_tab(); self.tabs.addTab(self.tab_history, "4. 내역")
        self.tab_summary = QWidget(); self.init_summary_tab(); self.tabs.addTab(self.tab_summary, "5. 집계")
        self.tab_settings = QWidget(); self.init_settings_tab(); self.tabs.addTab(self.tab_settings, "6. 라벨 설정")
        
        main_layout.addWidget(self.tabs)

        self.log_group = QGroupBox("시스템 실시간 연동 로그 (네트워크/DB 통신 모니터링)")
        self.log_group.setStyleSheet("QGroupBox { font-weight: bold; color: #37474F; font-size: 12px; }")
        log_layout = QVBoxLayout(self.log_group)
        log_layout.setContentsMargins(5, 5, 5, 5)
        
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(100)
        self.txt_log.setStyleSheet("background-color: #1E1E1E; color: #00FF66; font-family: 'Consolas', 'Malgun Gothic'; font-size: 12px;")
        log_layout.addWidget(self.txt_log)
        
        main_layout.addWidget(self.log_group)
        self.log_group.hide()

        self.setLayout(main_layout)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(30000)  # 10초 -> 30초로 완화하여 UI 프리징 방지
        self.sync_timer.timeout.connect(self.auto_sync_job)
        self.sync_timer.start()

    def manual_refresh_action(self):
        self.log("수동 새로고침 요청 중...")
        self.load_database()
        self.refresh_all_tables()
        if self.tabs.currentIndex() == 1:
            self.refresh_inspect_tab()

    def sanitize_dataframe_columns(self, df_in):
        if df_in.empty: return df_in
        req_cols = ['id', '등록일자', '등록일시', '거래처', '납품처', '내용', '순번', '도서명', '저자', '출판사', '정가', '권수', 'ISBN', 'ISBN_Clean', '상태', '입고일시', '비고', 'company_id']
        for col in req_cols:
            if col not in df_in.columns: df_in[col] = ""
        df_in.fillna("", inplace=True)
        df_in = df_in.astype(str)
        
        mask = (df_in['도서명'] != '도서명') & (df_in['거래처'] != '거래처') & (df_in['납품처'] != '납품처') & (df_in['도서명'] != '') & (df_in['상태'] != '삭제')
        return df_in[mask].reset_index(drop=True)

    def load_database(self):
        if self.is_saving: return 
        
        conn = get_db_connection()
        if conn:
            try:
                self.is_online = True
                cursor = conn.cursor()
                
                comp_id = self.get_active_company_id()
                if comp_id == 'ALL':
                    query = "SELECT id, reg_date AS 등록일자, reg_dt AS 등록일시, client AS 거래처, delivery AS 납품처, content AS 내용, seq AS 순번, title AS 도서명, author AS 저자, publisher AS 출판사, price AS 정가, qty AS 권수, isbn AS ISBN, isbn_clean AS ISBN_Clean, status AS 상태, intake_dt AS 입고일시, remarks AS 비고, company_id FROM books"
                    cursor.execute(query)
                else:
                    query = "SELECT id, reg_date AS 등록일자, reg_dt AS 등록일시, client AS 거래처, delivery AS 납품처, content AS 내용, seq AS 순번, title AS 도서명, author AS 저자, publisher AS 출판사, price AS 정가, qty AS 권수, isbn AS ISBN, isbn_clean AS ISBN_Clean, status AS 상태, intake_dt AS 입고일시, remarks AS 비고, company_id FROM books WHERE company_id=%s"
                    cursor.execute(query, (comp_id,))
                    
                rows = cursor.fetchall()
                conn.close()
                
                db_df = pd.DataFrame(rows)
                db_df = self.sanitize_dataframe_columns(db_df)
                
                self.df = db_df
                self.df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')

                if hasattr(self, 'lbl_db_status'):
                    self.lbl_db_status.setText("🟢 온라인 (중앙 서버 연결됨)")
                    self.lbl_db_status.setStyleSheet("font-size: 13px; font-weight: bold; padding: 6px; background-color: #E8F5E9; color: #2E7D32;")
                self.log(f"중앙 서버 데이터 동기화 완료 (총 {len(self.df)}건 정상 도서)")
                return
            except Exception as e:
                self.log(f"DB 로드 오류: {e}", is_error=True)

        self.is_online = False
        if hasattr(self, 'lbl_db_status'):
            self.lbl_db_status.setText("🔴 오프라인 (로컬 전용 모드 작동 중)")
            self.lbl_db_status.setStyleSheet("font-size: 13px; font-weight: bold; padding: 6px; background-color: #FFEBEE; color: #C62828;")

        if os.path.exists(DB_FILE):
            try:
                local_df = pd.read_csv(DB_FILE, dtype=str, encoding='utf-8-sig')
                self.df = self.sanitize_dataframe_columns(local_df)
                self.log(f"로컬 백업(CSV) 데이터 사용 중 (총 {len(self.df)}건 도서)")
            except Exception as e:
                self.log(f"로컬 백업 로드 오류: {e}", is_error=True)
        else:
            self.df = pd.DataFrame()

    def save_database(self):
        self.is_saving = True 
        comp_id = self.get_active_company_id()
        
        if not self.df.empty:
            active_df = self.df[self.df['상태'] != '삭제'].reset_index(drop=True)
            active_df = self.sanitize_dataframe_columns(active_df)
            try:
                active_df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            except Exception as e:
                self.log(f"로컬 CSV 저장 실패: {e}", is_error=True)
        else:
            if os.path.exists(DB_FILE): os.remove(DB_FILE)

        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                
                # DB의 최신 데이터 상태 조회
                if comp_id == 'ALL':
                    cursor.execute("SELECT id, status, intake_dt FROM books")
                else:
                    cursor.execute("SELECT id, status, intake_dt FROM books WHERE company_id=%s", (comp_id,))
                
                db_rows = cursor.fetchall()
                # 고유 식별자(PK id)를 키로 매핑하여 중복 도서 충돌 원천 차단
                db_id_map = {str(r['id']): r for r in db_rows}

                insert_data = []
                update_data = []

                for _, r in self.df.iterrows():
                    r_comp = str(r.get('company_id', '')).strip() or comp_id
                    if r_comp == 'ALL': r_comp = 'COMP_A'
                    
                    row_id = str(r.get('id', '')).strip()
                    status = str(r.get('상태', '미입고')).strip()
                    intake_dt = str(r.get('입고일시', '')).strip()

                    # 1. 기존 DB에 있던 도서 (고유 id 기준 1대1 정확한 업데이트)
                    if row_id and row_id != 'nan' and row_id in db_id_map:
                        db_item = db_id_map[row_id]
                        if status != db_item['status']:
                            update_data.append((status, intake_dt, row_id))
                    # 2. 엑셀로 신규 등록된 도서 (신규 INSERT)
                    else:
                        if status != '삭제':
                            insert_data.append((
                                str(r.get('등록일자', '')), str(r.get('등록일시', '')),
                                str(r.get('거래처', '')).strip(), str(r.get('납품처', '')).strip(),
                                str(r.get('내용', '')), str(r.get('순번', '')),
                                str(r.get('도서명', '')), str(r.get('저자', '')), str(r.get('출판사', '')),
                                str(r.get('정가', '')), str(r.get('권수', '')), str(r.get('ISBN', '')),
                                str(r.get('ISBN_Clean', '')).strip(), status, intake_dt,
                                str(r.get('비고', '')), r_comp
                            ))

                if insert_data:
                    sql_insert = """INSERT INTO books (reg_date, reg_dt, client, delivery, content, seq, title, author, publisher, price, qty, isbn, isbn_clean, status, intake_dt, remarks, company_id) 
                                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    cursor.executemany(sql_insert, insert_data)

                if update_data:
                    sql_update = "UPDATE books SET status=%s, intake_dt=%s WHERE id=%s"
                    cursor.executemany(sql_update, update_data)

                # DB 영구 반영 커밋
                conn.commit()
                conn.close()
                
                self.df = self.df[self.df['상태'] != '삭제'].reset_index(drop=True)
                self.is_online = True
                self.log(f"중앙 DB 데이터 안전 동기화 완료! (신규 {len(insert_data)}건 / 상태변경 {len(update_data)}건 반영)")
            except Exception as e:
                self.is_online = False
                self.log(f"중앙 DB 전송 실패(에러): {e}", is_error=True)
        
        self.is_saving = False 

    def auto_sync_job(self):
        if self.is_saving: return
        conn = get_db_connection()
        if conn:
            try:
                self.load_database()
                self.refresh_all_tables()
                if self.tabs.currentIndex() == 1:
                    if hasattr(self, 'line_search') and not self.line_search.text().strip():
                        if self.table_to_inspect.rowCount() == 0:
                            self.refresh_inspect_tab()
            except Exception:
                pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.tabs.currentIndex() == 1 and hasattr(self, 'line_search') and self.line_search.hasFocus():
                self.line_search.clear()
                self.ensure_barcode_focus()
            else:
                if hasattr(self, 'line_search'):
                    self.line_search.clear()
            event.accept()
        elif event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            if self.table_to_inspect.hasFocus():
                self.process_inspect_enter()
                event.accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    # ----------------------------------------------------
    # 1. 등록 탭
    # ----------------------------------------------------
    def init_register_tab(self):
        layout = QVBoxLayout(self.tab_register)
        
        lbl_info = QLabel("엑셀 납품 목록 등록")
        lbl_info.setStyleSheet("font-size: 26px; font-weight: bold; color: #333; margin-top: 20px; margin-bottom: 15px;")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_info)
        
        groupbox_style = """
            QGroupBox { 
                font-size: 16px; 
                font-weight: bold; 
                color: #007ACC; 
                margin-top: 15px; 
                padding-top: 20px; 
                border: 1px solid #B0BEC5; 
                border-radius: 6px; 
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                subcontrol-position: top left; 
                left: 15px; 
                padding: 0 5px; 
                background-color: #FAFAFA; 
            }
        """
        
        meta_box = QGroupBox("납품 건별 기본 Information 입력")
        meta_box.setStyleSheet(groupbox_style)
        meta_form = QFormLayout(meta_box)
        meta_form.setSpacing(12)
        
        self.line_client = QLineEdit()
        self.line_client.setPlaceholderText("거래처명을 입력하고 엔터를 누르세요 (예: 경남서점)")
        self.line_client.setStyleSheet("padding: 8px; font-size: 15px; border: 2px solid #607D8B; border-radius: 4px;")
        
        self.client_completer = QCompleter(self)
        self.client_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.client_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.line_client.setCompleter(self.client_completer)
        self.refresh_client_completer()

        self.line_client.returnPressed.connect(self.check_client_interlock)
        
        self.line_delivery = QLineEdit()
        self.line_delivery.setPlaceholderText("납품처 세부 항목을 입력하세요 (예: 시립어린이전문)")
        self.line_delivery.setStyleSheet("padding: 8px; font-size: 15px; border: 1px solid #ccc; border-radius: 4px;")
        
        self.line_content = QLineEdit()
        self.line_content.setPlaceholderText("엑셀 B열이 빈 경우 사용할 대표 내용 (예: 어린이전문 1)")
        self.line_content.setStyleSheet("padding: 8px; font-size: 15px; border: 1px solid #ccc; border-radius: 4px;")
        
        meta_form.addRow("▶ 거래처 입력 :", self.line_client)
        meta_form.addRow("▶ 납품처 입력 :", self.line_delivery)
        meta_form.addRow("▶ 내용 항목 입력 :", self.line_content)
        layout.addWidget(meta_box)
        
        guide_box = QGroupBox("권장 엑셀 데이터 양식 (실물 엑셀 서식 기준)")
        guide_box.setStyleSheet("""
            QGroupBox { 
                font-size: 16px; 
                font-weight: bold; 
                color: #455A64; 
                margin-top: 15px; 
                padding-top: 25px; 
                border: 1px solid #B0BEC5; 
                border-radius: 6px; 
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                subcontrol-position: top left; 
                left: 15px; 
                padding: 0 5px; 
                background-color: #FAFAFA; 
            }
        """)
        guide_layout = QVBoxLayout(guide_box)
        
        guide_desc = QLabel("※ B열(기적1차 1, 기적1차 2 등)의 행별 고유 내용이 각각 정확히 유지되어 인쇄됩니다!\n"
                            "※ 검수를 위해 [ISBN] 또는 [바코드] 열은 반드시 엑셀에 존재해야 합니다.")
        guide_desc.setStyleSheet("font-size: 14px; color: #555; font-weight: normal; margin-bottom: 8px;")
        guide_layout.addWidget(guide_desc)
        
        example_table = QTableWidget(1, 11)
        example_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        example_table.setFixedHeight(65)
        example_table.setHorizontalHeaderLabels(['번호', '납품처+연번', '도서', '저자', '출판사', '단가', '수량', '금액', 'ISBN', '납품처', '연번'])
        example_table.setItem(0, 0, QTableWidgetItem("1"))
        example_table.setItem(0, 1, QTableWidgetItem("기적1차 1"))
        example_table.setItem(0, 2, QTableWidgetItem("111년 후 이 자리에는 커다란 삼나무가 자랄 거야"))
        example_table.setItem(0, 3, QTableWidgetItem("쥘리 두인 지음..."))
        example_table.setItem(0, 4, QTableWidgetItem("아이스크림미디어"))
        example_table.setItem(0, 5, QTableWidgetItem("16800"))
        example_table.setItem(0, 6, QTableWidgetItem("1"))
        example_table.setItem(0, 7, QTableWidgetItem("16800"))
        example_table.setItem(0, 8, QTableWidgetItem("9791159295492"))
        example_table.setItem(0, 9, QTableWidgetItem("기적1차"))
        example_table.setItem(0, 10, QTableWidgetItem("1"))
        example_table.setStyleSheet("font-size: 13px; font-weight: normal; color: black;")
        example_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        guide_layout.addWidget(example_table)
        layout.addWidget(guide_box)
        
        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton("위 정보로 새 엑셀(.xlsx) 파일 자동 인식하여 등록하기")
        self.btn_load.setStyleSheet("background-color: #FF9800; color: white; font-size: 18px; font-weight: bold; padding: 20px; border-radius: 12px;")
        self.btn_load.clicked.connect(self.load_excel)
        
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_load, 4)
        btn_layout.addStretch(1)
        
        layout.addLayout(btn_layout)
        layout.addStretch(1)

    def check_client_interlock(self):
        client_text = self.line_client.text().strip()
        if not client_text: return
        
        self.known_clients.add(client_text)
        self.save_app_state()
        self.refresh_client_completer()
            
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("거래처 확인")
        msg_box.setText(f"입력하신 거래처가 '[ {client_text} ]' 이(가) 맞습니까?\n\n(맞으시면 엔터 키나 [예]를 누르세요.)")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        
        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self.line_delivery.setFocus()
            force_korean_ime(self.line_delivery)

    def load_excel(self):
        client_name = self.line_client.text().strip()
        delivery_name = self.line_delivery.text().strip()
        content_name = self.line_content.text().strip()
        comp_id = self.get_active_company_id()
        if comp_id == 'ALL': comp_id = 'COMP_A'
        
        if not client_name or not delivery_name:
            QMessageBox.warning(self, "경고", "거래처와 납품처 정보는 필수 입력 사항입니다.")
            return

        self.known_clients.add(client_name)
        self.save_app_state()
        self.refresh_client_completer()

        from PyQt6.QtWidgets import QFileDialog
        fname, _ = QFileDialog.getOpenFileName(self, '납품 엑셀 파일 불러오기', '', 'Excel Files (*.xlsx *.xls)')
        if fname:
            try:
                new_df = pd.read_excel(fname, dtype=str, header=None)
                new_df.fillna("", inplace=True)
                new_df = new_df.astype(str).apply(lambda s: s.str.strip())

                first_row = new_df.iloc[0]
                has_header = first_row.str.contains('도서명|서명|책제목|도서|순번|연번|번호|저자|출판사|정가|단가|권수|수량|isbn|바코드|납품처', case=False, na=False).any()

                if has_header:
                    header_row = first_row
                    data_df = new_df[1:].copy()
                else:
                    header_row = pd.Series([f"Col_{i}" for i in range(len(new_df.columns))])
                    data_df = new_df.copy()

                std_columns = {
                    '순번': ['순번', '연번', '번호', 'no'], 
                    '도서명': ['도서명', '도서', '서명', '책제목', '품명'],
                    '저자': ['저자', '지은이', '글쓴이'], 
                    '출판사': ['출판사', '발행처'],
                    '정가': ['정가', '가격', '단가', '금액'], 
                    '권수': ['권수', '수량'],
                    'ISBN': ['isbn', '바코드'],
                    '내용': ['내용', '납품처+연번', '납품처연번', '간지내용', '구분', '세부내용']
                }
                
                renamed = {}; mapped_stds = set()
                for col in header_row:
                    c_clean = str(col).strip().lower()
                    for std, aliases in std_columns.items():
                        if c_clean in aliases and std not in mapped_stds:
                            renamed[col] = std; mapped_stds.add(std); break
                            
                data_df.columns = header_row
                data_df.rename(columns=renamed, inplace=True)
                data_df = data_df.loc[:, ~data_df.columns.duplicated()]

                if '내용' not in data_df.columns and len(data_df.columns) > 1:
                    col_1_name = data_df.columns[1]
                    if col_1_name not in ['순번', '도서명', '저자', '출판사', '정가', '권수', 'ISBN']:
                        data_df.rename(columns={col_1_name: '내용'}, inplace=True)

                if 'ISBN' not in data_df.columns:
                    for col in data_df.columns:
                        if data_df[col].astype(str).str.len().max() >= 10 and data_df[col].astype(str).str.isnumeric().any():
                            data_df.rename(columns={col: 'ISBN'}, inplace=True)
                            break
                            
                if 'ISBN' not in data_df.columns:
                    QMessageBox.warning(self, "경고", "'ISBN' 또는 '바코드' 열을 찾지 못했습니다.")
                    return

                def clean_isbn(x):
                    x_str = str(x).strip()
                    try:
                        if 'e' in x_str.lower() or '.' in x_str:
                            return str(int(float(x_str)))
                    except: pass
                    return x_str
                
                data_df['ISBN_Clean'] = data_df['ISBN'].apply(clean_isbn)
                data_df['ISBN_Clean'] = data_df['ISBN_Clean'].astype(str).str.replace(r'\D', '', regex=True)

                now_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                now_date = datetime.now().strftime("%Y-%m-%d")
                errors = []; rows_out = []

                for idx, row in data_df.iterrows():
                    excel_row_num = idx + 1  
                    title = str(row.get('도서명', '')).strip()
                    isbn = str(row.get('ISBN_Clean', '')).strip()
                    orig_isbn = str(row.get('ISBN', '')).strip()

                    if title in ['도서명', '도서'] or orig_isbn in ['ISBN', '바코드']: continue
                    if title == '' and orig_isbn == '': continue
                    if '합계' in title or '총계' in title or '소계' in title: continue

                    has_error = False
                    if title == '':
                        errors.append(f"[엑셀 {excel_row_num}행 오류] 도서명이 누락되었습니다. (입력된 ISBN: {orig_isbn})")
                        has_error = True
                    if isbn == '' or len(isbn) < 10:
                        errors.append(f"[엑셀 {excel_row_num}행 오류] ISBN(바코드)이 유실되었거나 형식이 맞지 않습니다. (도서명: '{title}', 입력값: '{orig_isbn}')")
                        has_error = True

                    if not has_error:
                        raw_b_val = row.iloc[1] if len(row) > 1 else None
                        if pd.notna(raw_b_val) and str(raw_b_val).strip() != "" and str(raw_b_val).strip().lower() != "nan":
                            row_content = str(raw_b_val).strip()
                        else:
                            row_content = content_name

                        row_dict = {}
                        row_dict['도서명'] = title
                        row_dict['ISBN_Clean'] = isbn
                        row_dict['ISBN'] = orig_isbn
                        row_dict['저자'] = str(row.get('저자', '')).strip()
                        row_dict['출판사'] = str(row.get('출판사', '')).strip()
                        row_dict['정가'] = str(row.get('정가', '')).strip()
                        row_dict['권수'] = str(row.get('권수', '1')).strip() or '1'
                        row_dict['내용'] = row_content
                        row_dict['등록일자'] = now_date
                        row_dict['등록일시'] = now_dt
                        row_dict['거래처'] = client_name
                        row_dict['납품처'] = delivery_name
                        row_dict['상태'] = '미입고'
                        row_dict['입고일시'] = '' 
                        row_dict['비고'] = ''
                        row_dict['company_id'] = comp_id
                        rows_out.append(row_dict)

                if errors:
                    err_dialog = QDialog(self)
                    err_dialog.setWindowTitle("엑셀 데이터 등록 오류 리포트 (등록 취소됨)")
                    err_dialog.resize(650, 450)
                    err_layout = QVBoxLayout(err_dialog)
                    
                    lbl_msg = QLabel(f"수입 검사 결과 총 {len(errors)}개의 데이터 결격 행이 발견되었습니다.\n"
                                     f"데이터 무결성을 지키기 위해 모든 도서의 등록이 전면 중단되었습니다.")
                    lbl_msg.setStyleSheet("font-weight: bold; color: #D32F2F; font-size: 14px;")
                    err_layout.addWidget(lbl_msg)
                    
                    text_edit = QTextEdit()
                    text_edit.setReadOnly(True)
                    text_edit.setPlainText("\n".join(errors))
                    text_edit.setStyleSheet("font-family: 'Malgun Gothic'; font-size: 13px; color: #B71C1C; background-color: #FFEBEE; border: 1px solid #FFCDD2;")
                    err_layout.addWidget(text_edit)
                    
                    btn_close = QPushButton("확인 (등록 취소 및 엑셀 수정하러 가기)")
                    btn_close.setStyleSheet("background-color: #D32F2F; color: white; font-weight: bold; padding: 12px; border-radius: 4px; font-size: 14px;")
                    btn_close.clicked.connect(err_dialog.accept)
                    err_layout.addWidget(btn_close)
                    
                    err_dialog.exec()
                    return 

                if not rows_out:
                    QMessageBox.warning(self, "경고", "등록 가능한 정상 도서 데이터가 엑셀 파일에 존재하지 않습니다.")
                    return

                final_df = pd.DataFrame(rows_out).reset_index(drop=True)
                final_df['순번'] = range(1, len(final_df) + 1)
                
                for req_col in ['순번', '도서명', '저자', '출판사', '정가', '권수']:
                    if req_col not in final_df.columns: final_df[req_col] = ''
                
                if self.df.empty: self.df = final_df
                else: self.df = pd.concat([self.df, final_df], ignore_index=True)
                
                self.save_database() 
                self.refresh_all_tables()
                QMessageBox.information(self, "등록 완료", f"[{client_name}-{delivery_name}] 목록 도서 {len(final_df)}건이 성공적으로 등록되었습니다!")
                
                self.line_client.clear(); self.line_delivery.clear(); self.line_content.clear()
                self.tabs.setCurrentIndex(1) 
            except Exception as e:
                QMessageBox.warning(self, "오류", f"엑셀 분석 중 오류 발생:\n{e}")

    # ----------------------------------------------------
    # 2. 검수 탭
    # ----------------------------------------------------
    def init_inspect_tab(self):
        layout = QVBoxLayout(self.tab_inspect)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ★ [모드 전환 바] 권한별 숨김/표시를 위해 QWidget 컨테이너로 감싸기
        self.mode_bar_widget = QWidget()
        mode_bar = QHBoxLayout(self.mode_bar_widget)
        mode_bar.setContentsMargins(0, 0, 0, 0)
        mode_bar.setSpacing(8)

        self.btn_mode_delivery = QPushButton("📦 1. 납품 도서 검수 모드 (공공/학교 납품)")
        self.btn_mode_delivery.setStyleSheet("font-size: 15px; font-weight: bold; padding: 10px; background-color: #1976D2; color: white; border-radius: 4px;")
        self.btn_mode_delivery.clicked.connect(lambda: self.set_inspect_mode(False))

        self.btn_mode_store = QPushButton("🏪 2. 매장 재고 입고 모드 (서점 매대 진열)")
        self.btn_mode_store.setStyleSheet("font-size: 15px; font-weight: bold; padding: 10px; background-color: #ECEFF1; color: #455A64; border-radius: 4px;")
        self.btn_mode_store.clicked.connect(lambda: self.set_inspect_mode(True))

        mode_bar.addWidget(self.btn_mode_delivery, 1)
        mode_bar.addWidget(self.btn_mode_store, 1)
        layout.addWidget(self.mode_bar_widget)

        # ★ [매장 모드 전용 매입처 툴바]
        self.store_vendor_group = QGroupBox("매장 매입처(거래처) 선택")
        self.store_vendor_group.setStyleSheet("QGroupBox { font-weight: bold; color: #2E7D32; background-color: #E8F5E9; padding: 6px; border-radius: 4px; }")
        store_vendor_layout = QHBoxLayout(self.store_vendor_group)
        store_vendor_layout.setContentsMargins(8, 8, 8, 8)

        self.store_vendor_buttons = []
        preset_vendors = ["북센", "출협", "교보", "인교", "알라딘", "YES24", "영풍"]
        for v in preset_vendors:
            btn_v = QPushButton(v)
            btn_v.setCheckable(True)
            btn_v.setStyleSheet("font-size: 13px; font-weight: bold; padding: 5px 10px;")
            if v == "북센":
                btn_v.setChecked(True)
                btn_v.setStyleSheet("font-size: 13px; font-weight: bold; padding: 5px 10px; background-color: #2E7D32; color: white;")
            btn_v.clicked.connect(lambda checked, name=v: self.on_store_preset_clicked(name))
            store_vendor_layout.addWidget(btn_v)
            self.store_vendor_buttons.append(btn_v)

        store_vendor_layout.addWidget(QLabel("기타/출판사:"))
        self.line_custom_vendor = QLineEdit()
        self.line_custom_vendor.setPlaceholderText("출판사명 직접 입력 후 엔터")
        self.line_custom_vendor.setFixedWidth(160)
        self.line_custom_vendor.returnPressed.connect(self.on_custom_vendor_entered)
        
        # 거래처 자동완성 설정
        self.vendor_completer = QCompleter(self)
        self.vendor_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.vendor_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.line_custom_vendor.setCompleter(self.vendor_completer)
        self.refresh_client_completer()

        store_vendor_layout.addWidget(self.line_custom_vendor)
        layout.addWidget(self.store_vendor_group)
        self.store_vendor_group.hide()  # 기본은 납품 모드이므로 숨김

        top_bar = QHBoxLayout()
        self.btn_all_select = QPushButton("전체지정")
        self.btn_all_select.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_all_select.clicked.connect(self.select_all_jobs_globally)
        
        self.btn_list_select = QPushButton("목록지정")
        self.btn_list_select.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_list_select.clicked.connect(self.open_job_list_dialog)
        
        top_bar.addWidget(self.btn_all_select)
        top_bar.addWidget(self.btn_list_select)
        
        top_bar.addWidget(QLabel("검색어(Esc):"))
        self.line_search = QLineEdit()
        self.line_search.setPlaceholderText("도서명, ISBN 등으로 필터링...")
        self.line_search.setStyleSheet("padding: 5px;")
        self.line_search.textChanged.connect(self.search_inspect_table)
        top_bar.addWidget(self.line_search)
        
        top_bar.addWidget(QLabel("일자지정:"))
        self.chk_date_limit = QLineEdit(datetime.now().strftime("%Y-%m-%d"))
        self.chk_date_limit.setReadOnly(True)
        self.chk_date_limit.setFixedWidth(100)
        self.chk_date_limit.setStyleSheet("padding: 5px; background-color: #f0f0f0; text-align: center;")
        top_bar.addWidget(self.chk_date_limit)
        
        top_bar.addWidget(QLabel("입고처:"))
        self.line_supplier = QLineEdit()
        self.line_supplier.setPlaceholderText("선택된 작업 목록 없음")
        self.line_supplier.setReadOnly(True)
        self.line_supplier.setStyleSheet("padding: 5px; background-color: #E0E0E0; font-weight: bold; color: #333;")
        top_bar.addWidget(self.line_supplier)
        
        self.btn_inspect_close = QPushButton("닫 기")
        self.btn_inspect_close.setStyleSheet("padding: 6px 12px;")
        self.btn_inspect_close.clicked.connect(lambda: self.tabs.setCurrentIndex(2))  
        top_bar.addWidget(self.btn_inspect_close)
        
        layout.addLayout(top_bar)
        
        upper_group = QGroupBox("바코드 매칭 인식 도서 목록 (선택 후 [엔터] 키 입력 시 간지 출력)")
        upper_group.setStyleSheet("QGroupBox { font-weight: bold; color: #007ACC; }")
        upper_layout = QVBoxLayout(upper_group)
        
        self.table_to_inspect = QTableWidget()
        self.table_to_inspect.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_to_inspect.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_to_inspect.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_to_inspect.cellDoubleClicked.connect(self.on_book_double_clicked)
        upper_layout.addWidget(self.table_to_inspect)
        layout.addWidget(upper_group, 3)  
        
        middle_bar = QHBoxLayout()
        lbl_middle_info = QLabel("★ ISBN체크시만 ISBN이 저장됩니다..")
        lbl_middle_info.setStyleSheet("color: #007ACC; font-weight: bold; font-size: 13px;")
        middle_bar.addWidget(lbl_middle_info)
        
        self.cb_similar = QCheckBox("유사도서 검색")
        self.cb_direct_print = QCheckBox("바로인쇄"); self.cb_direct_print.setChecked(True); self.cb_direct_print.setStyleSheet("font-weight: bold; color: #2E7D32;")
        self.cb_one_page = QCheckBox("1장만인쇄")
        self.cb_individual = QCheckBox("권수별 개별인쇄")
        self.cb_isbn_print = QCheckBox("ISBN 표시")
        self.cb_print_active = QCheckBox("인쇄"); self.cb_print_active.setChecked(True)
        # ★ 프로그램 자체 비프음 On/Off 옵션 (리더기 하드웨어 소리와 중복 방지 위해 기본 꺼짐)
        self.cb_sound_active = QCheckBox("스피커 소리"); self.cb_sound_active.setChecked(False)
        
        self.combo_format = QComboBox()
        self.combo_format.addItems(["양식1", "양식2"])
        self.combo_format.setEnabled(False)
        
        for cb in [self.cb_similar, self.cb_direct_print, self.cb_one_page, self.cb_individual, self.cb_isbn_print, self.cb_print_active, self.cb_sound_active]:
            middle_bar.addWidget(cb)
        middle_bar.addWidget(self.combo_format)
        
        middle_bar.addWidget(QLabel("바코드 스캔:"))
        self.line_barcode = QLineEdit()
        self.line_barcode.setPlaceholderText("스캐너로 스캔...")
        self.line_barcode.setStyleSheet("font-size: 16px; font-weight: bold; padding: 6px; border: 3px solid #FF9800; border-radius: 4px;")
        self.line_barcode.setFixedWidth(220)
        self.line_barcode.returnPressed.connect(self.process_barcode)
        middle_bar.addWidget(self.line_barcode)
        
        layout.addLayout(middle_bar)
        
        lower_group = QGroupBox("최근 입고 및 간지 출력 도서 내역 (완료 히스토리 역사순)")
        lower_group.setStyleSheet("QGroupBox { font-weight: bold; color: #43A047; }")
        lower_layout = QVBoxLayout(lower_group)
        
        self.table_recent = QTableWidget()
        self.table_recent.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_recent.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_recent.cellDoubleClicked.connect(self.on_book_double_clicked)
        lower_layout.addWidget(self.table_recent)
        layout.addWidget(lower_group, 2)  
        
        self.lbl_scan_result = QLabel("스캔 대기 중..."); self.lbl_scan_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_scan_result.setStyleSheet("font-size: 20px; font-weight: bold; color: gray; margin: 3px;")
        layout.addWidget(self.lbl_scan_result)
    def set_inspect_mode(self, is_store_mode):
        """납품 검수 모드 <-> 매장 재고 입고 모드 스위칭"""
        self.store_mode = is_store_mode
        if is_store_mode:
            self.btn_mode_store.setStyleSheet("font-size: 15px; font-weight: bold; padding: 10px; background-color: #2E7D32; color: white; border-radius: 4px;")
            self.btn_mode_delivery.setStyleSheet("font-size: 15px; font-weight: bold; padding: 10px; background-color: #ECEFF1; color: #455A64; border-radius: 4px;")
            self.store_vendor_group.show()
            self.cb_print_active.setChecked(False)  # 매장 진열용은 간지 인쇄 기본 끔
            self.line_supplier.setText(f"[매장재고] 공급처: {self.store_vendor}")
            self.lbl_scan_result.setText(f"🏪 매장 입고 모드 작동 중: 바코드를 스캔하면 [{self.store_vendor}] 매장재고로 즉시 입고됩니다.")
            self.lbl_scan_result.setStyleSheet("font-size: 17px; font-weight: bold; color: #2E7D32;")
        else:
            self.btn_mode_delivery.setStyleSheet("font-size: 15px; font-weight: bold; padding: 10px; background-color: #1976D2; color: white; border-radius: 4px;")
            self.btn_mode_store.setStyleSheet("font-size: 15px; font-weight: bold; padding: 10px; background-color: #ECEFF1; color: #455A64; border-radius: 4px;")
            self.store_vendor_group.hide()
            self.cb_print_active.setChecked(True)   # 납품용은 간지 인쇄 켬
            self.refresh_inspect_tab()
        self.ensure_barcode_focus()

    def on_store_preset_clicked(self, vendor_name):
        self.store_vendor = vendor_name
        self.line_custom_vendor.clear()
        for btn in self.store_vendor_buttons:
            if btn.text() == vendor_name:
                btn.setChecked(True)
                btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 5px 10px; background-color: #2E7D32; color: white;")
            else:
                btn.setChecked(False)
                btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 5px 10px;")
        self.line_supplier.setText(f"[매장재고] 공급처: {self.store_vendor}")
        self.ensure_barcode_focus()

    def on_custom_vendor_entered(self):
        text = self.line_custom_vendor.text().strip()
        if text:
            self.store_vendor = text
            self.known_clients.add(text)
            self.save_app_state()
            self.refresh_client_completer()
            for btn in self.store_vendor_buttons:
                btn.setChecked(False)
                btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 5px 10px;")
            self.line_supplier.setText(f"[매장재고] 공급처: {self.store_vendor}")
            QMessageBox.information(self, "거래처 지정", f"매장 입고 거래처가 '[ {text} ]' 로 지정되었습니다.")
        self.ensure_barcode_focus()
    def open_job_list_dialog(self):
        if self.df.empty:
            QMessageBox.warning(self, "안내", "등록된 도서 데이터가 없어 지정할 수 없습니다.")
            return
            
        dialog = JobListDialog(self.df, self.selected_jobs, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_jobs = dialog.get_selected_jobs()
            self.save_app_state() 
            self.refresh_inspect_tab()
        self.ensure_barcode_focus()

    def select_all_jobs_globally(self):
        if self.df.empty:
            QMessageBox.information(self, "안내", "등록된 데이터 원장이 존재하지 않습니다.")
            return
            
        cols = ['거래처', '납품처', '등록일시']
        for c in cols:
            if c not in self.df.columns: self.df[c] = ""
                
        unique_jobs = self.df[cols].drop_duplicates()
        self.selected_jobs = set(unique_jobs.itertuples(index=False, name=None))
        self.save_app_state() 
        self.refresh_inspect_tab()
        QMessageBox.information(self, "완료", f"데이터베이스의 전체 {len(self.selected_jobs)}개 목록이 강제 활성화되었습니다.")

    def refresh_inspect_tab(self):
        if self.df.empty or not self.selected_jobs:
            self.table_to_inspect.clear(); self.table_to_inspect.setRowCount(0)
            self.line_supplier.setText("선택된 목록 없음")
            self.lbl_scan_result.setText("필터 차단: [목록지정]을 마쳐야 스캔이 가능합니다.")
            self.lbl_scan_result.setStyleSheet("font-size: 20px; font-weight: bold; color: #D32F2F;")
            return
            
        mask = self.df.apply(lambda r: (
            str(r.get('거래처', '')).strip(), 
            str(r.get('납품처', '')).strip(), 
            str(r.get('등록일시', '')).strip()
        ) in self.selected_jobs or (
            str(r.get('거래처', '')).strip(), 
            str(r.get('납품처', '')).strip(), 
            str(r.get('내용', '')).strip(),
            str(r.get('등록일시', '')).strip()
        ) in self.selected_jobs or (
            str(r.get('거래처', '')).strip(), 
            str(r.get('납품처', '')).strip()
        ) in self.selected_jobs, axis=1)
        
        active_df = self.df[mask]
        self.table_to_inspect.clear()
        self.table_to_inspect.setRowCount(0)
        
        unique_vendors = active_df['납품처'].unique()
        if len(unique_vendors) == 1: self.line_supplier.setText(str(unique_vendors[0]))
        elif len(unique_vendors) > 1: self.line_supplier.setText(f"{str(unique_vendors[0])} 외 {len(unique_vendors)-1}곳")
        else: self.line_supplier.setText("선택된 목록 없음")
            
        self.lbl_scan_result.setText("Optibook 검수 가드 작동 중: 바코드를 찍으면 인식된 도서가 상단에 표시됩니다.")
        self.lbl_scan_result.setStyleSheet("font-size: 16px; font-weight: bold; color: green;")

    def search_inspect_table(self, text):
        query = text.strip().lower()
        if not query:
            self.table_to_inspect.clear()
            self.table_to_inspect.setRowCount(0)
            self.lbl_scan_result.setText("Optibook 검수 가드 작동 중: 바코드를 찍거나 검색어로 도서를 조회하세요.")
            self.lbl_scan_result.setStyleSheet("font-size: 16px; font-weight: bold; color: green;")
            return

        if self.df.empty:
            return

        # 활성화된 작업 목록 필터링 적용
        if self.selected_jobs:
            mask = self.df.apply(lambda r: (
                str(r.get('거래처', '')).strip(), 
                str(r.get('납품처', '')).strip(), 
                str(r.get('등록일시', '')).strip()
            ) in self.selected_jobs or (
                str(r.get('거래처', '')).strip(), 
                str(r.get('납품처', '')).strip(), 
                str(r.get('내용', '')).strip(),
                str(r.get('등록일시', '')).strip()
            ) in self.selected_jobs or (
                str(r.get('거래처', '')).strip(), 
                str(r.get('납품처', '')).strip()
            ) in self.selected_jobs, axis=1)
            target_df = self.df[mask]
        else:
            target_df = self.df

        # 도서명, ISBN, 저자 대상 조회 (목록 탭과 동일한 검색 방식)
        search_mask = (target_df['도서명'].astype(str).str.lower().str.contains(query, na=False)) | \
                      (target_df['ISBN_Clean'].astype(str).str.contains(query, na=False)) | \
                      (target_df['저자'].astype(str).str.lower().str.contains(query, na=False))
        
        matches = target_df[search_mask]

        if not matches.empty:
            self.render_inspect_table(self.table_to_inspect, matches, append_sum=False)
            self.table_to_inspect.selectRow(0)
            self.lbl_scan_result.setText(f"검색 결과 {len(matches)}건 발견: 도서 선택 후 [엔터(Enter)] 키 입력 시 간지 출력")
            self.lbl_scan_result.setStyleSheet("font-size: 16px; font-weight: bold; color: #007ACC;")
        else:
            self.table_to_inspect.clear()
            self.table_to_inspect.setRowCount(0)
            self.lbl_scan_result.setText(f"'{text}' 검색 결과가 작업 목록에 없습니다.")
            self.lbl_scan_result.setStyleSheet("font-size: 18px; font-weight: bold; color: red;")

    def process_barcode(self):
        isbn = self.line_barcode.text().strip()
        self.line_barcode.clear()
        self.ensure_barcode_focus()
        if not isbn:
            return

        # 10자리 미만의 비정상 짧은 바코드 10회 연속 감지기
        if len(isbn) < 10:
            self.short_scan_count += 1
            if self.short_scan_count >= 10:
                self.short_scan_count = 0
                QMessageBox.warning(
                    self, 
                    "바코드 스캐너 점검 안내", 
                    "⚠️ 바코드가 비정상적으로 짧게 인식되는 현상이 10회 연속 감지되었습니다!\n\n"
                    "1. [메모장]을 열고 바코드를 스캔하여 정상적인 13자리 숫자가 찍히는지 확인해 보세요.\n"
                    "2. 계속해서 짧게 나오거나 키보드 입력이 꼬인 경우,\n"
                    "   스캐너 USB를 뺐다 꽂거나 컴퓨터를 재부팅 후 재시도해 주시기 바랍니다."
                )
        else:
            self.short_scan_count = 0

        # ========================================================
        # ★ [모드 2] 매장 재고 입고 모드 분기 처리
        # ========================================================
        if getattr(self, 'store_mode', False):
            comp_id = self.get_active_company_id()
            if comp_id == 'ALL': comp_id = 'COMP_A'

            now_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            now_date = datetime.now().strftime("%Y-%m-%d")

            # 1. 사내 DB 이력 조회 (메모리 -> 중앙 서버 원장 순차 검색, 삭제된 이력도 메타데이터로 활용)
            ref_book = None
            if not self.df.empty and 'ISBN_Clean' in self.df.columns:
                mem_matches = self.df[self.df['ISBN_Clean'] == isbn]
                if not mem_matches.empty:
                    ref_book = mem_matches.iloc[-1].to_dict()

            # 메모리에 없으면 중앙 DB 서버에서 과거 등록 이력(삭제 도서 포함) 직접 조회
            if not ref_book:
                conn = get_db_connection()
                if conn:
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT title AS 도서명, author AS 저자, publisher AS 출판사, price AS 정가 "
                            "FROM books WHERE isbn_clean=%s AND title != '' ORDER BY id DESC LIMIT 1",
                            (isbn,)
                        )
                        ref_book = cursor.fetchone()
                        conn.close()
                    except Exception:
                        pass

            if ref_book:
                # 과거에 한 번이라도 등록된 적이 있는 경우 -> 서지 정보 자동 완성
                title = str(ref_book.get('도서명', f'도서_{isbn}'))
                author = str(ref_book.get('저자', ''))
                pub = str(ref_book.get('출판사', ''))
                price = str(ref_book.get('정가', '0'))
                remarks = "[사내이력]"
            else:
                # 완전 신규 도서 -> 1초 간이 팝업 호출 (실물 정가 확인)
                dlg = QuickNewBookDialog(isbn, self.store_vendor, self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    self.lbl_scan_result.setText("매장 도서 등록이 취소되었습니다.")
                    self.lbl_scan_result.setStyleSheet("font-size: 16px; color: gray;")
                    return
                b_info = dlg.get_book_data()
                title = b_info['도서명']
                price = b_info['정가']
                author = b_info['저자']
                pub = b_info['출판사']
                remarks = "[수동등록]"

            # 매장재고 도서 수 기준 순번 계산 (매장 1호 도서부터 시작)
            store_count = len(self.df[self.df['납품처'] == '매장재고']) if not self.df.empty else 0

            # 매장재고 데이터프레임 행 생성
            new_row = {
                'id': '',
                '등록일자': now_date,
                '등록일시': now_dt,
                '거래처': self.store_vendor,
                '납품처': '매장재고',
                '내용': '매장입고',
                '순번': str(store_count + 1),
                '도서명': title,
                '저자': author,
                '출판사': pub,
                '정가': price,
                '권수': '1',
                'ISBN': isbn,
                'ISBN_Clean': isbn,
                '상태': '입고',
                '입고일시': now_dt,
                '비고': remarks,
                'company_id': comp_id
            }

            self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
            self.save_database()
            self.refresh_all_tables()

            # 최근 입고 내역 테이블에 즉시 표시
            self.recent_scans.insert(0, new_row)
            recent_df = pd.DataFrame(self.recent_scans)
            self.render_inspect_table(self.table_recent, recent_df, append_sum=False)
            if self.table_recent.rowCount() > 0:
                self.table_recent.selectRow(0)

            if hasattr(self, 'cb_sound_active') and self.cb_sound_active.isChecked():
                play_beep_success()

            self.lbl_scan_result.setText(f"🏪 [매장입고 완료] [{self.store_vendor}] {title} ({int(float(price)):,}원) - 출처: {remarks}")
            self.lbl_scan_result.setStyleSheet("font-size: 18px; font-weight: bold; color: #2E7D32;")
            return

        # ========================================================
        # ★ [모드 1] 기존 납품 도서 검수 모드
        # ========================================================
        if self.df.empty: return

        if not self.selected_jobs:
            if hasattr(self, 'cb_sound_active') and self.cb_sound_active.isChecked():
                play_beep_error()
            self.lbl_scan_result.setText("검수 차단: 활성화된 목록이 없습니다. [목록지정]을 해주세요.")
            self.lbl_scan_result.setStyleSheet("font-size: 20px; font-weight: bold; color: red;")
            return

        QApplication.processEvents()

        mask = self.df.apply(lambda r: (
            str(r.get("거래처", "")).strip(),
            str(r.get("납품처", "")).strip(),
            str(r.get("등록일시", "")).strip(),
        ) in self.selected_jobs or (
            str(r.get("거래처", "")).strip(),
            str(r.get("납품처", "")).strip(),
            str(r.get("내용", "")).strip(),
            str(r.get("등록일시", "")).strip(),
        ) in self.selected_jobs or (
            str(r.get("거래처", "")).strip(),
            str(r.get("납품처", "")).strip(),
        ) in self.selected_jobs, axis=1)

        active_df = self.df[mask]
        matches = active_df[active_df["ISBN_Clean"] == isbn]

        if matches.empty and self.cb_similar.isChecked():
            matches = active_df[
                active_df["도서명"].astype(str).str.contains(isbn, case=False, na=False) |
                active_df["ISBN_Clean"].astype(str).str.contains(isbn, case=False, na=False)
            ]

        if not matches.empty:
            self.render_inspect_table(self.table_to_inspect, matches, append_sum=False)
            self.table_to_inspect.selectRow(0)

            if self.cb_direct_print.isChecked():
                unprocessed = matches[matches["상태"] == "미입고"]
                if not unprocessed.empty:
                    target_idx = unprocessed.index[0]
                    if hasattr(self, 'cb_sound_active') and self.cb_sound_active.isChecked():
                        play_beep_success()
                    self.execute_book_intake(target_idx)
                else:
                    v = str(matches.iloc[0].get("납품처", ""))
                    if hasattr(self, 'cb_sound_active') and self.cb_sound_active.isChecked():
                        play_beep_error()
                    self.lbl_scan_result.setText(f"이미 처리 완료된 도서입니다. [{v}]")
                    self.lbl_scan_result.setStyleSheet("font-size: 22px; font-weight: bold; color: orange;")
            else:
                if hasattr(self, 'cb_sound_active') and self.cb_sound_active.isChecked():
                    play_beep_success()
                self.lbl_scan_result.setText("도서 인식됨. 선택 후 [엔터(Enter)] 키를 치면 간지가 인쇄됩니다.")
                self.lbl_scan_result.setStyleSheet("font-size: 18px; font-weight: bold; color: #007ACC;")
                self.table_to_inspect.setFocus()
        else:
            self.table_to_inspect.clear()
            self.table_to_inspect.setRowCount(0)
            if hasattr(self, 'cb_sound_active') and self.cb_sound_active.isChecked():
                play_beep_error()
            self.lbl_scan_result.setText("스캔 실패: 선택된 활성 작업 목록에 존재하지 않는 도서입니다.")
            self.lbl_scan_result.setStyleSheet("font-size: 22px; font-weight: bold; color: red;")

    def process_inspect_enter(self):
        row = self.table_to_inspect.currentRow()
        if row < 0: return
        item = self.table_to_inspect.item(row, 0)
        if not item: return
        
        orig_idx = item.data(Qt.ItemDataRole.UserRole)
        if orig_idx is None or orig_idx not in self.df.index: return
        
        row_data = self.df.loc[orig_idx]
        if row_data['상태'] == '입고':
            self.lbl_scan_result.setText("이미 입고 처리가 마감된 도서입니다.")
            self.lbl_scan_result.setStyleSheet("font-size: 20px; font-weight: bold; color: orange;")
            self.ensure_barcode_focus()
            return
            
        self.execute_book_intake(orig_idx)
        
        item_status = self.table_to_inspect.item(row, 0)
        if item_status:
            item_status.setText("입고")
            item_status.setForeground(QColor("blue"))
            item_status.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            
        self.ensure_barcode_focus()

    def execute_book_intake(self, target_idx):
        self.df.at[target_idx, '상태'] = '입고'
        self.df.at[target_idx, '입고일시'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_database()
        
        row_data = self.df.loc[target_idx]
        vendor = str(row_data.get('납품처', ''))
        title = str(row_data.get('도서명', ''))
        
        self.lbl_scan_result.setText(f"간지 인쇄 및 입고 처리 완료: [{vendor}] {title}")
        self.lbl_scan_result.setStyleSheet("font-size: 20px; font-weight: bold; color: blue;")
        
        if self.cb_print_active.isChecked():
            try:
                qty = int(float(row_data.get('권수', 1)))
            except:
                qty = 1

            if self.cb_one_page.isChecked():
                self.trigger_physical_print_for_row(row_data, silent=True)
            elif self.cb_individual.isChecked() and qty > 1:
                for i in range(1, qty + 1):
                    temp_row = row_data.copy()
                    temp_row['권수_표시'] = f"{i}-{qty}"
                    self.trigger_physical_print_for_row(temp_row, silent=True)
            else:
                self.trigger_physical_print_for_row(row_data, silent=True)
            
        self.recent_scans.insert(0, row_data)
        recent_df = pd.DataFrame(self.recent_scans)
        self.render_inspect_table(self.table_recent, recent_df, append_sum=False)
        
        if self.table_recent.rowCount() > 0:
            self.table_recent.selectRow(0)

    # ----------------------------------------------------
    # 3. 목록 탭
    # ----------------------------------------------------
    def init_list_tab(self):
        layout = QVBoxLayout(self.tab_list)
        filter_layout = QHBoxLayout()
        self.combo_list_vendor = QComboBox(); self.combo_list_vendor.setStyleSheet("font-size: 15px; padding: 5px;")
        self.combo_list_status = QComboBox(); self.combo_list_status.addItems(["전체", "입고", "미입고"])
        self.combo_list_status.setStyleSheet("font-size: 15px; padding: 5px;")
        self.line_list_search = QLineEdit()
        self.line_list_search.setPlaceholderText("더블클릭 시 도서 정보 수정 가능! (검색...)")
        self.line_list_search.setStyleSheet("font-size: 15px; padding: 5px;")
        self.line_list_search.returnPressed.connect(self.search_list)
        
        self.btn_search = QPushButton("검색"); self.btn_search.setStyleSheet("background-color: #607D8B; color: white; font-weight: bold; padding: 8px;")
        self.btn_search.clicked.connect(self.search_list)
        
        self.btn_export_excel = QPushButton("엑셀 내보내기")
        self.btn_export_excel.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 8px; border-radius: 4px;")
        self.btn_export_excel.clicked.connect(self.export_to_excel)
        
        filter_layout.addWidget(QLabel("납품처:")); filter_layout.addWidget(self.combo_list_vendor)
        filter_layout.addWidget(QLabel("상태:")); filter_layout.addWidget(self.combo_list_status)
        filter_layout.addWidget(self.line_list_search); filter_layout.addWidget(self.btn_search)
        filter_layout.addWidget(self.btn_export_excel)
        layout.addLayout(filter_layout)
        
        self.table_list = QTableWidget(); self.table_list.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_list.cellDoubleClicked.connect(self.on_book_double_clicked)
        layout.addWidget(self.table_list)

    def search_list(self):
        if self.df.empty: return
        vendor = self.combo_list_vendor.currentText()
        status = self.combo_list_status.currentText()
        query = self.line_list_search.text().strip().lower()
        
        f_df = self.df.copy()
        if vendor != "전체": f_df = f_df[f_df['납품처'] == vendor]
        if status != "전체": f_df = f_df[f_df['상태'] == status]
        if query:
            mask = (f_df['도서명'].astype(str).str.lower().str.contains(query)) | \
                   (f_df['ISBN_Clean'].astype(str).str.contains(query))
            f_df = f_df[mask]
        self.render_table(self.table_list, f_df, show_time=False, append_sum=True)

    def export_to_excel(self):
        if self.df.empty:
            QMessageBox.warning(self, "경고", "내보낼 도서 데이터가 존재하지 않습니다.")
            return
            
        selected_ranges = self.table_list.selectedRanges()
        selected_rows = set()
        for r_range in selected_ranges:
            for r in range(r_range.topRow(), r_range.bottomRow() + 1):
                selected_rows.add(r)
                
        if not selected_rows:
            total_rows = self.table_list.rowCount()
            actual_data_count = total_rows - 2 if total_rows > 2 else total_rows
            for r in range(actual_data_count):
                selected_rows.add(r)
                
        if not selected_rows:
            QMessageBox.warning(self, "경고", "엑셀로 변환할 목록이 없습니다.")
            return
            
        export_data = []
        global_idx = 1
        
        for r in sorted(selected_rows):
            item = self.table_list.item(r, 0)
            if not item: continue
            
            orig_idx = item.data(Qt.ItemDataRole.UserRole)
            if orig_idx is None or orig_idx not in self.df.index: continue
            
            row = self.df.loc[orig_idx]
            
            try: seq_val = int(float(row.get('순번', 0)))
            except: seq_val = row.get('순번', '')
                
            try: price_val = int(float(row.get('정가', 0)))
            except: price_val = row.get('정가', '')
                
            try: qty_val = int(float(row.get('권수', 1)))
            except: qty_val = row.get('권수', '')
                
            export_data.append({
                '전번(전체번호)': global_idx,
                '거래처': row.get('거래처', ''),
                '납품처': row.get('납품처', ''),
                '내용': row.get('내용', ''),
                '순번': seq_val,
                '도서명': row.get('도서명', ''),
                '저자': row.get('저자', ''),
                '출판사': row.get('출판사', ''),
                '정가': price_val,
                '권수': qty_val,
                'ISBN': row.get('ISBN_Clean', ''),
                '입고상태': row.get('상태', ''),
                '작업일자': row.get('입고일시', ''),
                '회원사코드': row.get('company_id', '')
            })
            global_idx += 1
            
        if not export_data:
            QMessageBox.warning(self, "경고", "유효한 도서 내역을 추출하지 못했습니다.")
            return
            
        from PyQt6.QtWidgets import QFileDialog
        
        vendor_name = self.combo_list_vendor.currentText().strip()
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_name = f"입고검수내역_{vendor_name}_{current_time}.xlsx"
        
        fname, _ = QFileDialog.getSaveFileName(self, '엑셀 파일로 저장', default_name, 'Excel Files (*.xlsx)')
        
        if fname:
            try:
                export_df = pd.DataFrame(export_data)
                export_df.to_excel(fname, index=False)
                QMessageBox.information(self, "완료", f"엑셀 파일이 성공적으로 생성되었습니다!\n파일명: {os.path.basename(fname)}")
            except Exception as e:
                QMessageBox.warning(self, "오류", f"엑셀 파일 저장 중 오류가 발생했습니다:\n{e}")

    # ----------------------------------------------------
    # 4. 내역 탭
    # ----------------------------------------------------
    def init_history_tab(self):
        layout = QVBoxLayout(self.tab_history)
        filter_layout = QHBoxLayout()
        lbl = QLabel("입고 날짜 선택:"); lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.date_picker = QDateEdit(); self.date_picker.setCalendarPopup(True); self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setStyleSheet("font-size: 16px; padding: 5px;")
        self.btn_search_history = QPushButton("해당 날짜 입고 내역 조회")
        self.btn_search_history.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px;")
        self.btn_search_history.clicked.connect(self.search_history)
        
        filter_layout.addWidget(lbl); filter_layout.addWidget(self.date_picker); filter_layout.addWidget(self.btn_search_history); filter_layout.addStretch()
        layout.addLayout(filter_layout)
        self.table_history = QTableWidget(); self.table_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_history.cellDoubleClicked.connect(self.on_book_double_clicked)
        layout.addWidget(self.table_history)

    def search_history(self):
        if self.df.empty: return
        target_date = self.date_picker.date().toString("yyyy-MM-dd")
        f_df = self.df[(self.df['상태'] == '입고') & (self.df['입고일시'].astype(str).str.startswith(target_date))]
        self.render_table(self.table_history, f_df, show_time=True, append_sum=True)

    # ----------------------------------------------------
    # 5. 집계 탭
    # ----------------------------------------------------
    def init_summary_tab(self):
        layout = QVBoxLayout(self.tab_summary)
        top_layout = QHBoxLayout()
        self.lbl_grand_total = QLabel("총 합계 | 대기 중...")
        self.lbl_grand_total.setStyleSheet("font-size: 20px; font-weight: bold; background-color: #2196F3; color: white; padding: 15px; border-radius: 8px;")
        top_layout.addWidget(self.lbl_grand_total, 4)
        
        self.btn_delete_vendor = QPushButton("선택한 납품처 삭제")
        self.btn_delete_vendor.setStyleSheet("background-color: #F44336; color: white; font-size: 16px; font-weight: bold; padding: 15px; border-radius: 8px;")
        self.btn_delete_vendor.clicked.connect(self.delete_selected_vendor)
        top_layout.addWidget(self.btn_delete_vendor, 1)
        layout.addLayout(top_layout)
        
        self.table_summary = QTableWidget(); self.table_summary.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_summary.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_summary.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_summary.setColumnCount(6)
        self.table_summary.setHorizontalHeaderLabels(['납품처명', '전체(권)', '입고완료(권)', '미입고(권)', '입고율', '정가합계(원)'])
        header = self.table_summary.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.table_summary.setStyleSheet("font-size: 15px;")
        self.table_summary.cellDoubleClicked.connect(self.on_summary_double_clicked)
        layout.addWidget(self.table_summary)

    def delete_selected_vendor(self):
        selected_items = self.table_summary.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "경고", "삭제할 납품처/등록건을 표에서 먼저 클릭하여 선택해주세요.")
            return
        row = selected_items[0].row()
        item_0 = self.table_summary.item(row, 0)
        batch_key = item_0.data(Qt.ItemDataRole.UserRole)
        vendor_disp = item_0.text()
        
        reply = QMessageBox.question(
            self, 
            '납품처 등록건 삭제 확인', 
            f"정말로 '{vendor_disp}' 등록건의 모든 도서 목록을 삭제하시겠습니까?\n(서버 및 다른 PC에서도 즉시 삭제 반영됩니다)", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.processEvents()
            comp_id = self.get_active_company_id()
            
            if batch_key and isinstance(batch_key, tuple):
                c, v = batch_key[:2]
                mask = (self.df['거래처'] == c) & (self.df['납품처'] == v)
                self.df.loc[mask, '상태'] = '삭제'
                self.selected_jobs = {j for j in self.selected_jobs if j[:2] != (c, v)}
                
                conn = get_db_connection()
                if conn:
                    try:
                        cursor = conn.cursor()
                        if comp_id == 'ALL':
                            cursor.execute("UPDATE books SET status='삭제' WHERE client=%s AND delivery=%s", (c, v))
                        else:
                            cursor.execute("UPDATE books SET status='삭제' WHERE company_id=%s AND client=%s AND delivery=%s", (comp_id, c, v))
                        conn.close()
                    except Exception as e:
                        self.log(f"DB 일괄 삭제 중 오류: {e}", is_error=True)
            else:
                vendor_name = vendor_disp.split('(')[0].split('[')[0].strip()
                mask = self.df['납품처'] == vendor_name
                self.df.loc[mask, '상태'] = '삭제'
                
                conn = get_db_connection()
                if conn:
                    try:
                        cursor = conn.cursor()
                        if comp_id == 'ALL':
                            cursor.execute("UPDATE books SET status='삭제' WHERE delivery=%s", (vendor_name,))
                        else:
                            cursor.execute("UPDATE books SET status='삭제' WHERE company_id=%s AND delivery=%s", (comp_id, vendor_name))
                        conn.close()
                    except Exception as e:
                        self.log(f"DB 일괄 삭제 중 오류: {e}", is_error=True)
                
            self.save_database()
            self.save_app_state()
            self.refresh_all_tables()
            QMessageBox.information(self, "삭제 완료", f"'{vendor_disp}' 등록건이 성공적으로 삭제 처리되었습니다.")

    def on_summary_double_clicked(self, row, col):
        vendor = self.table_summary.item(row, 0).text()
        status_filter = "전체"
        if col == 2: status_filter = "입고"
        elif col == 3: status_filter = "미입고"
        self.tabs.setCurrentIndex(2)
        self.combo_list_vendor.setCurrentText(vendor); self.combo_list_status.setCurrentText(status_filter)
        self.line_list_search.clear()
        self.search_list()

    # ----------------------------------------------------
    # 6. 라벨 설정 탭
    # ----------------------------------------------------
    def init_settings_tab(self):
        layout = QHBoxLayout(self.tab_settings)
        control_box = QGroupBox("프린터 렌더링 및 위치 설정")
        control_layout = QFormLayout(control_box)
        
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("설정 저장")
        self.btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.btn_save.clicked.connect(self.save_template)
        
        self.btn_test_print = QPushButton("테스트 인쇄")
        self.btn_test_print.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; padding: 10px;")
        self.btn_test_print.clicked.connect(lambda: self.trigger_physical_print_for_row(self.get_current_test_row_data(), silent=False))
        
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_test_print)
        control_layout.addRow(btn_layout)
        
        self.combo_test_data = QComboBox()
        self.combo_test_data.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px;")
        self.combo_test_data.currentIndexChanged.connect(self.update_preview)
        control_layout.addRow("테스트 도서 데이터:", self.combo_test_data)

        self.combo_printer_list = QComboBox()
        self.combo_printer_list.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        self.refresh_available_printers()
        control_layout.addRow("사용할 라벨 프린터:", self.combo_printer_list)

        self.combo_font = QFontComboBox()
        self.combo_font.currentFontChanged.connect(self.update_preview)
        control_layout.addRow("글씨체:", self.combo_font)
        
        self.sliders = {}
        slider_config = [
            ("출력 시작 여백", "1. 세로 위치 (배출구/상하 여백 mm)", 0, 100, 0),
            ("가로 위치", "2. 가로 위치 (80mm 종이 폭 방향 mm)", 0, 60, 0),
            ("라벨 총 출력 길이", "3. 라벨 총 길이 (절단 길이 mm)", 20, 300, 80),
            ("항목 간 줄간격", "4. 글자 항목 간 간격", 0, 50, 2),
            ("긴 글 줄바꿈 간격", "5. 긴 글 줄바꿈 행간", 0, 30, 1),
            ("줄바꿈 들여쓰기 여백", "6. 줄바꿈 들여쓰기 여백", 0, 50, 0)
        ]
        
        for key, disp_name, min_v, max_v, def_v in slider_config:
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(min_v, max_v)
            s.setValue(def_v)
            s.valueChanged.connect(self.update_preview)
            control_layout.addRow(disp_name + ":", s)
            self.sliders[key] = s
            
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(100, 600)
        self.spin_dpi.setValue(203)
        self.spin_dpi.setSuffix(" DPI")
        self.spin_dpi.valueChanged.connect(self.update_preview)
        control_layout.addRow("프린터 해상도:", self.spin_dpi)

        self.spin_huge = QSpinBox()
        self.spin_huge.setRange(12, 200)
        self.spin_huge.setValue(40)  # ★ 기본값: 40
        self.spin_huge.valueChanged.connect(self.update_preview)
        control_layout.addRow("1. 순번 숫자 크기 (대):", self.spin_huge)

        self.spin_large = QSpinBox()
        self.spin_large.setRange(10, 200)
        self.spin_large.setValue(30)  # ★ 기본값: 30
        self.spin_large.valueChanged.connect(self.update_preview)
        control_layout.addRow("2. 기본 정보/납품처 크기 (중):", self.spin_large)

        self.spin_norm = QSpinBox()
        self.spin_norm.setRange(6, 200)
        self.spin_norm.setValue(20)  # ★ 기본값: 20
        self.spin_norm.valueChanged.connect(self.update_preview)
        control_layout.addRow("3. 도서명/정가 크기 (소):", self.spin_norm)
        
        layout.addWidget(control_box, 1)
        
        preview_box = QGroupBox("실물 1:1 완벽 일치 미리보기 (마우스로 드래그하여 위치 보정 가능)")
        preview_layout = QVBoxLayout(preview_box)
        
        self.preview_offset_x = 91
        self.preview_offset_y = -1
        self.preview_extra_len_mm = 0
        self.drag_start_pos = None

        self.lbl_preview_offset_info = QLabel(
            "🖱️ [좌클릭 드래그]: 글자 위치 보정 | 🎡 [마우스 휠]: 미리보기 종이 여백 보정\n"
            "★ 현재 보정값 -> 위치(X: 91 px, Y: -1 px) / 종이 여백: +0 mm"
        )
        self.lbl_preview_offset_info.setStyleSheet("font-size: 13px; font-weight: bold; color: #007ACC; background-color: #E3F2FD; padding: 8px; border-radius: 4px;")
        preview_layout.addWidget(self.lbl_preview_offset_info)

        self.lbl_preview_canvas = QLabel()
        self.lbl_preview_canvas.setStyleSheet("background-color: #333; padding: 15px;")
        self.lbl_preview_canvas.setCursor(Qt.CursorShape.OpenHandCursor)

        self.lbl_preview_canvas.mousePressEvent = self.on_preview_mouse_press
        self.lbl_preview_canvas.mouseMoveEvent = self.on_preview_mouse_move
        self.lbl_preview_canvas.mouseReleaseEvent = self.on_preview_mouse_release
        self.lbl_preview_canvas.wheelEvent = self.on_preview_wheel
        
        scroll = QScrollArea()
        scroll.setWidget(self.lbl_preview_canvas)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #2b2b2b;")
        
        preview_layout.addWidget(scroll)
        layout.addWidget(preview_box, 1)
        
        self.load_template()
        self.refresh_test_data_combo()
        self.update_preview()

    def refresh_test_data_combo(self):
        if not hasattr(self, 'combo_test_data'): return
        
        curr_selected_id = self.combo_test_data.currentData() if self.combo_test_data.currentIndex() > 0 else None

        self.combo_test_data.blockSignals(True)
        self.combo_test_data.clear()
        self.combo_test_data.addItem("샘플 데이터 (기본)", None)
        
        restore_idx = 0
        if not self.df.empty:
            for orig_idx, row in self.df.iterrows():
                v_name = str(row.get('납품처', '')).strip()
                t_name = str(row.get('도서명', '')).strip()
                seq_num = str(row.get('순번', '')).strip()
                disp = f"[{v_name}] {seq_num}. {t_name}"
                if len(disp) > 35:
                    disp = disp[:32] + "..."
                self.combo_test_data.addItem(disp, orig_idx)
                
                if curr_selected_id is not None and orig_idx == curr_selected_id:
                    restore_idx = self.combo_test_data.count() - 1

        self.combo_test_data.setCurrentIndex(restore_idx)
        self.combo_test_data.blockSignals(False)

    def get_current_test_row_data(self):
        if hasattr(self, 'combo_test_data') and self.combo_test_data.currentIndex() > 0:
            orig_idx = self.combo_test_data.currentData()
            if orig_idx is not None and orig_idx in self.df.index:
                return self.df.loc[orig_idx]
        return None

    def refresh_available_printers(self):
        self.combo_printer_list.clear()
        printers = QPrinterInfo.availablePrinterNames()
        default_printer = QPrinterInfo.defaultPrinterName()
        
        if not printers:
            self.combo_printer_list.addItem("설치된 프린터 없음", "")
            return

        selected_idx = 0
        for i, p_name in enumerate(printers):
            self.combo_printer_list.addItem(f"{p_name}", p_name)
            if self.target_printer_name and p_name == self.target_printer_name:
                selected_idx = i
            elif not self.target_printer_name and p_name == default_printer:
                selected_idx = i
                
        self.combo_printer_list.setCurrentIndex(selected_idx)

    def on_preview_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.lbl_preview_canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def on_preview_mouse_move(self, event):
        if self.drag_start_pos and event.buttons() & Qt.MouseButton.LeftButton:
            diff = event.pos() - self.drag_start_pos
            self.drag_start_pos = event.pos()
            
            self.preview_offset_x += diff.x()
            self.preview_offset_y += diff.y()
            
            self.lbl_preview_offset_info.setText(
                f"🖱️ 미리보기 마우스 보정 중... [실제 인쇄물에는 영향 없음]\n"
                f"★ 현재 보정값 -> 가로(X): {self.preview_offset_x} px, 세로(Y): {self.preview_offset_y} px"
            )
            self.update_preview()

    def on_preview_mouse_release(self, event):
        self.drag_start_pos = None
        self.lbl_preview_canvas.setCursor(Qt.CursorShape.OpenHandCursor)

    def on_preview_wheel(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.preview_extra_len_mm += 2
        else:
            self.preview_extra_len_mm -= 2
            
        self.preview_extra_len_mm = max(-30, self.preview_extra_len_mm)
        
        if hasattr(self, 'lbl_preview_offset_info'):
            self.lbl_preview_offset_info.setText(
                f"🖱️ [좌클릭 드래그]: 글자 위치 보정 | 🎡 [마우스 휠]: 미리보기 종이 여백 보정\n"
                f"★ 현재 보정값 -> 위치(X: {self.preview_offset_x} px, Y: {self.preview_offset_y} px) / 종이 여백: {self.preview_extra_len_mm:+} mm"
            )
        self.update_preview()

    def generate_printed_page_image(self, row_data=None, draw_guide=True):
        total_len_mm = self.sliders["라벨 총 출력 길이"].value() if "라벨 총 출력 길이" in self.sliders else 80
        feed_m_mm = self.sliders["출력 시작 여백"].value() if "출력 시작 여백" in self.sliders else 0
        side_m_mm = self.sliders["가로 위치"].value() if "가로 위치" in self.sliders else 0
        user_dpi = self.spin_dpi.value() if hasattr(self, 'spin_dpi') else 203

        base_mm_to_px = lambda mm: int(mm * user_dpi / 25.4)
        offset_x = base_mm_to_px(feed_m_mm)
        offset_y = base_mm_to_px(side_m_mm)

        if draw_guide:
            offset_x += getattr(self, 'preview_offset_x', 0)
            offset_y += getattr(self, 'preview_offset_y', 0)
            actual_paper_len_mm = total_len_mm + getattr(self, 'preview_extra_len_mm', 0)
        else:
            actual_paper_len_mm = total_len_mm

        actual_paper_len_mm = max(10, actual_paper_len_mm)

        target_w_px = int(80.0 * user_dpi / 25.4)
        target_h_px = int(actual_paper_len_mm * user_dpi / 25.4)

        SCALE = 2.0
        unrotated_img = QImage(int(target_h_px * SCALE), int(target_w_px * SCALE), QImage.Format.Format_RGB32)
        unrotated_img.fill(QColor("white"))

        painter = QPainter(unrotated_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.scale(SCALE, SCALE)

        self.draw_label_content_at(painter, offset_x, offset_y, row_data)
        painter.end()

        transform = QTransform().rotate(90)
        rotated_img = unrotated_img.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        scaled_img = rotated_img.scaled(target_w_px, target_h_px, 
                                        Qt.AspectRatioMode.IgnoreAspectRatio, 
                                        Qt.TransformationMode.SmoothTransformation)

        final_paper_img = scaled_img.convertToFormat(QImage.Format.Format_Grayscale8)
        try:
            import numpy as np
            ptr = final_paper_img.bits()
            ptr.setsize(final_paper_img.sizeInBytes())
            arr = np.frombuffer(ptr, np.uint8).reshape((final_paper_img.height(), final_paper_img.bytesPerLine()))
            w = final_paper_img.width()
            arr[:, :w] = np.where(arr[:, :w] < 200, 0, 255)
        except Exception as e:
            print(f"이진화 처리 예외: {e}")

        if draw_guide:
            guide_img = final_paper_img.convertToFormat(QImage.Format.Format_RGB32)
            painter_paper = QPainter(guide_img)
            pen_guide = QPen(QColor("#D32F2F"), 2, Qt.PenStyle.DashLine)
            painter_paper.setPen(pen_guide)
            painter_paper.drawRect(0, 0, guide_img.width() - 1, guide_img.height() - 1)
            painter_paper.end()
            return guide_img

        return final_paper_img

    def update_preview(self):
        if not hasattr(self, 'lbl_preview_canvas'): return
            
        test_row = self.get_current_test_row_data() if hasattr(self, 'get_current_test_row_data') else None
        paper_img = self.generate_printed_page_image(test_row, draw_guide=True)
        
        display_w = 320
        scaled_img = paper_img.scaledToWidth(display_w, Qt.TransformationMode.SmoothTransformation)
        
        pixmap = QPixmap.fromImage(scaled_img)
        self.lbl_preview_canvas.setPixmap(pixmap)
        self.lbl_preview_canvas.setFixedSize(pixmap.width(), pixmap.height())

    def draw_label_content_at(self, painter, start_x, start_y, row_data=None):
        f_fam = self.combo_font.currentFont().family() or "Malgun Gothic"
        user_dpi = self.spin_dpi.value() if hasattr(self, 'spin_dpi') else 203

        def make_font(pt_size, weight):
            font = QFont(f_fam)
            font.setWeight(weight)
            px_size = max(1, int(pt_size * 96.0 / 72.0))
            font.setPixelSize(px_size)
            return font

        f_huge = make_font(self.spin_huge.value(), QFont.Weight.Black)
        f_large = make_font(self.spin_large.value(), QFont.Weight.Black)
        f_norm = make_font(self.spin_norm.value(), QFont.Weight.Bold)

        if row_data is not None:
            num_val = str(row_data.get('순번', '1')).split('.')[0]
            info_text = str(row_data.get('내용', '')).strip() or "기적1차 1"
            copy_val = str(row_data.get('권수', '1')).split('.')[0]
            copy_text = str(row_data.get('권수_표시', f"1-{copy_val}")).replace('(', '').replace(')', '')
            
            c_str = str(row_data.get('거래처', '')).strip()
            d_str = str(row_data.get('납품처', '')).strip()
            
            if c_str and d_str:
                vendor_text = f"{c_str}-\n{d_str}"
                vendor_first_line = f"{c_str}-"
            elif c_str:
                vendor_text = f"{c_str}-"
                vendor_first_line = f"{c_str}-"
            else:
                vendor_text = d_str
                vendor_first_line = d_str
                
            title_text = str(row_data.get('도서명', '도서명 없음')).strip()
            
            if hasattr(self, 'cb_isbn_print') and self.cb_isbn_print.isChecked():
                title_text += f"\n[{row_data.get('ISBN_Clean', '')}]"
                
            try: price_text = f"{int(float(row_data.get('정가', 0))):,} 원"
            except: price_text = str(row_data.get('정가', '0'))
        else:
            num_val = "1"
            info_text = "기적1차 1"
            copy_text = "1-1"
            vendor_text = "하늘지음-\n화도4차"
            vendor_first_line = "하늘지음-"
            title_text = "111년 후 이 자리에는 커다란 삼나무가 자랄 거야 (초판 한정 부록 포함 스페셜 에디션)"
            price_text = "16,800 원"

        painter.setPen(QColor("black"))
        
        max_paper_w_px = int(76.0 * user_dpi / 25.4)
        box_width = max(100, max_paper_w_px - start_x)

        fm_large = QFontMetrics(f_large)
        vendor_line_width = fm_large.horizontalAdvance(vendor_first_line)
        title_box_width = max(vendor_line_width, 100)

        def draw_wrapped_text(p, x, y, width, text, font, max_lines=99, elide=False):
            p.setFont(font)
            fm = p.fontMetrics()
            
            words = text.split('\n')
            lines = []
            for w in words:
                line_buf = ""
                for char in w:
                    if fm.horizontalAdvance(line_buf + char) <= width:
                        line_buf += char
                    else:
                        if line_buf: lines.append(line_buf)
                        line_buf = char
                if line_buf: lines.append(line_buf)

            if len(lines) > max_lines:
                lines = lines[:max_lines]
                if elide and lines:
                    last_l = lines[-1]
                    if len(last_l) > 3:
                        lines[-1] = last_l[:-2] + "..."
                    else:
                        lines[-1] = last_l + "..."

            draw_y = y
            for line in lines:
                p.drawText(x, draw_y + fm.ascent(), line)
                draw_y += fm.lineSpacing()

            return draw_y - y

        curr_y = start_y

        h1 = draw_wrapped_text(painter, start_x, curr_y, box_width, num_val, f_huge, max_lines=1)
        curr_y += h1 + 6

        h2 = draw_wrapped_text(painter, start_x, curr_y, box_width, info_text, f_large, max_lines=1)
        curr_y += h2 + 4

        h3 = draw_wrapped_text(painter, start_x, curr_y, box_width, copy_text, f_large, max_lines=1)
        curr_y += h3 + 4

        h4 = draw_wrapped_text(painter, start_x, curr_y, box_width, vendor_text, f_large, max_lines=2)
        curr_y += h4 + 6

        h5 = draw_wrapped_text(painter, start_x, curr_y, title_box_width, title_text, f_norm, max_lines=3, elide=True)
        curr_y += h5 + 4

        draw_wrapped_text(painter, start_x, curr_y, box_width, price_text, f_norm, max_lines=1)

    def trigger_physical_print_for_row(self, row_data=None, silent=False):
        from PyQt6.QtCore import QMarginsF
        from PyQt6.QtGui import QPageLayout

        target_printer = self.target_printer_name
        if not target_printer:
            err_msg = "선택된 라벨 프린터가 없습니다."
            self.log(f"인쇄 오류: {err_msg}", is_error=True)
            if not silent:
                QMessageBox.warning(self, "인쇄 오류", f"{err_msg}\n[6. 라벨 설정] 탭에서 프린터를 지정해주세요.")
            return

        try:
            user_dpi = self.spin_dpi.value() if hasattr(self, 'spin_dpi') else 203

            printer = QPrinter(QPrinter.PrinterMode.PrinterResolution)
            printer.setPrinterName(target_printer)
            printer.setResolution(user_dpi)
            printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)

            total_len_mm = self.sliders["라벨 총 출력 길이"].value() if "라벨 총 출력 길이" in self.sliders else 80
            feed_m_mm = self.sliders["출력 시작 여백"].value() if "출력 시작 여백" in self.sliders else 0
            side_m_mm = self.sliders["가로 위치"].value() if "가로 위치" in self.sliders else 0

            page_size_mm = QSizeF(80.0, float(total_len_mm))
            printer.setPageSize(QPageSize(page_size_mm, QPageSize.Unit.Millimeter))

            painter = QPainter()
            if not painter.begin(printer):
                err_msg = f"프린터 '{target_printer}'에 연결할 수 없습니다."
                self.log(f"인쇄 오류: {err_msg}", is_error=True)
                if not silent:
                    QMessageBox.warning(self, "인쇄 오류", err_msg)
                return

            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            base_mm_to_px = lambda mm: int(mm * user_dpi / 25.4)
            offset_x = base_mm_to_px(feed_m_mm)
            offset_y = base_mm_to_px(side_m_mm)

            paper_w_px = base_mm_to_px(80.0)
            painter.translate(paper_w_px, 0)
            painter.rotate(90)

            self.draw_label_content_at(painter, offset_x, offset_y, row_data)
            painter.end()

            if row_data is not None:
                doc_title = str(row_data.get('도서명', '테스트 페이지'))
            else:
                doc_title = '테스트 페이지'

            self.log(f"🖨️ 라벨 인쇄 완료: {doc_title} (프린터: {target_printer})")

        except Exception as e:
            self.log(f"인쇄 중 시스템 예외 발생: {e}", is_error=True)
            if not silent:
                QMessageBox.critical(self, "인쇄 오류", f"인쇄 처리 중 오류가 발생했습니다:\n{e}")

    def save_template(self):
        selected_printer = self.combo_printer_list.currentData() or self.combo_printer_list.currentText()
        self.target_printer_name = selected_printer

        data = { 
            "target_printer": selected_printer,
            "font_family": self.combo_font.currentFont().family() or "Malgun Gothic", 
            "left": self.sliders["출력 시작 여백"].value(), 
            "top": self.sliders["가로 위치"].value(), 
            "length": self.sliders["라벨 총 출력 길이"].value(), 
            "item_space": self.sliders["항목 간 줄간격"].value(),
            "line_space": self.sliders["긴 글 줄바꿈 간격"].value(),
            "indent": self.sliders["줄바꿈 들여쓰기 여백"].value(),
            "dpi": self.spin_dpi.value(),
            "size_huge": self.spin_huge.value(), 
            "size_large": self.spin_large.value(), 
            "size_norm": self.spin_norm.value() 
        }
        try:
            with open(TEMPLATE_FILE, "w", encoding="utf-8") as f: 
                json.dump(data, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "저장 완료", f"라벨 템플릿 및 프린터 설정이 저장되었습니다!\n(적용 프린터: {selected_printer})")
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"템플릿 저장 중 오류가 발생했습니다:\n{e}")

    def load_template(self):
        if os.path.exists(TEMPLATE_FILE):
            try:
                with open(TEMPLATE_FILE, "r", encoding="utf-8") as f: 
                    data = json.load(f)
                self.target_printer_name = data.get("target_printer", self.target_printer_name)
                self.refresh_available_printers()
                font_name = data.get("font_family", "Malgun Gothic")
                self.combo_font.setCurrentFont(QFont(font_name, 12))
                if "출력 시작 여백" in self.sliders: self.sliders["출력 시작 여백"].setValue(data.get("left", 0))
                if "가로 위치" in self.sliders: self.sliders["가로 위치"].setValue(data.get("top", 0))
                if "라벨 총 출력 길이" in self.sliders: self.sliders["라벨 총 출력 길이"].setValue(data.get("length", 150))
                if "항목 간 줄간격" in self.sliders: self.sliders["항목 간 줄간격"].setValue(data.get("item_space", 2))
                if "긴 글 줄바꿈 간격" in self.sliders: self.sliders["긴 글 줄바꿈 간격"].setValue(data.get("line_space", 1))
                if "줄바꿈 들여쓰기 여백" in self.sliders: self.sliders["줄바꿈 들여쓰기 여백"].setValue(data.get("indent", 0))
                self.spin_dpi.setValue(data.get("dpi", 203))
                self.spin_huge.setValue(max(1, data.get("size_huge", 40)))
                self.spin_large.setValue(max(1, data.get("size_large", 30)))
                self.spin_norm.setValue(max(1, data.get("size_norm", 20)))
            except Exception as e:
                print(f"템플릿 로드 실패: {e}")

    def render_inspect_table(self, table_widget, df_data, append_sum=False):
        table_widget.setUpdatesEnabled(False)  # ★ 대량 렌더링 중 화면 다시 그리기 억제 (속도 대폭 향상)
        try:
            display_cols = ['상태', '권수', 'ISBN_Clean', '도서명', '출판사', '정가', '비고', '납품처']
            if not df_data.empty and '비고' not in df_data.columns:
                df_data = df_data.copy()
                df_data['비고'] = ""
                
            headers = ["구분", "수량", "ISBN", "도서명", "출판사", "정가", "비고", "납품처"]
            row_count = len(df_data)
            if append_sum and row_count > 0: row_count += 2
                
            table_widget.clear(); table_widget.setRowCount(row_count); table_widget.setColumnCount(len(headers))
            table_widget.setHorizontalHeaderLabels(headers)
            
            total_qty = 0; total_price = 0
            
            for r, (orig_idx, row) in enumerate(df_data.iterrows()):
                table_widget.setVerticalHeaderItem(r, QTableWidgetItem(str(r + 1)))
                for c_idx, col_name in enumerate(display_cols):
                    val = str(row.get(col_name, ''))
                    if val.lower() == 'nan': display_val = ""
                    elif col_name == '상태': display_val = val
                    elif col_name in ['순번', '권수']:
                        try: 
                            num_val = int(float(val))
                            display_val = str(num_val)
                            if col_name == '권수': total_qty += num_val
                        except: display_val = val
                    elif col_name == '정가':
                        try: 
                            price_val = int(float(val))
                            display_val = f"{price_val:,}"
                            total_price += price_val
                        except: display_val = val
                    else: display_val = val

                    item = QTableWidgetItem(display_val)
                    item.setData(Qt.ItemDataRole.UserRole, orig_idx)
                    
                    if col_name == '상태':
                        if display_val == '입고': 
                            item.setForeground(QColor("blue"))
                            item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
                        else: 
                            item.setForeground(QColor("red"))
                    table_widget.setItem(r, c_idx, item)
                    
            if append_sum and len(df_data) > 0:
                empty_r = len(df_data); sum_r = len(df_data) + 1
                table_widget.setVerticalHeaderItem(empty_r, QTableWidgetItem(""))
                table_widget.setVerticalHeaderItem(sum_r, QTableWidgetItem("총계"))
                
                for c_idx, col_name in enumerate(display_cols):
                    table_widget.setItem(empty_r, c_idx, QTableWidgetItem(""))
                    val_sum = ""
                    if col_name == '도서명': val_sum = "합계"
                    elif col_name == '권수': val_sum = str(total_qty)
                    elif col_name == '정가': val_sum = f"{total_price:,}"
                        
                    item_sum = QTableWidgetItem(val_sum)
                    item_sum.setFont(QFont("Arial", 10, QFont.Weight.Bold)); item_sum.setBackground(QColor("#f0f0f0")) 
                    table_widget.setItem(sum_r, c_idx, item_sum)

            # ★ [최적화] CPU를 갉아먹는 resizeColumnsToContents 대신 최적 고정 폭 지정
            header = table_widget.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            table_widget.setColumnWidth(0, 55)   # 구분
            table_widget.setColumnWidth(1, 45)   # 수량
            table_widget.setColumnWidth(2, 125)  # ISBN
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch) # 도서명 자동 확장
            table_widget.setColumnWidth(4, 110)  # 출판사
            table_widget.setColumnWidth(5, 75)   # 정가
            table_widget.setColumnWidth(6, 85)   # 비고
            table_widget.setColumnWidth(7, 100)  # 납품처
        finally:
            table_widget.setUpdatesEnabled(True)  # 화면 렌더링 즉시 재개

    def refresh_all_tables(self):
        if hasattr(self, 'client_completer'):
            self.refresh_client_completer()

        if hasattr(self, 'refresh_test_data_combo'):
            self.refresh_test_data_combo()

        if self.df.empty: 
            self.table_summary.clear(); self.table_summary.setRowCount(0)
            self.table_list.clear(); self.table_list.setRowCount(0)
            self.combo_list_vendor.clear()
            self.lbl_grand_total.setText("총 합계 | 대기 중...")
            return

        # ★ 1. 갱신 전 콤보박스 선택값, 스크롤 위치, 선택된 도서 행 기억
        current_vendor = self.combo_list_vendor.currentText()
        list_scroll = self.table_list.verticalScrollBar().value()
        summary_scroll = self.table_summary.verticalScrollBar().value()
        
        selected_list_orig_idx = None
        curr_row = self.table_list.currentRow()
        if curr_row >= 0:
            item = self.table_list.item(curr_row, 0)
            if item:
                selected_list_orig_idx = item.data(Qt.ItemDataRole.UserRole)

        # 콤보박스 갱신 후 이전 선택값 복원
        self.combo_list_vendor.blockSignals(True)
        self.combo_list_vendor.clear()
        self.combo_list_vendor.addItem("전체")
        vendors = [v for v in self.df['납품처'].unique() if v and v != '납품처']
        self.combo_list_vendor.addItems(vendors)
        
        if current_vendor in vendors or current_vendor == "전체":
            self.combo_list_vendor.setCurrentText(current_vendor)
        self.combo_list_vendor.blockSignals(False)

        # 목록 탭 표 갱신
        self.search_list()

        # ★ 2. 스크롤 위치 및 선택된 행 복원
        self.table_list.verticalScrollBar().setValue(list_scroll)
        if selected_list_orig_idx is not None:
            for r in range(self.table_list.rowCount()):
                item = self.table_list.item(r, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_list_orig_idx:
                    self.table_list.selectRow(r)
                    break

        # 집계 탭 렌더링
        batch_cols = ['거래처', '납품처']
        unique_batches = self.df[batch_cols].drop_duplicates().reset_index(drop=True)
        
        self.table_summary.setRowCount(len(unique_batches))
        t_all, d_all, p_all, price_all = 0, 0, 0, 0

        for i, row in unique_batches.iterrows():
            c, v = str(row['거래처']), str(row['납품처'])
            
            mask = (self.df['거래처'] == c) & (self.df['납품처'] == v)
            v_df = self.df[mask]
            
            v_t = len(v_df); v_d = len(v_df[v_df['상태'] == '입고']); v_p = v_t - v_d
            try: v_pr = v_df['정가'].astype(float).sum()
            except: v_pr = 0
            
            unique_contents = [cnt for cnt in v_df['내용'].dropna().unique() if str(cnt).strip() and str(cnt).strip() != '내용']
            if len(unique_contents) == 1:
                cnt_tag = f" ({unique_contents[0]})"
            elif len(unique_contents) > 1:
                cnt_tag = f" ({unique_contents[0]} 외 {len(unique_contents)-1}종)"
            else:
                cnt_tag = ""
                
            disp_vendor = f"{v}{cnt_tag}"
            
            item_vendor = QTableWidgetItem(disp_vendor)
            item_vendor.setData(Qt.ItemDataRole.UserRole, (c, v))
            
            # 입고율 계산 (100%: 초록, 진행 중: 노랑/호박색, 0%: 회색)
            rate = (v_d / v_t * 100.0) if v_t > 0 else 0.0
            item_rate = QTableWidgetItem(f"{rate:.1f}%")
            item_rate.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            if rate >= 100.0:
                item_rate.setForeground(QColor("#2E7D32"))  # 100% 완료: 선명한 초록색
            elif rate > 0.0:
                item_rate.setForeground(QColor("#E65100"))  # 진행 중: 눈에 잘 띄는 진한 노랑(호박색)
            else:
                item_rate.setForeground(QColor("#9E9E9E"))  # 0%: 차분한 회색

            self.table_summary.setItem(i, 0, item_vendor)
            self.table_summary.setItem(i, 1, QTableWidgetItem(f"{v_t:,}"))
            self.table_summary.setItem(i, 2, QTableWidgetItem(f"{v_d:,}"))
            self.table_summary.setItem(i, 3, QTableWidgetItem(f"{v_p:,}"))
            self.table_summary.setItem(i, 4, item_rate)
            self.table_summary.setItem(i, 5, QTableWidgetItem(f"{int(v_pr):,}"))
            t_all += v_t; d_all += v_d; p_all += v_p; price_all += v_pr

        self.table_summary.verticalScrollBar().setValue(summary_scroll)
        total_rate = (d_all / t_all * 100.0) if t_all > 0 else 0.0
        self.lbl_grand_total.setText(f"총 합계 | 전체: {t_all:,} 권 / 입고: {d_all:,} 권 ({total_rate:.1f}%) / 미입고: {p_all:,} 권 / 총액: {int(price_all):,} 원")

    def render_table(self, table_widget, df_data, show_time=False, append_sum=True):
        table_widget.setUpdatesEnabled(False)  # ★ 대량 데이터 렌더링 중 GUI 리페인트 차단
        try:
            if show_time: 
                display_cols = ['입고일시', '내용', '상태', '순번', '도서명', '저자', '출판사', '정가', '권수', 'ISBN_Clean']
            else: 
                display_cols = ['내용', '상태', '순번', '도서명', '저자', '출판사', '정가', '권수', 'ISBN_Clean']
            
            actual_cols = [c for c in display_cols if c in df_data.columns]
            headers = [c.replace('ISBN_Clean', 'ISBN') for c in actual_cols]
            row_count = len(df_data)
            if append_sum and row_count > 0: 
                row_count += 2
                
            table_widget.clear()
            table_widget.setRowCount(row_count)
            table_widget.setColumnCount(len(actual_cols))
            table_widget.setHorizontalHeaderLabels(headers)
            
            total_qty = 0
            for r, (orig_idx, row) in enumerate(df_data.iterrows()):
                table_widget.setVerticalHeaderItem(r, QTableWidgetItem(str(r + 1)))
                for c_idx, col_name in enumerate(actual_cols):
                    val = str(row.get(col_name, ''))
                    
                    if col_name == '내용':
                        if not val or val.lower() == 'nan':
                            val = str(row.get('납품처', ''))
                            
                    if val.lower() == 'nan': 
                        display_val = ""
                    elif col_name == '상태': 
                        display_val = val
                    elif col_name in ['순번', '권수']:
                        try: 
                            num_val = int(float(val))
                            display_val = str(num_val)
                            if col_name == '권수': 
                                total_qty += num_val
                        except: 
                            display_val = val
                    elif col_name == '정가':
                        try: 
                            display_val = f"{int(float(val)):,}"
                        except: 
                            display_val = val
                    else: 
                        display_val = val

                    item = QTableWidgetItem(display_val)
                    item.setData(Qt.ItemDataRole.UserRole, orig_idx)
                    
                    if col_name == '상태':
                        if display_val == '입고': 
                            item.setForeground(QColor("blue"))
                            item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
                        else: 
                            item.setForeground(QColor("red"))
                    table_widget.setItem(r, c_idx, item)
                    
            if append_sum and len(df_data) > 0:
                empty_r = len(df_data)
                sum_r = len(df_data) + 1
                table_widget.setVerticalHeaderItem(empty_r, QTableWidgetItem(""))
                table_widget.setVerticalHeaderItem(sum_r, QTableWidgetItem("총계"))
                
                for c_idx, col_name in enumerate(actual_cols):
                    table_widget.setItem(empty_r, c_idx, QTableWidgetItem(""))
                    val_sum = ""
                    if col_name == '도서명': 
                        val_sum = "합계"
                    elif col_name == '권수': 
                        val_sum = str(total_qty)
                    item_sum = QTableWidgetItem(val_sum)
                    item_sum.setFont(QFont("Arial", 10, QFont.Weight.Bold))
                    item_sum.setBackground(QColor("#f0f0f0")) 
                    table_widget.setItem(sum_r, c_idx, item_sum)

            # ★ [최적화] 대량 연산 대신 도서명 자동 확장 및 기본 너비 설정
            header = table_widget.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            for c_idx, col_name in enumerate(actual_cols):
                if col_name == '도서명':
                    header.setSectionResizeMode(c_idx, QHeaderView.ResizeMode.Stretch)
                elif col_name in ['순번', '수량', '권수', '상태']:
                    table_widget.setColumnWidth(c_idx, 60)
                elif col_name == 'ISBN_Clean':
                    table_widget.setColumnWidth(c_idx, 130)
                elif col_name in ['정가', '출판사']:
                    table_widget.setColumnWidth(c_idx, 90)
                elif col_name == '입고일시':
                    table_widget.setColumnWidth(c_idx, 140)
        finally:
            table_widget.setUpdatesEnabled(True)  # 화면 렌더링 즉시 재개

    def on_book_double_clicked(self, row, col):
        sender_table = self.sender(); item = sender_table.item(row, col)
        if not item: return
        orig_idx = item.data(Qt.ItemDataRole.UserRole)
        if orig_idx is None or orig_idx not in self.df.index: return 
        
        row_data = self.df.loc[orig_idx]
        old_status = str(row_data.get('상태', '미입고'))
        dialog = BookEditDialog(row_data, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data(); new_status = new_data['상태']
            for k, v in new_data.items(): self.df.at[orig_idx, k] = v
                
            if old_status != '입고' and new_status == '입고': self.df.at[orig_idx, '입고일시'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif new_status == '미입고': self.df.at[orig_idx, '입고일시'] = "" 
                
            self.save_database(); self.refresh_all_tables()
            self.refresh_inspect_tab()
            if hasattr(self, 'search_history'): self.search_history()
        self.ensure_barcode_focus()

    def on_tab_changed(self, index):
        """탭 전환 시 시각적 프레임 드롭을 방지하기 위해 탭이 먼저 부드럽게 넘어간 뒤 해당 탭만 지연 로딩"""
        QTimer.singleShot(10, lambda: self._lazy_load_tab(index))

    def _lazy_load_tab(self, index):
        if index == 0:    # 1. 등록 탭 -> 거래처 자동완성만 가볍게 갱신
            self.refresh_client_completer()
        elif index == 1:  # 2. 검수 탭 -> 검수 대상 및 바코드 포커스
            self.refresh_inspect_tab()
            self.ensure_barcode_focus()
        elif index == 2:  # 3. 목록 탭 -> 목록 표만 검색/표시
            self.search_list()
        elif index == 4:  # 5. 집계 탭 -> 집계 표만 계산/표시
            self.render_summary_tab()
        elif index == 5:  # 6. 라벨 설정 탭 -> 테스트 도서 콤보만 갱신
            self.refresh_test_data_combo()

    def render_summary_tab(self):
        """[독립 렌더링] 5. 집계 탭만 빠르게 계산하여 화면 깜빡임 없이 출력"""
        if self.df.empty:
            self.table_summary.clear()
            self.table_summary.setRowCount(0)
            self.lbl_grand_total.setText("총 합계 | 대기 중...")
            return

        self.table_summary.setUpdatesEnabled(False)
        try:
            summary_scroll = self.table_summary.verticalScrollBar().value()
            batch_cols = ['거래처', '납품처']
            unique_batches = self.df[batch_cols].drop_duplicates().reset_index(drop=True)
            
            self.table_summary.setRowCount(len(unique_batches))
            t_all, d_all, p_all, price_all = 0, 0, 0, 0

            for i, row in unique_batches.iterrows():
                c, v = str(row['거래처']), str(row['납품처'])
                mask = (self.df['거래처'] == c) & (self.df['납품처'] == v)
                v_df = self.df[mask]
                
                v_t = len(v_df)
                v_d = len(v_df[v_df['상태'] == '입고'])
                v_p = v_t - v_d
                try: v_pr = v_df['정가'].astype(float).sum()
                except: v_pr = 0
                
                unique_contents = [cnt for cnt in v_df['내용'].dropna().unique() if str(cnt).strip() and str(cnt).strip() != '내용']
                if len(unique_contents) == 1:
                    cnt_tag = f" ({unique_contents[0]})"
                elif len(unique_contents) > 1:
                    cnt_tag = f" ({unique_contents[0]} 외 {len(unique_contents)-1}종)"
                else:
                    cnt_tag = ""
                    
                disp_vendor = f"{v}{cnt_tag}"
                item_vendor = QTableWidgetItem(disp_vendor)
                item_vendor.setData(Qt.ItemDataRole.UserRole, (c, v))
                
                rate = (v_d / v_t * 100.0) if v_t > 0 else 0.0
                item_rate = QTableWidgetItem(f"{rate:.1f}%")
                item_rate.setFont(QFont("Arial", 10, QFont.Weight.Bold))
                if rate >= 100.0:
                    item_rate.setForeground(QColor("#2E7D32"))
                elif rate > 0.0:
                    item_rate.setForeground(QColor("#E65100"))
                else:
                    item_rate.setForeground(QColor("#9E9E9E"))

                self.table_summary.setItem(i, 0, item_vendor)
                self.table_summary.setItem(i, 1, QTableWidgetItem(f"{v_t:,}"))
                self.table_summary.setItem(i, 2, QTableWidgetItem(f"{v_d:,}"))
                self.table_summary.setItem(i, 3, QTableWidgetItem(f"{v_p:,}"))
                self.table_summary.setItem(i, 4, item_rate)
                self.table_summary.setItem(i, 5, QTableWidgetItem(f"{int(v_pr):,}"))
                t_all += v_t; d_all += v_d; p_all += v_p; price_all += v_pr

            self.table_summary.verticalScrollBar().setValue(summary_scroll)
            total_rate = (d_all / t_all * 100.0) if t_all > 0 else 0.0
            self.lbl_grand_total.setText(f"총 합계 | 전체: {t_all:,} 권 / 입고: {d_all:,} 권 ({total_rate:.1f}%) / 미입고: {p_all:,} 권 / 총액: {int(price_all):,} 원")
        finally:
            self.table_summary.setUpdatesEnabled(True)
class QuickNewBookDialog(QDialog):
    """[매장 신규 도서] 뒤표지 실물 정가 확인용 1초 간이 등록 다이얼로그"""
    def __init__(self, isbn, default_vendor, parent=None):
        super().__init__(parent)
        self.isbn = isbn
        self.vendor = default_vendor
        self.setWindowTitle("신규 도서 실물 정가 확인 (엔터 누르면 즉시 입고)")
        self.resize(420, 240)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        lbl_isbn = QLabel(f"<b>ISBN:</b> {self.isbn}  |  <b>매입처:</b> {self.vendor}")
        lbl_isbn.setStyleSheet("font-size: 13px; color: #1565C0; padding: 5px; background: #E3F2FD; border-radius: 4px;")
        layout.addWidget(lbl_isbn)

        self.line_price = QLineEdit()
        self.line_price.setPlaceholderText("책 뒤표지 정가 숫자만 입력 (예: 15000)")
        self.line_price.setStyleSheet("font-size: 16px; font-weight: bold; padding: 6px; border: 2px solid #FF9800; border-radius: 4px;")
        
        self.line_title = QLineEdit()
        self.line_title.setPlaceholderText("도서명 입력 (생략 가능)")
        self.line_title.setStyleSheet("font-size: 13px; padding: 5px;")

        self.line_author = QLineEdit()
        self.line_author.setPlaceholderText("저자 (생략 가능)")
        self.line_author.setStyleSheet("font-size: 13px; padding: 5px;")

        self.line_pub = QLineEdit()
        self.line_pub.setPlaceholderText("출판사 (생략 가능)")
        self.line_pub.setStyleSheet("font-size: 13px; padding: 5px;")

        form.addRow("▶ 정 가 (필수):", self.line_price)
        form.addRow("▶ 도 서 명:", self.line_title)
        form.addRow("▶ 저 자:", self.line_author)
        form.addRow("▶ 출 판 사:", self.line_pub)
        layout.addLayout(form)

        btn_ok = QPushButton("입고 완료 (Enter)")
        btn_ok.setStyleSheet("font-size: 15px; font-weight: bold; background-color: #2E7D32; color: white; padding: 10px; border-radius: 4px;")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)

        # 정가 입력창에 즉시 포커스 설정
        self.line_price.setFocus()
        self.line_price.returnPressed.connect(self.accept)

    def get_book_data(self):
        price_val = self.line_price.text().strip().replace(',', '')
        try: price_int = int(float(price_val))
        except: price_int = 0

        title_val = self.line_title.text().strip() or f"신규도서({self.isbn[-4:]})"
        return {
            '도서명': title_val,
            '정가': str(price_int),
            '저자': self.line_author.text().strip(),
            '출판사': self.line_pub.text().strip()
        }
class StorePermissionDialog(QDialog):
    """[총괄관리자 전용] 매장 입고 모드를 허용할 회원사 직관적 체크박스 설정창"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🏪 매장 재고 입고 모드 권한 관리")
        self.resize(380, 420)
        self.checkboxes = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lbl_desc = QLabel("매장 재고 입고 모드를 활성화할 회원사를 체크하세요.\n(체크된 업체만 검수 탭에 매장 모드 버튼이 노출됩니다)")
        lbl_desc.setStyleSheet("font-size: 13px; font-weight: bold; color: #1565C0; background-color: #E3F2FD; padding: 10px; border-radius: 6px;")
        layout.addWidget(lbl_desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.form_layout = QVBoxLayout(container)
        self.form_layout.setSpacing(8)

        # 1. DB에서 등록된 전체 회원사 목록 가져오기
        companies = []
        conn = get_db_connection()
        allowed_list = []
        if conn:
            try:
                cursor = conn.cursor()
                # 설정 테이블 자동 생성
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        setting_key VARCHAR(50) PRIMARY KEY,
                        setting_val TEXT
                    )
                """)
                # 현재 허용된 업체 목록 조회
                cursor.execute("SELECT setting_val FROM app_settings WHERE setting_key='store_allowed_companies'")
                row = cursor.fetchone()
                if row and row['setting_val']:
                    allowed_list = [c.strip() for c in row['setting_val'].split(',') if c.strip()]
                else:
                    allowed_list = ['COMP_A']

                # 전체 회원사 목록 조회
                cursor.execute("SELECT DISTINCT company_id, user_name FROM users WHERE company_id != 'ALL' AND company_id != ''")
                companies = cursor.fetchall()
                conn.close()
            except Exception as e:
                print(f"권한 목록 조회 오류: {e}")

        # 2. 업체별 체크박스 생성
        for comp in companies:
            cid = comp['company_id']
            cname = comp['user_name']
            cb = QCheckBox(f"{cname} ({cid})")
            cb.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
            if cid in allowed_list:
                cb.setChecked(True)
            self.checkboxes[cid] = cb
            self.form_layout.addWidget(cb)

        self.form_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        btn_save = QPushButton("설정 저장 및 즉시 반영")
        btn_save.setStyleSheet("font-size: 15px; font-weight: bold; background-color: #2E7D32; color: white; padding: 12px; border-radius: 6px;")
        btn_save.clicked.connect(self.save_permissions)
        layout.addWidget(btn_save)

    def save_permissions(self):
        selected = [cid for cid, cb in self.checkboxes.items() if cb.isChecked()]
        val_str = ",".join(selected)

        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                sql = "REPLACE INTO app_settings (setting_key, setting_val) VALUES ('store_allowed_companies', %s)"
                cursor.execute(sql, (val_str,))
                conn.commit()
                conn.close()
                QMessageBox.information(self, "저장 완료", f"총 {len(selected)}개 회원사에 매장 기능 권한이 지정되었습니다.")
                self.accept()
                return
            except Exception as e:
                QMessageBox.critical(self, "저장 실패", f"DB 저장 중 오류 발생:\n{e}")
        else:
            QMessageBox.critical(self, "연결 실패", "중앙 DB 서버에 연결할 수 없습니다.")
