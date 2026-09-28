import os
import sys
from dotenv import load_dotenv

# 앱 버전 설정
CURRENT_APP_VERSION = "1.0.2"

# 기본 경로 및 실행 디렉터리 고정
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    os.chdir(BASE_DIR)
except Exception as e:
    print(f"작업 디렉터리 고정 실패: {e}")

def get_safe_path(filename):
    return os.path.abspath(os.path.join(BASE_DIR, filename))

# .env 환경 변수 파일 로드
load_dotenv(get_safe_path(".env"))

# 중앙 TiDB Cloud DB 접속 정보
DB_HOST = os.getenv("TIDB_HOST", "gateway01.ap-northeast-1.prod.aws.tidbcloud.com")
DB_PORT = int(os.getenv("TIDB_PORT", 4000))
DB_USER = os.getenv("TIDB_USER", "BdRX6BGKz6XdjZR.root")
DB_PASS = os.getenv("TIDB_PASSWORD", "")
DB_NAME = os.getenv("TIDB_DATABASE", "bookst_db")

# 파일 경로 정의
TEMPLATE_FILE = get_safe_path("graphic_template.json")
DB_FILE = get_safe_path("bookst_db.csv")
APP_STATE_FILE = get_safe_path("app_state.json")
LOGIN_STATE_FILE = get_safe_path("login_state.json")
OFFLINE_AUTH_FILE = get_safe_path("offline_auth.json")