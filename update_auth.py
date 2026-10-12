# update_auth.py
with open('dialogs/auth_dialogs.py', 'r', encoding='utf-8') as f:
    code = f.read()

start_marker = '        conn = get_db_connection()'
end_marker = '            QMessageBox.critical(self, "연결 실패", "네트워크에 연결할 수 없으며, 저장된 오프라인 로그인 정보가 없습니다.\\n최초 1회는 인터넷이 연결된 상태에서 로그인해야 합니다.")'

idx1 = code.find(start_marker)
idx2 = code.find(end_marker)
assert idx1 != -1 and idx2 != -1, f"Markers not found: idx1={idx1}, idx2={idx2}"

new_code = '''        # 1. 온라인 중앙 DB 로그인 시도
        db_error_occurred = False
        
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, user_name, role, company_id, status FROM users WHERE user_id=%s AND user_pw=%s", (u_id, u_pw))
                user = cursor.fetchone()
                conn.close()
                
                if user:
                    if user['status'] == 'PENDING':
                        QMessageBox.warning(self, "승인 대기", "현재 관리자의 승인 대기 중입니다.\\n승인 후 이용 가능합니다.")
                        return
                    elif user['status'] == 'REJECTED':
                        QMessageBox.critical(self, "거절됨", "가입 신청이 거절된 계정입니다. 관리자에게 문의하세요.")
                        return
                    elif user['status'] == 'APPROVED':
                        self.user_info = user
                        self.save_credentials_state(u_id, u_pw)
                        
                        # 오프라인 캐시 갱신
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
                        return
                else:
                    QMessageBox.critical(self, "로그인 실패", "아이디 또는 비밀번호가 올바르지 않습니다.")
                    return
            else:
                db_error_occurred = True
        except Exception:
            db_error_occurred = True

        # 2. 서버 연결 실패 시 오프라인 캐시 인증으로 자동 Fallback
        if db_error_occurred:
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
                            QMessageBox.information(self, "오프라인 접속", "중앙 서버 연결이 불안정하여 [오프라인 로컬 모드]로 안전하게 자동 전환되었습니다.\\n기존 로컬 도서 데이터로 검수 및 조회가 가능합니다.")
                            self.accept()
                            return
                        else:
                            QMessageBox.warning(self, "승인 대기", "승인되지 않은 계정입니다.")
                            return
                except Exception:
                    pass
            
            QMessageBox.critical(self, "연결 실패", "중앙 DB 서버에 연결할 수 없으며, 저장된 오프라인 로그인 정보가 없습니다.\\n최초 1회는 인터넷이 연결된 상태에서 정상 로그인해야 오프라인 캐시가 생성됩니다.")'''

code = code[:idx1] + new_code + code[idx2 + len(end_marker):]

with open('dialogs/auth_dialogs.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated dialogs/auth_dialogs.py successfully!")
