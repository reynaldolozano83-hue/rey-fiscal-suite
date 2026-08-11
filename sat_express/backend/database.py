import sqlite3
import os

DB_NAME = "sat_express.db"

def get_connection():
    # Store database in the backend folder
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Orders and Transactions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_uuid TEXT UNIQUE NOT NULL,
            rfc TEXT NOT NULL,
            ciec_encrypted TEXT NOT NULL,
            email TEXT NOT NULL,
            doc_type TEXT NOT NULL, -- 'csf' or 'opinion'
            payment_status TEXT DEFAULT 'pending', -- 'pending', 'paid', 'failed'
            download_status TEXT DEFAULT 'pending', -- 'pending', 'success', 'failed'
            error_message TEXT,
            pdf_data BLOB,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("SAT Express database initialized successfully.")
