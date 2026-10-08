# -*- coding: utf-8 -*-
import sqlite3
import os
from typing import List, Dict, Any, Optional

DB_NAME = "database.db"


class DatabaseManager:

    def __init__(self, db_path: str = DB_NAME):
        self.db_path = db_path
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Возвращает подключение к БД с доступом к колонкам по имени."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Создает необходимые таблицы, если они еще не существуют."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Таблица настроек (хранит сессию и конфигурацию репрайсинга)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT,
                    password TEXT,
                    merchant_uuid TEXT,
                    shop_name TEXT,
                    friendly_shops TEXT DEFAULT '',
                    undercut_step REAL DEFAULT 0.01,
                    night_boost_enabled INTEGER DEFAULT 0
                )
            """
            )

            # Создаем начальную строку настроек, если ее нет
            cursor.execute(
                "INSERT OR IGNORE INTO settings (id) VALUES (1)"
            )

            # 2. Таблица товаров
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    offer_id TEXT,
                    sku TEXT,
                    name TEXT,
                    category TEXT,
                    limit_min REAL DEFAULT 0.0,
                    limit_max REAL DEFAULT 0.0,
                    manual_price REAL DEFAULT 0.0,
                    my_price REAL DEFAULT 0.0,
                    comp_price REAL DEFAULT 0.0,
                    calculated_price REAL DEFAULT 0.0,
                    qty INTEGER DEFAULT 0,
                    auto_reprice INTEGER DEFAULT 1,
                    needs_update INTEGER DEFAULT 0
                )
            """
            )
            conn.commit()

    # ==================== НАСТРОЙКИ (SETTINGS) ====================

    def save_auth_session(
        self, username: str, password: str, merchant_uuid: str, shop_name: str
    ):
        """Сохраняет данные авторизации после успешного входа."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE settings 
                SET username = ?, password = ?, merchant_uuid = ?, shop_name = ?
                WHERE id = 1
            """,
                (username, password, merchant_uuid, shop_name),
            )
            conn.commit()

    def load_settings(self) -> Dict[str, Any]:
        """Загружает все текущие настройки приложения."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM settings WHERE id = 1")
            row = cursor.fetchone()
            return dict(row) if row else {}

    def update_reprice_settings(
        self,
        friendly_shops: str,
        undercut_step: float,
        night_boost_enabled: bool,
    ):
        """Обновляет бизнес-правила (дружественные магазины, шаг демпинга и т.д.)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE settings 
                SET friendly_shops = ?, undercut_step = ?, night_boost_enabled = ?
                WHERE id = 1
            """,
                (friendly_shops, undercut_step, 1 if night_boost_enabled else 0),
            )
            conn.commit()

    # ==================== ТОВАРЫ (PRODUCTS) ====================

    def upsert_products_from_catalog(self, products_data: List[Dict[str, Any]]):
        """
        Импортирует/обновляет товары из личного кабинета Umico/Birmarket.
        ВАЖНО: Поля limit_min, limit_max, manual_price и auto_reprice
        НЕ перезаписываются, чтобы не сбросить настройки пользователя!
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for item in products_data:
                cursor.execute(
                    """
                    INSERT INTO products (product_id, offer_id, sku, name, category, my_price, qty)
                    VALUES (:product_id, :offer_id, :sku, :name, :category, :my_price, :qty)
                    ON CONFLICT(product_id) DO UPDATE SET
                        offer_id = excluded.offer_id,
                        sku = excluded.sku,
                        name = excluded.name,
                        category = excluded.category,
                        my_price = excluded.my_price,
                        qty = excluded.qty
                """,
                    item,
                )
            conn.commit()

    def get_all_products(self) -> List[Dict[str, Any]]:
        """Получает список всех товаров для отображения в интерфейсе UI."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products ORDER BY name ASC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def update_product_user_limits(
        self,
        product_id: str,
        limit_min: float,
        limit_max: float,
        manual_price: float,
        auto_reprice: bool,
    ):
        """Вызывается при изменении Мин/Макс/Ручной цены пользователем в таблице UI."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE products 
                SET limit_min = ?, limit_max = ?, manual_price = ?, auto_reprice = ?
                WHERE product_id = ?
            """,
                (
                    limit_min,
                    limit_max,
                    manual_price,
                    1 if auto_reprice else 0,
                    product_id,
                ),
            )
            conn.commit()

    def save_core_calculation(
        self,
        product_id: str,
        comp_price: float,
        calculated_price: float,
        needs_update: bool,
    ):
        """Записывает результаты работы модуля core.py (расчитанную цену и флаг отправки)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE products 
                SET comp_price = ?, calculated_price = ?, needs_update = ?
                WHERE product_id = ?
            """,
                (
                    comp_price,
                    calculated_price,
                    1 if needs_update else 0,
                    product_id,
                ),
            )
            conn.commit()

    def get_products_pending_update(self) -> List[Dict[str, Any]]:
        """Возвращает только те товары, у которых изменилась цена (needs_update = 1) для pusher.py."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM products WHERE needs_update = 1"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def reset_update_flag(self, product_id: str, new_my_price: float):
        """Сбрасывает флаг needs_update в 0 после успешной отправки цены на Umico."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE products 
                SET needs_update = 0, my_price = ?
                WHERE product_id = ?
            """,
                (new_my_price, product_id),
            )
            conn.commit()