import asyncio
import gspread
import os
import sys
import io
import random
import re
import datetime
import httpx
from oauth2client.service_account import ServiceAccountCredentials

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# КОНФИГУРАЦИЯ
SHEET_FILE = os.path.join(BASE_DIR, 'sirius-bot-493613-c89eb1def69b.json')
SHEET_NAME = 'Sirius'
BILLING_SHEET_NAME = 'Birmarket Time'
MY_SHOP_ID = 5620
FRIENDLY_SHOPS = [] 
SENT_PRICES_CACHE = {}

BATCH_SIZE = 100

async def fetch_mget_data(client: httpx.AsyncClient, batch_pool):
    pids = [item["pid"] for item in batch_pool]
    url = "https://birmarket.az/catalog/v3/market/products/mget"
    params = {
        "q[id_in]": ",".join(pids), 
        "include_fields": "id,offers" 
    }
    headers = {
        'accept': 'application/json',
        'user-agent': 'Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'
    }
    try:
        resp = await client.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200: 
            return resp.json().get('data', [])
    except Exception: 
        pass
    return []

async def run_repricer():
    updated_count = 0
    first_place_pids = set() 

    async with httpx.AsyncClient() as client:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                SHEET_FILE, 
                ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            )
            gc = await asyncio.to_thread(gspread.authorize, creds)
            sh = await asyncio.to_thread(gc.open, SHEET_NAME)
            sheet = await asyncio.to_thread(sh.get_worksheet, 0)
            
            try:
                all_data = await asyncio.to_thread(sheet.get_all_values)
            except Exception as e:
                if "429" in str(e):
                    print("⚠️ GOOGLE API ЛИМИТ! Спим 65 секунд...")
                    await asyncio.sleep(65)
                    all_data = await asyncio.to_thread(sheet.get_all_values)
                else: 
                    raise e
            
            pool = []
            for i, r in enumerate(all_data[1:], 2):
                if len(r) > 11 and "/product/" in r[4] and r[11] == "Satışda":
                    m = re.search(r'product/(\d+)', r[4])
                    if m: 
                        pool.append({"row": i, "pid": m.group(1), "name": r[3], "raw_data": r})

            print(f"📊 ТОВАРОВ В РАБОТЕ: {len(pool)}")

            global_mega_buffer = []

            for i in range(0, len(pool), BATCH_SIZE):
                batch = pool[i : i + BATCH_SIZE]
                api_data = await fetch_mget_data(client, batch)
                results_map = {str(p['id']): p.get('offers', []) for p in api_data}

                for b in batch:
                    pid = b["pid"]
                    offers = results_map.get(pid)
                    row_raw = b["raw_data"] 
                    if not offers: 
                        continue

                    my_offer = None
                    enemies = {}
                    friends = {}

                    # --- ИЗВЛЕЧЕНИЕ ID И ЦЕН ПРОДАВЦОВ ---
                    for off in offers:
                        m_info = off.get('marketing_name') if isinstance(off.get('marketing_name'), dict) else {}
                        s_info = off.get('seller_marketing_name') if isinstance(off.get('seller_marketing_name'), dict) else {}
                        
                        sid = int(
                            off.get('seller_marketing_name_id') or 
                            off.get('marketing_name_id') or 
                            m_info.get('internal_id') or 
                            s_info.get('internal_id') or 0
                        )
                        price = float(off.get('retail_price', 0))

                        if sid == MY_SHOP_ID: 
                            my_offer = off
                        elif sid in FRIENDLY_SHOPS: 
                            friends[sid] = price
                        elif sid != 0: 
                            enemies[sid] = price
                    
                    if not my_offer: 
                        continue
                    
                    my_p = float(my_offer.get('retail_price', 0))

                    # --- ПАРСИНГ ПАРАМЕТРОВ ИЗ ТАБЛИЦЫ ---
                    try: price_in_table = float(row_raw[7].replace(',', '.')) if row_raw[7] else 0.0 
                    except: price_in_table = 0.0
                    text_in_table = str(row_raw[8]) 
                    try: limit_min = float(row_raw[5].replace(',', '.')) if row_raw[5] else 0.0 
                    except: limit_min = 0.0
                    try: limit_max = float(row_raw[6].replace(',', '.')) if row_raw[6] else 0.0 
                    except: limit_max = 0.0
                    try: umico_limit = float(row_raw[13].replace(',', '.')) if len(row_raw) > 13 and row_raw[13] else 0.0 
                    except: umico_limit = 0.0
                    try: manual_p = float(row_raw[14].replace(',', '.')) if len(row_raw) > 14 and row_raw[14] else 0.0 
                    except: manual_p = 0.0

                    target_p = my_p
                    comp_p_text = ""
                    no_discount_flag = False
                    
                    min_friend = min(friends.values()) if friends else float('inf')
                    min_enemy = min(enemies.values()) if enemies else float('inf')

                    # --- ЛОГИКА ВЫБОРА ЦЕНЫ ---
                    if manual_p > 0:
                        all_others = {**enemies, **friends}
                        best_price = min(all_others.values()) if all_others else 0.0
                        if not all_others:
                            target_p = manual_p
                            no_discount_flag = True
                            comp_p_text = "Manual (Alone)"
                        else:
                            step = 0.01 if best_price <= 100 else 0.02
                            if abs(best_price - manual_p) < 0.009 or abs(best_price - (manual_p + 0.01)) < 0.009:
                                target_p = manual_p
                                no_discount_flag = True
                                comp_p_text = f"O-Match ({best_price})"
                            else:
                                target_p = round(best_price - step, 2)
                                comp_p_text = str(best_price)
                    
                    elif min_friend == float('inf') and min_enemy == float('inf'):
                        comp_p_text = "Yegane Satici"
                        if limit_max > 0:
                            target_p = limit_max
                        elif my_p >= max(limit_min, umico_limit):
                            target_p = my_p 
                        else:
                            base_for_bonus = max(limit_min, umico_limit)
                            bonus = random.randint(15, 20) / 100
                            target_p = round(base_for_bonus * (1 + bonus), 2)
                    
                    elif min_friend <= min_enemy:
                        target_p = min_friend
                        comp_p_text = f"Dost ({min_friend})"

                    else:
                        step = 0.01 if min_enemy <= 100 else 0.02
                        potential_p = round(min_enemy - step, 2)
                        effective_min = max(limit_min, umico_limit)

                        if effective_min > 0 and potential_p < effective_min:
                            if limit_max > 0:
                                target_p = limit_max
                                comp_p_text = f"Max Limit ({min_enemy})"
                            else:
                                target_p = effective_min
                                comp_p_text = str(min_enemy)
                        else:
                            target_p = potential_p
                            comp_p_text = str(min_enemy)

                    # --- ФИНАЛЬНЫЕ ОГРАНИЧЕНИЯ И СТРАХОВКА ---
                    final_p = max(target_p, limit_min, umico_limit)
                    if limit_max > 0:
                        final_p = min(final_p, limit_max)

                    if manual_p > 0 and abs(final_p - manual_p) < 0.009:
                        no_discount_flag = True

                    if my_p <= (final_p + 0.01) and final_p <= min_enemy: 
                        first_place_pids.add(pid)

                    # --- ПРОВЕРКА ОБНОВЛЕНИЙ И КЭШИРОВАНИЕ ---
                    site_mismatch = abs(my_p - final_p) > 0.009
                    price_mismatch = abs(final_p - price_in_table) > 0.009
                    text_mismatch = comp_p_text != text_in_table

                    if site_mismatch:
                        if SENT_PRICES_CACHE.get(pid) != final_p:
                            updated_count += 1
                            command_val = "UPDATE_OFF" if no_discount_flag else "UPDATE_ON"
                            global_mega_buffer.append({
                                'range': f'M{b["row"]}', 
                                'values': [[command_val]]
                            })
                            SENT_PRICES_CACHE[pid] = final_p

                        global_mega_buffer.append({
                            'range': f'H{b["row"]}:I{b["row"]}', 
                            'values': [[str(final_p), str(comp_p_text)]]
                        })

                    elif price_mismatch or text_mismatch:
                        global_mega_buffer.append({
                            'range': f'H{b["row"]}:I{b["row"]}', 
                            'values': [[str(final_p), str(comp_p_text)]]
                        })

            # Запись всех изменений за 1 запрос
            if global_mega_buffer:
                try:
                    await asyncio.to_thread(sheet.batch_update, global_mega_buffer)
                except Exception as sheet_err:
                    if "429" in str(sheet_err):
                        print("⚠️ Лимит на сохранении результатов! Засыпаем на 60 сек...")
                        await asyncio.sleep(60)
                        await asyncio.to_thread(sheet.batch_update, global_mega_buffer)
                    else:
                        raise sheet_err
            
            print(f"🥇 ПЕРВЫЙ В: {len(first_place_pids)}")
            print(f"📈 ОБНОВЛЕНО: {updated_count}")
            print("✨ КРУГ ЗАВЕРШЕН ПО ОБНОВЛЕННОЙ СИСТЕМЕ КЭША.")

        except Exception as e:
            print(f"⚠️ ОШИБКА: {e}")
            await asyncio.sleep(5)

