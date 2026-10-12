# create_indexes.py
import os
import pymysql
from dotenv import load_dotenv
from config import get_safe_path, DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME

load_dotenv(get_safe_path(".env"))

print("TiDB Cloud 인덱스 최적화 연결 중...")
try:
    conn = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        charset="utf8mb4",
        ssl={},
        connect_timeout=10,
        autocommit=True
    )
    cursor = conn.cursor()
    print("1. idx_books_comp_del_date 인덱스 생성 중...")
    cursor.execute("CREATE INDEX IF NOT EXISTS `idx_books_comp_del_date` ON `books` (`company_id`, `delivery`, `reg_date`)")
    
    print("2. idx_books_isbn 인덱스 생성 중...")
    cursor.execute("CREATE INDEX IF NOT EXISTS `idx_books_isbn` ON `books` (`isbn_clean`)")
    
    conn.commit()
    conn.close()
    print("✅ 인덱스 생성이 성공적으로 완료되었습니다!")
except Exception as e:
    print(f"❌ 인덱스 생성 중 오류 발생: {e}")
