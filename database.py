import sqlite3
import os

DB_NAME = "birmarket_local.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Настройки и Авторизация
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            username TEXT,
            password TEXT,
            merchant_uuid TEXT,
            merchant_name TEXT,
            access_token TEXT,
            refresh_token TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # 2. Товары и Настройки Демпинга (Замена Листа 1)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            offer_id TEXT,
            category_name TEXT,
            gtin TEXT,
            sku TEXT,
            name TEXT,
            min_price REAL DEFAULT 0.0,
            max_price REAL DEFAULT 0.0,
            my_price REAL DEFAULT 0.0,
            comp_price REAL DEFAULT 0.0,
            manual_base REAL DEFAULT 0.0,
            undercut_step REAL DEFAULT 0.01,
            qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Satışda',
            rrp_limit REAL DEFAULT 0.0,
            auto_repricing INTEGER DEFAULT 1
        )
        """)
        
        # 3. Дружественные магазины
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS friendly_shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_uuid TEXT UNIQUE,
            shop_name TEXT
        )
        """)
        
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("✅ Локальная база данных успешно инициализирована!")