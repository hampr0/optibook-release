# error_handler.py
"""
신성미래서적 - Optibook-IMS 전역 오류 수집 및 로깅 모듈
- 로컬 디스크 파일(optibook_error.log, logs/app_YYYYMMDD.log) 실시간 기록
- 중앙 DB(TiDB Cloud error_logs 테이블) 비동기 원격 전송
- sys.excepthook 및 threading.excepthook 전역 등록으로 미처리 예외 100% 포획
"""

import os
import sys
import threading
import traceback
import platform
import socket
from datetime import datetime

# 로그 디렉토리 생성
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

MASTER_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "optibook_error.log")

CURRENT_USER_INFO = {"company_id": "UNKNOWN", "user_id": "UNKNOWN"}


def set_user_context(company_id, user_id):
    """현재 로그인된 사용자 컨텍스트 설정"""
    CURRENT_USER_INFO["company_id"] = str(company_id)
    CURRENT_USER_INFO["user_id"] = str(user_id)


def log_exception(exc_type, exc_value, exc_traceback, thread_name="MainThread"):
    """모든 예외를 로컬 파일 및 원격 DB에 안전하게 기록"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_str = "".join(tb_lines)
    
    comp_id = CURRENT_USER_INFO.get("company_id", "UNKNOWN")
    user_id = CURRENT_USER_INFO.get("user_id", "UNKNOWN")
    pc_name = socket.gethostname()
    os_info = f"{platform.system()} {platform.release()}"
    
    error_summary = f"[{now_str}] [{comp_id}/{user_id}] [{pc_name}] [{thread_name}] {exc_type.__name__}: {exc_value}"
    
    log_content = (
        f"\n{'='*70}\n"
        f"발생일시: {now_str}\n"
        f"회사/사용자: {comp_id} / {user_id}\n"
        f"컴퓨터/OS: {pc_name} / {os_info}\n"
        f"스레드명: {thread_name}\n"
        f"오류내용: {exc_type.__name__}: {exc_value}\n"
        f"상세 스택 트레이스:\n{tb_str}"
        f"{'='*70}\n"
    )
    
    # 1. 로컬 통합 에러 로그 파일 기록 (optibook_error.log)
    try:
        with open(MASTER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_content)
    except Exception:
        pass
        
    # 2. 일자별 상세 로그 파일 기록 (logs/app_YYYYMMDD.log)
    daily_file = os.path.join(LOG_DIR, f"error_{datetime.now().strftime('%Y%m%d')}.log")
    try:
        with open(daily_file, "a", encoding="utf-8") as f:
            f.write(log_content)
    except Exception:
        pass

    # 콘솔 출력
    print(error_summary, file=sys.stderr)
    
    # 3. 원격 DB 비동기 전송
    def _send_to_remote():
        try:
            from db import get_db_connection
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                sql = "INSERT INTO error_logs (company_id, user_id, error_msg, traceback) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (comp_id, user_id, f"[{pc_name}][{thread_name}] {exc_type.__name__}: {exc_value}", tb_str))
                conn.commit()
                conn.close()
        except Exception:
            pass

    threading.Thread(target=_send_to_remote, daemon=True).start()


def global_sys_excepthook(exc_type, exc_value, exc_traceback):
    """메인 스레드 미처리 예외 전역 훅"""
    log_exception(exc_type, exc_value, exc_traceback, thread_name="MainThread")
    # 기본 excepthook 동작도 함께 수행
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def global_threading_excepthook(args):
    """백그라운드 스레드 미처리 예외 전역 훅 (Python 3.8+)"""
    thread_name = getattr(args.thread, "name", "WorkerThread")
    log_exception(args.exc_type, args.exc_value, args.exc_traceback, thread_name=thread_name)


def init_error_handler():
    """애플리케이션 시작 시 전역 오류 감시기 등록"""
    sys.excepthook = global_sys_excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = global_threading_excepthook
