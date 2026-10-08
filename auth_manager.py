# -*- coding: utf-8 -*-
import aiohttp
import cloudscraper
import requests

LOGIN_URL = "https://bbu.birmarket.az/api/v1/auth/sign-in"
PARTNERS_INFO_URL = "https://catalog-bbu-rb-api.birmarket.az/bbu/v1/partners/info"
PARTNERS_PROFILE_URL = "https://catalog-bbu-rb-api.birmarket.az/bbu/v1/partners/profile"


class AuthManager:

    def __init__(self):
        self.access_token = None
        self.merchant_uuid = None
        self.shop_name = None
        self.username = None
        self.password = None

    def login(self, username, password, log_cb=print) -> bool:
        """Авторизация по логину и паролю."""
        self.username = username
        self.password = password
        log_cb("🔐 Выполняется вход в кабинет...")

        scraper = cloudscraper.create_scraper()
        payload = {"username": username, "password": password}
        headers = {
            "origin": "https://business.birmarket.az",
            "referer": "https://business.birmarket.az/",
            "Content-Type": "application/json",
        }

        try:
            res = scraper.post(
                LOGIN_URL, json=payload, headers=headers, timeout=15
            )
            if res.status_code in [200, 201]:
                data = res.json()
                self.access_token = data.get("access_token") or data.get(
                    "accessToken"
                )
                if self.access_token:
                    log_cb(
                        "🔑 Авторизация успешна! Получаем параметры магазина..."
                    )
                    return self.fetch_store_info(log_cb)

            log_cb(f"❌ Неверный логин или пароль (Код ошибки: {res.status_code})")
        except Exception as e:
            log_cb(f"❌ Ошибка подключения при входе: {e}")

        return False

    def fetch_store_info(self, log_cb=print) -> bool:
        """Подтягивание названия магазина и merchant_uuid из API."""
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

            # 1. Попытка получить данные через /partners/info
            res_info = requests.get(
                PARTNERS_INFO_URL, headers=headers, timeout=10
            )

            if res_info.status_code == 200:
                try:
                    res_json = res_info.json()
                    data = res_json.get("data", {})
                    attr = data.get("attributes", data)

                    self.merchant_uuid = (
                        attr.get("ext_id")
                        or attr.get("id")
                        or data.get("id")
                    )
                    m_name = attr.get("marketing_name")
                    if isinstance(m_name, dict):
                        self.shop_name = m_name.get("name")

                    if not self.shop_name:
                        self.shop_name = attr.get("name") or attr.get(
                            "trade_name"
                        )
                except Exception as ex:
                    log_cb(f"⚠️ Ошибка разбора ответа partners/info: {ex}")

            # 2. Запасной вариант через /partners/profile
            if not self.merchant_uuid or not self.shop_name:
                res_prof = requests.get(
                    PARTNERS_PROFILE_URL, headers=headers, timeout=10
                )
                if res_prof.status_code == 200:
                    try:
                        p_data = res_prof.json()
                        if not self.merchant_uuid:
                            self.merchant_uuid = p_data.get(
                                "uuid"
                            ) or p_data.get("id")
                        if not self.shop_name:
                            self.shop_name = p_data.get("name") or p_data.get(
                                "trade_name"
                            )
                    except Exception:
                        pass

            if not self.shop_name and self.merchant_uuid:
                self.shop_name = f"Магазин #{str(self.merchant_uuid)[:6]}"
            elif not self.shop_name:
                self.shop_name = "Мой Магазин"

            if not self.merchant_uuid:
                log_cb("❌ Не удалось определить ID магазина от сервера.")
                return False

            log_cb(
                f"✅ Подключено: «{self.shop_name}» (ID: {self.merchant_uuid})"
            )
            return True

        except Exception as e:
            log_cb(f"⚠️ Ошибка получения профиля: {e}")
            return False

    async def async_refresh_token(self, log_cb=print) -> bool:
        """Асинхронное фоновое обновление токена, если он истек во время работы."""
        if not self.username or not self.password:
            return False

        log_cb("🔄 Токен истек. Выполняется авто-обновление...")
        payload = {"username": self.username, "password": self.password}
        headers = {
            "origin": "https://business.birmarket.az",
            "referer": "https://business.birmarket.az/",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    LOGIN_URL, json=payload, headers=headers, timeout=15
                ) as res:
                    if res.status in [200, 201]:
                        data = await res.json()
                        new_token = data.get("access_token") or data.get(
                            "accessToken"
                        )
                        if new_token:
                            self.access_token = new_token
                            log_cb("🔑 Токен успешно обновлен!")
                            return True
        except Exception as e:
            log_cb(f"❌ Ошибка обновления токена: {e}")

        return False