import os
import json
import base64
import tempfile
from PyQt6.QtWidgets import (QDialog, QFormLayout, QLabel, QLineEdit, 
                             QPushButton, QMessageBox, QVBoxLayout, 
                             QHBoxLayout, QCheckBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor

from config import LOGIN_STATE_FILE, OFFLINE_AUTH_FILE
from db import get_db_connection


def get_custom_check_icon():
    """Qt 스타일시트와 100% 호환되는 선명한 화이트 체크마크(✓) 아이콘 동적 생성"""
    icon_path = os.path.join(tempfile.gettempdir(), "optibook_white_check.png").replace("\\", "/")
    if not os.path.exists(icon_path) or os.path.getsize(icon_path) == 0:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#FFFFFF"), 3.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        # 선명한 'V' 체크 그리기 (왼쪽 다리 -> 꺾임점 -> 오른쪽 다리)
        painter.drawLine(7, 16, 13, 22)
        painter.drawLine(13, 22, 25, 9)
        painter.end()
        
        pixmap.save(icon_path, "PNG")
    return icon_path


class SignUpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("신성미래서적-도서검수시스템 회원가입")
        self.resize(400, 320)
        self.setStyleSheet("background-color: #F8FAFC;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(16)
        
        lbl_title = QLabel("회원가입")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 800; color: #0F172A;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)
        
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)
        
        input_style = """
            QLineEdit {
                padding: 10px 12px;
                font-size: 14px;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                background-color: #FFFFFF;
            }
            QLineEdit:focus {
                border: 2px solid #2563EB;
            }
        """
        
        self.line_id = QLineEdit(); self.line_id.setPlaceholderText("사용할 아이디")
        self.line_pw = QLineEdit(); self.line_pw.setEchoMode(QLineEdit.EchoMode.Password); self.line_pw.setPlaceholderText("비밀번호")
        self.line_name = QLineEdit(); self.line_name.setPlaceholderText("담당자 성함 또는 서점/회원사명")
        
        for le in [self.line_id, self.line_pw, self.line_name]:
            le.setStyleSheet(input_style)
            form_layout.addWidget(le)
            
        layout.addLayout(form_layout)
        
        btn_submit = QPushButton("가입 신청하기")
        btn_submit.setStyleSheet("""
            QPushButton {
                background-color: #16A34A;
                color: white;
                font-weight: bold;
                padding: 12px;
                font-size: 15px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #15803D;
            }
        """)
        btn_submit.clicked.connect(self.process_signup)
        layout.addWidget(btn_submit)
        
    def process_signup(self):
        u_id = self.line_id.text().strip()
        u_pw = self.line_pw.text().strip()
        u_name = self.line_name.text().strip()
        
        if not u_id or not u_pw or not u_name:
            QMessageBox.warning(self, "경고", "모든 항목을 빠짐없이 입력해주세요.")
            return
            
        try:
            conn = get_db_connection()
            if not conn:
                QMessageBox.critical(self, "연결 실패", "클라우드 DB 서버에 접속할 수 없습니다.")
                return

            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE user_id=%s", (u_id,))
            if cursor.fetchone():
                QMessageBox.warning(self, "중복 오류", "이미 존재하거나 신청된 아이디입니다.")
                conn.close()
                return
                
            sql = "INSERT INTO users (user_id, user_pw, user_name, role, company_id, status) VALUES (%s, %s, %s, 'USER', '', 'PENDING')"
            cursor.execute(sql, (u_id, u_pw, u_name))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "신청 완료", "회원가입 신청이 완료되었습니다!\n관리자 승인 후 로그인이 가능합니다.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"회원가입 처리 중 오류 발생:\n{e}")


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("신성미래서적-도서검수시스템 로그인")
        self.resize(400, 420)
        self.setStyleSheet("background-color: #F8FAFC;")
        self.user_info = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 30, 32, 30)
        layout.setSpacing(16)
        
        # --- 1. 상단 브랜딩 타이틀 ---
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        lbl_brand = QLabel("신성미래서적")
        lbl_brand.setStyleSheet("font-size: 28px; font-weight: 800; color: #1E3A8A; letter-spacing: -0.5px;")
        lbl_brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_subtitle = QLabel("도서검수시스템")
        lbl_subtitle.setStyleSheet("font-size: 14px; font-weight: 600; color: #475569;")
        lbl_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(lbl_brand)
        header_layout.addWidget(lbl_subtitle)
        layout.addLayout(header_layout)
        
        layout.addSpacing(6)
        
        # --- 2. 입력 폼 디자인 ---
        form_layout = QVBoxLayout()
        form_layout.setSpacing(12)
        
        input_style = """
            QLineEdit {
                padding: 11px 14px;
                font-size: 14px;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                background-color: #FFFFFF;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 2px solid #2563EB;
            }
        """
        
        lbl_id = QLabel("아이디")
        lbl_id.setStyleSheet("font-size: 13px; font-weight: 600; color: #334155;")
        self.line_id = QLineEdit()
        self.line_id.setPlaceholderText("사용자 아이디를 입력하세요")
        self.line_id.setStyleSheet(input_style)
        
        lbl_pw = QLabel("비밀번호")
        lbl_pw.setStyleSheet("font-size: 13px; font-weight: 600; color: #334155;")
        self.line_pw = QLineEdit()
        self.line_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.line_pw.setPlaceholderText("비밀번호를 입력하세요")
        self.line_pw.setStyleSheet(input_style)
        self.line_pw.returnPressed.connect(self.attempt_login)
        
        form_layout.addWidget(lbl_id)
        form_layout.addWidget(self.line_id)
        form_layout.addWidget(lbl_pw)
        form_layout.addWidget(self.line_pw)
        
        layout.addLayout(form_layout)
        
        # --- 3. 체크박스 옵션 (선명한 화이트 V 체크마크 완벽 렌더링) ---
        chk_layout = QHBoxLayout()
        check_icon_path = get_custom_check_icon()
        
        chk_style = f"""
            QCheckBox {{
                font-size: 13px;
                color: #475569;
                font-weight: 600;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid #94A3B8;
                border-radius: 4px;
                background-color: #FFFFFF;
            }}
            QCheckBox::indicator:hover {{
                border-color: #2563EB;
            }}
            QCheckBox::indicator:checked {{
                background-color: #2563EB;
                border-color: #2563EB;
                image: url('{check_icon_path}');
            }}
        """
        self.chk_save_id = QCheckBox("아이디 저장")
        self.chk_save_id.setStyleSheet(chk_style)
        self.chk_save_pw = QCheckBox("비밀번호 저장")
        self.chk_save_pw.setStyleSheet(chk_style)
        
        self.chk_save_id.toggled.connect(self.on_save_id_toggled)
        
        chk_layout.addWidget(self.chk_save_id)
        chk_layout.addWidget(self.chk_save_pw)
        chk_layout.addStretch()
        
        layout.addLayout(chk_layout)
        layout.addSpacing(4)
        
        # --- 4. 하단 동작 버튼 ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_login = QPushButton("로그인")
        btn_login.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                font-weight: bold;
                padding: 12px;
                font-size: 15px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton:pressed {
                background-color: #1E40AF;
            }
        """)
        btn_login.clicked.connect(self.attempt_login)
        
        btn_signup = QPushButton("회원가입")
        btn_signup.setStyleSheet("""
            QPushButton {
                background-color: #E2E8F0;
                color: #334155;
                font-weight: bold;
                padding: 12px;
                font-size: 15px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #CBD5E1;
            }
            QPushButton:pressed {
                background-color: #94A3B8;
            }
        """)
        btn_signup.clicked.connect(self.open_signup)
        
        btn_layout.addWidget(btn_login, 1)
        btn_layout.addWidget(btn_signup, 1)
        layout.addLayout(btn_layout)
        
        self.load_saved_credentials()

    def on_save_id_toggled(self, checked):
        if not checked:
            self.chk_save_pw.setChecked(False)

    def load_saved_credentials(self):
        if os.path.exists(LOGIN_STATE_FILE):
            try:
                with open(LOGIN_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saved_id = data.get("saved_id", "")
                    saved_pw = data.get("saved_pw", "")
                    
                    if saved_id:
                        self.line_id.setText(saved_id)
                        self.chk_save_id.setChecked(True)
                    if saved_pw:
                        try:
                            decoded_pw = base64.b64decode(saved_pw.encode('utf-8')).decode('utf-8')
                            self.line_pw.setText(decoded_pw)
                            self.chk_save_pw.setChecked(True)
                        except Exception:
                            pass
            except Exception:
                pass

    def save_credentials_state(self, u_id, u_pw):
        try:
            data = {}
            if self.chk_save_id.isChecked():
                data["saved_id"] = u_id
            else:
                data["saved_id"] = ""

            if self.chk_save_pw.isChecked():
                data["saved_pw"] = base64.b64encode(u_pw.encode('utf-8')).decode('utf-8')
            else:
                data["saved_pw"] = ""

            with open(LOGIN_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
        
    def open_signup(self):
        dialog = SignUpDialog(self)
        dialog.exec()
        
    def attempt_login(self):
        u_id = self.line_id.text().strip()
        u_pw = self.line_pw.text().strip()
        
        if not u_id or not u_pw:
            QMessageBox.warning(self, "경고", "아이디와 비밀번호를 입력해주세요.")
            return

        conn = get_db_connection()
        
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, user_name, role, company_id, status FROM users WHERE user_id=%s AND user_pw=%s", (u_id, u_pw))
                user = cursor.fetchone()
                conn.close()
                
                if user:
                    if user['status'] == 'PENDING':
                        QMessageBox.warning(self, "승인 대기", "현재 관리자의 승인 대기 중입니다.\n승인 후 이용 가능합니다.")
                        return
                    elif user['status'] == 'REJECTED':
                        QMessageBox.critical(self, "거절됨", "가입 신청이 거절된 계정입니다. 관리자에게 문의하세요.")
                        return
                    elif user['status'] == 'APPROVED':
                        self.user_info = user
                        self.save_credentials_state(u_id, u_pw)
                        
                        try:
                            auth_cache = {}
                            if os.path.exists(OFFLINE_AUTH_FILE):
                                with open(OFFLINE_AUTH_FILE, "r", encoding="utf-8") as f:
                                    auth_cache = json.load(f)
                            auth_cache[u_id] = {
                                "user_pw": u_pw,
                                "user_name": user['user_name'],
                                "role": user['role'],
                                "company_id": user['company_id'],
                                "status": user['status']
                            }
                            with open(OFFLINE_AUTH_FILE, "w", encoding="utf-8") as f:
                                json.dump(auth_cache, f, ensure_ascii=False, indent=4)
                        except Exception:
                            pass
                            
                        self.accept()
                else:
                    QMessageBox.critical(self, "로그인 실패", "아이디 또는 비밀번호가 올바르지 않습니다.")
            except Exception as e:
                QMessageBox.critical(self, "DB 연결 오류", f"중앙 DB 접속 중 오류:\n{e}")
        else:
            if os.path.exists(OFFLINE_AUTH_FILE):
                try:
                    with open(OFFLINE_AUTH_FILE, "r", encoding="utf-8") as f:
                        auth_cache = json.load(f)
                    
                    if u_id in auth_cache and auth_cache[u_id]["user_pw"] == u_pw:
                        cached_user = auth_cache[u_id]
                        if cached_user["status"] == "APPROVED":
                            self.user_info = {
                                "user_id": u_id,
                                "user_name": cached_user["user_name"],
                                "role": cached_user["role"],
                                "company_id": cached_user["company_id"],
                                "status": cached_user["status"]
                            }
                            self.save_credentials_state(u_id, u_pw)
                            QMessageBox.information(self, "오프라인 접속", "인터넷이 연결되어 있지 않아 [오프라인 로컬 모드]로 로그인되었습니다.")
                            self.accept()
                            return
                        else:
                            QMessageBox.warning(self, "승인 대기", "승인되지 않은 계정입니다.")
                            return
                except Exception:
                    pass
            
            QMessageBox.critical(self, "연결 실패", "네트워크에 연결할 수 없으며, 저장된 오프라인 로그인 정보가 없습니다.\n최초 1회는 인터넷이 연결된 상태에서 로그인해야 합니다.")