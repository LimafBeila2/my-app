# -*- coding: utf-8 -*-
import cloudscraper
from typing import List, Dict, Any, Optional, Set

MP_CATALOG_PRODUCT_URL = "https://mp-catalog.birmarket.az/api/v1/products"


class CompetitorParser:

    def __init__(self, my_merchant_uuid: Optional[str] = None, friendly_shops: Optional[List[str]] = None):
        self.my_merchant_uuid = str(my_merchant_uuid or "").strip().lower()
        self.friendly_shops: Set[str] = set()
        
        if friendly_shops:
            self.set_friendly_shops_list(friendly_shops)

        # cloudscraper обходит базовые защиты Cloudflare на публичном API
        self.scraper = cloudscraper.create_scraper()

    def set_friendly_shops_from_string(self, friendly_shops_str: str):
        """Обновляет список дружественных магазинов из строки через запятую (из настроек БД/UI)."""
        if not friendly_shops_str:
            self.friendly_shops = set()
            return
            
        raw_list = friendly_shops_str.split(",")
        self.friendly_shops = {str(s).strip().lower() for s in raw_list if str(s).strip()}

    def set_friendly_shops_list(self, friendly_shops_list: List[str]):
        """Обновляет список дружественных магазинов из списка."""
        self.friendly_shops = {str(s).strip().lower() for s in friendly_shops_list if str(s).strip()}

    def set_my_merchant_uuid(self, merchant_uuid: str):
        """Устанавливает UID собственного магазина для исключения его из конкурентов."""
        self.my_merchant_uuid = str(merchant_uuid or "").strip().lower()

    def fetch_product_offers(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Запрашивает карточку товара и все предложения продавцов по product_id."""
        url = f"{MP_CATALOG_PRODUCT_URL}/{product_id}"
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "az",
            "content-language": "az",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "origin": "https://birmarket.az",
            "referer": "https://birmarket.az/",
        }

        try:
            res = self.scraper.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            print(f"⚠️ Ошибка запроса конкурентов (Product ID: {product_id}): {e}")

        return None

    def get_best_competitor_price(self, product_id: str) -> Dict[str, Any]:
        """
        Главная функция фильтрации и поиска минимальной цены конкурента:
        1. Запрашивает офферы карточки товара.
        2. Исключает свой магазин.
        3. Исключает дружественные магазины (по ID или по названию).
        4. Возвращает минимальную цену среди реальных конкурентов.
        """
        raw_data = self.fetch_product_offers(product_id)
        if not raw_data:
            return {
                "product_id": product_id,
                "best_comp_price": 0.0,
                "best_comp_name": "Нет данных",
                "total_competitors": 0
            }

        # Извлекаем список офферов (продавцов) на карточке
        product_data = raw_data.get("product") or raw_data.get("data") or raw_data
        offers = product_data.get("offers") or product_data.get("product_offers") or []

        if not offers and "default_offer" in product_data:
            offers = [product_data["default_offer"]]

        valid_competitors = []

        for offer in offers:
            try:
                seller = offer.get("seller") or {}
                m_name_obj = seller.get("marketing_name") or {}

                seller_id = str(seller.get("id") or offer.get("merchant_uuid") or offer.get("supplier_id") or "").strip().lower()
                seller_name = str(m_name_obj.get("name") or seller.get("name") or "").strip()
                seller_name_lower = seller_name.lower()

                price = float(offer.get("retail_price") or offer.get("price") or 0.0)
                if price <= 0:
                    continue

                # 1. Пропускаем свой магазин
                if self.my_merchant_uuid and (seller_id == self.my_merchant_uuid or seller_name_lower == self.my_merchant_uuid):
                    continue

                # 2. Пропускаем дружественные магазины (по ID или имени)
                if seller_id in self.friendly_shops or seller_name_lower in self.friendly_shops:
                    continue

                valid_competitors.append({
                    "seller_id": seller_id,
                    "seller_name": seller_name or "Неизвестно",
                    "price": price
                })
            except Exception:
                continue

        if not valid_competitors:
            return {
                "product_id": product_id,
                "best_comp_price": 0.0,
                "best_comp_name": "Конкурентов нет",
                "total_competitors": 0
            }

        # Сортируем конкурентов от меньшей цены к большей
        valid_competitors.sort(key=lambda x: x["price"])
        best_comp = valid_competitors[0]

        return {
            "product_id": product_id,
            "best_comp_price": best_comp["price"],
            "best_comp_name": best_comp["seller_name"],
            "total_competitors": len(valid_competitors)
        }