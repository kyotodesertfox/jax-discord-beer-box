import os
import psycopg2
from psycopg2 import pool
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / 'secrets' / 'db_conn.env')


class DBManager:
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        if not self.db_url:
            raise ValueError("❌ DATABASE_URL not found in db_conn.env")
        self.pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=self.db_url)
        print("✅ Database connection pool established.")

    def get_cursor(self):
        conn = self.pool.getconn()
        return conn, conn.cursor()

    def release_conn(self, conn):
        self.pool.putconn(conn)

    def close_all(self):
        self.pool.closeall()
