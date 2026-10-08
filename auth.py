# -*- coding: utf-8 -*-
import requests
import cloudscraper
import sqlite3
from database import DB_NAME

LOGIN_URL_BBU = "https://bbu.birmarket.az/api/v1/auth/sign-in"

class AuthManager:
    def __init__(self):
        self.access_token = None
        self.merchant_uuid = None
        self.shop_name = None
        self.username = None

    def login_and_save(self, username, password, log_cb=print) -> bool:
        """
        Выполняет вход в Birmarket, получает access_token, UID и имя магазина,
        и сохраняет сессию в локальную SQLite БД.
        """
        self.username = username
        log_cb("🔐 Выполняется вход в кабинет Birmarket...")

        scraper = cloudscraper.create_scraper()
        payload = {"username": username, "password": password}
        headers = {
            "origin": "https://business.birmarket.az",
            "referer": "https://business.birmarket.az/",
            "Content-Type": "application/json",
        }

        try:
            res = scraper.post(LOGIN_URL_BBU, json=payload, headers=headers, timeout=15)
            if res.status_code in [200, 201]:
                data = res.json()
                self.access_token = data.get("access_token") or data.get("accessToken")
                if self.access_token:
                    # Извлекаем UID и название магазина
                    if self._fetch_store_info(log_cb):
                        # Сохраняем данные авторизации в БД
                        self._save_session_to_db(password)
                        log_cb(f"✅ Успешный вход! Магазин: {self.shop_name} (UID: {self.merchant_uuid})")
                        return True
            
            log_cb(f"❌ Неверный логин или пароль (Код: {res.status_code})")
        except Exception as e:
            log_cb(f"❌ Ошибка подключения при входе: {e}")

        return False

    def _fetch_store_info(self, log_cb) -> bool:
        """Получение UID и имени магазина из API Birmarket."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Origin": "https://business.birmarket.az",
            "Referer": "https://business.birmarket.az/",
        }

        try:
            self.shop_name = None
            self.merchant_uuid = None

            # Основной запрос: info
            url_info = "https://catalog-bbu-rb-api.birmarket.az/bbu/v1/partners/info"
            res_info = requests.get(url_info, headers=headers, timeout=10)

            if res_info.status_code == 200:
                try:
                    res_json = res_info.json()
                    data = res_json.get("data", {})
                    attr = data.get("attributes", data)

                    self.merchant_uuid = attr.get("ext_id") or attr.get("id") or data.get("id")
                    m_name = attr.get("marketing_name")
                    if isinstance(m_name, dict):
                        self.shop_name = m_name.get("name")

                    if not self.shop_name:
                        self.shop_name = attr.get("name") or attr.get("trade_name")
                except Exception as ex:
                    log_cb(f"⚠️ Ошибка разбора partners/info: {ex}")

            # Запасной запрос: profile
            if not self.merchant_uuid or not self.shop_name:
                url_profile = "https://catalog-bbu-rb-api.birmarket.az/bbu/v1/partners/profile"
                res_prof = requests.get(url_profile, headers=headers, timeout=10)
                if res_prof.status_code == 200:
                    try:
                        p_data = res_prof.json()
                        if not self.merchant_uuid:
                            self.merchant_uuid = p_data.get("uuid") or p_data.get("id")
                        if not self.shop_name:
                            self.shop_name = p_data.get("name") or p_data.get("trade_name")
                    except Exception:
                        pass

            if not self.shop_name and self.merchant_uuid:
                self.shop_name = f"Магазин #{str(self.merchant_uuid)[:6]}"
            elif not self.shop_name:
                self.shop_name = "Магазин"

            if not self.merchant_uuid:
                log_cb("❌ Не удалось получить UID магазина от сервера.")
                return False

            return True

        except Exception as e:
            log_cb(f"⚠️ Ошибка загрузки профиля: {e}")
            return False

    def _save_session_to_db(self, password):
        """Сохранение аккаунта в SQLite."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO account_settings (id, username, password, merchant_uuid, merchant_name, access_token)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username=excluded.username,
                password=excluded.password,
                merchant_uuid=excluded.merchant_uuid,
                merchant_name=excluded.merchant_name,
                access_token=excluded.access_token,
                updated_at=CURRENT_TIMESTAMP
        """, (self.username, password, str(self.merchant_uuid), self.shop_name, self.access_token))
        conn.commit()
        conn.close()

    @staticmethod
    def get_saved_session():
        """Проверка наличия сохраненной сессии при запуске приложения."""
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM account_settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None