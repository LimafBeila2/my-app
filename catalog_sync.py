# -*- coding: utf-8 -*-
import requests
import re
import time
from typing import List, Dict, Any, Callable, Optional
from auth_manager import AuthManager
from db import DatabaseManager

CATALOG_PRODUCTS_URL = "https://catalog-bbu-rb-api.birmarket.az/bbu/v1/products"


class CatalogSyncer:

    def __init__(self, auth_manager: AuthManager, db_manager: DatabaseManager):
        self.auth = auth_manager
        self.db = db_manager

    def _get_headers(self) -> Dict[str, str]:
        """Формирует заголовки авторизации для API запросов."""
        return {
            "Authorization": f"Bearer {self.auth.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def fetch_page_products(self, page: int = 1, limit: int = 20, log_cb: Callable[[str], None] = print) -> Optional[Dict[str, Any]]:
        """Запрашивает активные товары продавца из API Birmarket."""
        if not self.auth.access_token or not self.auth.merchant_uuid:
            log_cb("❌ Ошибка: отсутствует токен или ID магазина.")
            return None

        params = {
            'q[s]': 'id asc',
            'q[status_in]': 'active,out_of_stock,ready_to_publish,removed_from_sale',
            'q[product_offers_merchant_uuid_eq]': self.auth.merchant_uuid,
            'q[product_offers_deleted_eq]': 'false',
            'page': page,
            'per_page': limit,
            'include_fields': 'id,name_az,name_ru,status,qty,product_offers,product,rrp,categories,gtin'
        }

        try:
            response = requests.get(
                CATALOG_PRODUCTS_URL,
                headers=self._get_headers(),
                params=params,
                timeout=15
            )

            # Переавторизация при истечении токена (401)
            if response.status_code == 401:
                log_cb("🔄 Токен истек, пробуем обновить авторизацию...")
                if self.auth.username and self.auth.password:
                    if self.auth.login(self.auth.username, self.auth.password, log_cb=log_cb):
                        response = requests.get(
                            CATALOG_PRODUCTS_URL,
                            headers=self._get_headers(),
                            params=params,
                            timeout=15
                        )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                log_cb("⏳ Пауза 5 сек: превышен лимит запросов (429)...")
                time.sleep(5)
                return self.fetch_page_products(page=page, limit=limit, log_cb=log_cb)
            else:
                log_cb(f"⚠️ Ошибка API Birmarket (Код {response.status_code}): {response.text[:200]}")

        except Exception as e:
            log_cb(f"⚠️ Сетевая ошибка при запросе каталога: {e}")

        return None

    def parse_products(self, raw_data: Dict[str, Any], log_cb: Callable[[str], None] = print) -> List[Dict[str, Any]]:
        """Разбирает список товаров с сопоставлением merchant_uuid продавца."""
        parsed_items = []
        data_list = raw_data.get("data", []) if isinstance(raw_data, dict) else []

        if not data_list:
            return []

        target_uuid = str(self.auth.merchant_uuid).strip().lower() if self.auth.merchant_uuid else ""

        for item in data_list:
            try:
                attrs = item.get("attributes", {})
                offers = attrs.get("product_offers", [])

                # Ищем оффер, принадлежащий текущему магазину
                my_offer = None
                for o in offers:
                    o_uuid = str(o.get("merchant_uuid", "")).strip().lower()
                    if o_uuid == target_uuid:
                        my_offer = o
                        break

                # Фильтруем удаленные или неактивные офферы
                if not my_offer or my_offer.get("active") is False or my_offer.get("deleted") is True:
                    continue

                pid = str(item.get("id") or "")
                if not pid:
                    continue

                # Категория
                cats = attrs.get("categories", [])
                category_name = cats[0].get("name_az") or cats[0].get("name_ru") if cats else "Без категории"

                # Название
                name = attrs.get("name_az") or attrs.get("name_ru") or f"Товар {pid}"

                # SKU / Штрихкод
                sku = str(my_offer.get("sku") or attrs.get("gtin") or "")

                # Offer ID
                raw_offer_id = str(my_offer.get("id", ""))
                offer_id = re.sub(r'\D', '', raw_offer_id) if raw_offer_id else pid

                # Цена продавца
                price = float(
                    my_offer.get("price") or 
                    my_offer.get("retail_price") or 
                    attrs.get("price") or 0.0
                )

                # Остаток
                qty = int(my_offer.get("qty", 0)) if my_offer.get("qty") is not None else 0

                parsed_items.append({
                    "product_id": pid,
                    "offer_id": offer_id,
                    "sku": sku,
                    "name": str(name),
                    "category": str(category_name),
                    "my_price": price,
                    "qty": qty
                })

            except Exception as ex:
                log_cb(f"⚠️ Ошибка разбора товара {item.get('id')}: {ex}")
                continue

        return parsed_items

    def sync_catalog(self, log_cb: Callable[[str], None] = print) -> int:
        """Скачивает товары и сохраняет их в базу SQLite."""
        log_cb("📦 Запуск синхронизации каталога товаров с Birmarket...")

        if not self.auth.merchant_uuid:
            log_cb("❌ Ошибка: не найден Merchant UUID магазина. Выполните вход заново.")
            return 0

        page = 1
        limit = 20
        total_synced = 0

        while True:
            log_cb(f"🔄 Получение страницы {page}...")
            raw_data = self.fetch_page_products(page=page, limit=limit, log_cb=log_cb)

            if not raw_data:
                log_cb("⚠️ Не удалось получить данные со страницы каталога.")
                break

            parsed_products = self.parse_products(raw_data, log_cb=log_cb)

            meta = raw_data.get("meta", {})
            total_pages = meta.get("total_pages") or 1

            if parsed_products:
                self.db.upsert_products_from_catalog(parsed_products)
                count_on_page = len(parsed_products)
                total_synced += count_on_page
                log_cb(f"✅ Страница {page}/{total_pages}: загружено {count_on_page} товаров.")

            if page >= total_pages:
                break

            page += 1
            time.sleep(0.1)

        log_cb(f"🎉 Синхронизация завершена! Всего товаров в базе: {total_synced}")
        return total_synced