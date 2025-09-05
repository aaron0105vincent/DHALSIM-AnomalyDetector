import sqlite3
import time

def safe_db_query(conn, query):
    while True:
        try:
            cur = conn.cursor()
            cur.execute(query)
            return cur.fetchall()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(0.1)
            else:
                raise
            
def get_master_time(conn):
    rows = safe_db_query(conn, "SELECT time FROM master_time WHERE id = 1")
    return int(float(rows[0][0])) if rows else None