async def boost_prices_at_night(sheet, pool, client: httpx.AsyncClient):
    """Функция для искусственного подъема цен в 05:00 утра для вытягивания врагов вверх"""
    now = datetime.datetime.now()
    
    if now.hour == 5 and 0 <= now.minute <= 2:
        print("🚀 УТРЕННИЙ ПОДЪЕМ ЦЕН (05:00): Вытягиваем конкурентов вверх...")
        
        mega_buffer = []
        boosted_count = 0

        for i in range(0, len(pool), BATCH_SIZE):
            batch = pool[i : i + BATCH_SIZE]
            api_data = await fetch_mget_data(client, batch)
            results_map = {str(p['id']): p.get('offers', []) for p in api_data}

            for b in batch:
                pid = b["pid"]
                offers = results_map.get(pid)
                row_raw = b["raw_data"]
                
                if not offers: 
                    continue

                enemies_exist = any(
                    (int((off.get('marketing_name') or off.get('seller_marketing_name') or {}).get('internal_id', 0)) != MY_SHOP_ID and
                     int((off.get('marketing_name') or off.get('seller_marketing_name') or {}).get('internal_id', 0)) not in FRIENDLY_SHOPS)
                    for off in offers
                )

                if enemies_exist:
                    try: limit_min = float(row_raw[5].replace(',', '.')) if row_raw[5] else 0.0
                    except: limit_min = 0.0
                    try: limit_max = float(row_raw[6].replace(',', '.')) if row_raw[6] else 0.0
                    except: limit_max = 0.0

                    if limit_min > 0:
                        if limit_max > 0:
                            new_target = limit_max
                        else:
                            new_target = round(limit_min * 1.20, 2)

                        mega_buffer.append({
                            'range': f'H{b["row"]}:I{b["row"]}', 
                            'values': [[str(new_target), "🚀 NIGHT BOOST"]]
                        })
                        mega_buffer.append({
                            'range': f'M{b["row"]}', 
                            'values': [["UPDATE_ON"]]
                        })
                        
                        SENT_PRICES_CACHE[pid] = new_target
                        boosted_count += 1

        if mega_buffer:
            try: 
                await asyncio.to_thread(sheet.batch_update, mega_buffer)
                print(f"✅ Подняли цены для {boosted_count} товаров. Спим 5 минут...")
                await asyncio.sleep(300)
            except Exception as e:
                print(f"⚠️ Ошибка при отправке ночного буста в таблицу: {e}")

if __name__ == "__main__":
    asyncio.run(run_repricer())