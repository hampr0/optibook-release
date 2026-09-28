import pymysql
from config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME

def get_db_connection():
    """TiDB Serverless 클라우드 DB 연결 (SSL 필수 적용)"""
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            charset="utf8mb4",
            ssl={},  # TiDB Serverless 필수
            connect_timeout=5,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        print(f"❌ DB 접속 에러: {e}")
        return None