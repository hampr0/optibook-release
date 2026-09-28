from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QHeaderView, 
                             QMessageBox, QInputDialog, QLabel, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from db import get_db_connection


class UserApprovalDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("관리자 전용 회원 승인 및 계정 관리")
        self.resize(800, 480)
        
        layout = QVBoxLayout(self)
        
        # --- 1. 상단 필터 바 ---
        filter_layout = QHBoxLayout()
        lbl_filter = QLabel("회원 보기 구분:")
        lbl_filter.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["승인 대기 회원 (PENDING)", "승인 완료 회원 (APPROVED)", "전체 회원 보기 (ALL)"])
        self.combo_filter.setStyleSheet("padding: 5px 10px; font-size: 13px;")
        self.combo_filter.currentIndexChanged.connect(self.load_users)
        
        filter_layout.addWidget(lbl_filter)
        filter_layout.addWidget(self.combo_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # --- 2. 회원 목록 테이블 ---
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["아이디", "이름/서점명", "회사코드", "신청일시", "상태"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)
        
        # --- 3. 하단 동작 버튼 ---
        btn_layout = QHBoxLayout()
        
        self.btn_approve = QPushButton("✅ 선택 계정 승인/코드수정")
        self.btn_approve.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 10px; font-size: 13px; border-radius: 4px;")
        self.btn_approve.clicked.connect(self.approve_user)
        
        self.btn_delete = QPushButton("🗑️ 선택 회원 영구 삭제")
        self.btn_delete.setStyleSheet("background-color: #D32F2F; color: white; font-weight: bold; padding: 10px; font-size: 13px; border-radius: 4px;")
        self.btn_delete.clicked.connect(self.delete_selected_user)

        self.btn_refresh = QPushButton("새로고침")
        self.btn_refresh.setStyleSheet("padding: 10px 15px; font-size: 13px;")
        self.btn_refresh.clicked.connect(self.load_users)
        
        btn_layout.addWidget(self.btn_approve)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_refresh)
        layout.addLayout(btn_layout)
        
        self.load_users()
        
    def load_users(self):
        filter_idx = self.combo_filter.currentIndex()
        if filter_idx == 0:
            where_sql = "WHERE status='PENDING'"
        elif filter_idx == 1:
            where_sql = "WHERE status='APPROVED'"
        else:
            where_sql = ""

        try:
            conn = get_db_connection()
            if not conn: 
                return
            cursor = conn.cursor()
            cursor.execute(f"SELECT user_id, user_name, company_id, created_at, status FROM users {where_sql} ORDER BY created_at DESC")
            users = cursor.fetchall()
            conn.close()
            
            self.table.setRowCount(len(users))
            for r, u in enumerate(users):
                self.table.setItem(r, 0, QTableWidgetItem(str(u['user_id'])))
                self.table.setItem(r, 1, QTableWidgetItem(str(u['user_name'])))
                self.table.setItem(r, 2, QTableWidgetItem(str(u.get('company_id', '') or '-')))
                self.table.setItem(r, 3, QTableWidgetItem(str(u['created_at'])))
                
                status_str = u.get('status', '')
                if status_str == 'PENDING':
                    status_item = QTableWidgetItem("승인대기")
                    status_item.setForeground(QColor("#E65100"))
                elif status_str == 'APPROVED':
                    status_item = QTableWidgetItem("승인완료")
                    status_item.setForeground(QColor("#2E7D32"))
                else:
                    status_item = QTableWidgetItem(str(status_str))
                
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, 4, status_item)
        except Exception as e:
            print(f"사용자 목록 로드 오류: {e}")
            
    def approve_user(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "경고", "승인할 계정을 선택하세요.")
            return
            
        user_id = self.table.item(row, 0).text()
        user_name = self.table.item(row, 1).text()
        current_comp = self.table.item(row, 2).text()
        default_val = current_comp if current_comp != '-' else "COMP_B"
        
        comp_code, ok = QInputDialog.getText(
            self, "회사 코드 부여", 
            f"[{user_name} ({user_id})] 계정에 부여할 회사 식별 코드를 입력하세요:\n(예: COMP_A, COMP_B 등)",
            text=default_val
        )
        if not ok or not comp_code.strip():
            return
            
        comp_code = comp_code.strip().upper()
        
        try:
            conn = get_db_connection()
            if not conn:
                QMessageBox.critical(self, "연결 실패", "DB에 연결할 수 없습니다.")
                return
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET status='APPROVED', company_id=%s WHERE user_id=%s", (comp_code, user_id))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "완료", f"[{user_id}] 계정이 승인/수정되었습니다. (회사코드: {comp_code})")
            self.load_users()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"승인 처리 중 오류:\n{e}")

    def delete_selected_user(self):
        """선택한 회원을 중앙 DB(users)에서 즉시 영구 삭제"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "선택 필요", "삭제할 계정을 테이블에서 먼저 클릭해 선택해주세요.")
            return

        user_id = self.table.item(row, 0).text().strip()
        user_name = self.table.item(row, 1).text().strip()

        # 총괄 마스터 계정 삭제 차단
        if user_id == 'ssbs_master':
            QMessageBox.critical(self, "삭제 불가", "총괄관리자 마스터 계정(ssbs_master)은 시스템 안전을 위해 삭제할 수 없습니다.")
            return

        reply = QMessageBox.question(
            self, 
            "회원 영구 삭제 확인", 
            f"정말 [{user_name} ({user_id})] 계정을 완전히 삭제하시겠습니까?\n삭제된 계정 정보는 복구할 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                conn = get_db_connection()
                if not conn:
                    QMessageBox.critical(self, "연결 실패", "DB 서버에 연결할 수 없습니다.")
                    return
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
                conn.commit()
                conn.close()

                QMessageBox.information(self, "삭제 완료", f"[{user_id}] 계정이 성공적으로 영구 삭제되었습니다.")
                self.load_users()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"회원 삭제 중 DB 오류 발생:\n{e}")


class ErrorLogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("관리자 전용 원격 시스템 오류 로그 리포트")
        self.resize(900, 520)
        
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["시간", "회원사", "사용자", "에러 메시지", "상세 추적(Traceback)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("로그 새로고침")
        btn_refresh.setStyleSheet("padding: 8px 15px; font-weight: bold;")
        btn_refresh.clicked.connect(self.load_error_logs)
        
        btn_clear = QPushButton("오류 로그 전체 비우기")
        btn_clear.setStyleSheet("background-color: #D32F2F; color: white; padding: 8px 15px; font-weight: bold;")
        btn_clear.clicked.connect(self.clear_logs)
        
        btn_close = QPushButton("닫기")
        btn_close.setStyleSheet("padding: 8px 15px;")
        btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(btn_refresh)
        btn_layout.addWidget(btn_clear)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        self.load_error_logs()
        
    def load_error_logs(self):
        try:
            conn = get_db_connection()
            if not conn: return
            cursor = conn.cursor()
            cursor.execute("SELECT error_time, company_id, user_id, error_msg, traceback FROM error_logs ORDER BY id DESC LIMIT 200")
            rows = cursor.fetchall()
            conn.close()
            
            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                self.table.setItem(r, 0, QTableWidgetItem(str(row['error_time'])))
                self.table.setItem(r, 1, QTableWidgetItem(str(row['company_id'])))
                self.table.setItem(r, 2, QTableWidgetItem(str(row['user_id'])))
                self.table.setItem(r, 3, QTableWidgetItem(str(row['error_msg'])))
                self.table.setItem(r, 4, QTableWidgetItem(str(row['traceback'])))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"오류 로그를 불러올 수 없습니다:\n{e}")
            
    def clear_logs(self):
        reply = QMessageBox.question(self, "확인", "서버의 모든 오류 로그 기록을 삭제하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                conn = get_db_connection()
                if not conn: return
                cursor = conn.cursor()
                cursor.execute("TRUNCATE TABLE error_logs")
                conn.commit()
                conn.close()
                self.load_error_logs()
                QMessageBox.information(self, "완료", "모든 오류 로그가 성공적으로 비워졌습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"로그 삭제 중 에러 발생:\n{e}")