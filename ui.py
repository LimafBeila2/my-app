import flet as ft
import asyncio
import threading
import sys
import re
import socket
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import httpx

import core
import umico_token
import Top
import pusher
import where

class ConsoleStream:
    """Перенаправляет print() напрямую в лог Flet на экране телефона"""
    def __init__(self, callback):
        self.callback = callback

    def write(self, text):
        clean = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-9;]*[ -/]*[@-~])', '', text)
        if clean.strip():
            self.callback(clean)

    def flush(self):
        pass

def main(page: ft.Page):
    page.title = "BIRMARKET PREMIUM"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 12
    page.scroll = ft.ScrollMode.ADAPTIVE
    page.bgcolor = "#0D0D0D"

    is_running = {"val": False}

    # Индикаторы статуса
    net_dot = ft.Container(width=10, height=10, border_radius=5, bgcolor=ft.Colors.GREY)
    token_dot = ft.Container(width=10, height=10, border_radius=5, bgcolor=ft.Colors.GREY)
    
    billing_status_text = ft.Text("ПРОВЕРКА ДОСТУПА...", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY)
    billing_badge = ft.Container(
        content=billing_status_text,
        bgcolor="#1F1F1F",
        padding=10,
        border_radius=8,
        alignment=ft.alignment.center
    )

    # Виджеты счетчиков
    txt_total = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color="#569CD6")
    txt_first = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color="#FFD700")
    txt_updated = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color="#1DB954")

    def make_stat_card(title, value_widget):
        return ft.Container(
            content=ft.Column([
                ft.Text(title, size=10, color=ft.Colors.GREY_400),
                value_widget
            ], spacing=2),
            bgcolor="#1C1C1C",
            padding=10,
            border_radius=10,
            expand=True
        )

    stats_row = ft.Row([
        make_stat_card("ВСЕГО", txt_total),
        make_stat_card("1-Е МЕСТО", txt_first),
        make_stat_card("ОБНОВЛЕНО", txt_updated),
    ], spacing=8)

    # Консоль логов
    logs_col = ft.Column(spacing=2, scroll=ft.ScrollMode.ALWAYS)
    logs_container = ft.Container(
        content=logs_col,
        bgcolor="#080808",
        border_radius=10,
        padding=10,
        height=340,
        border=ft.border.all(1, "#262626")
    )

    def log_message(msg):
        msg_str = msg.strip()
        if "РАБОТЕ:" in msg_str:
            m = re.search(r'РАБОТЕ:\s*(\d+)', msg_str)
            if m: txt_total.value = m.group(1)
        elif "В:" in msg_str:
            m = re.search(r'В:\s*(\d+)', msg_str)
            if m: txt_first.value = m.group(1)
        elif "ОБНОВЛЕНО:" in msg_str:
            m = re.search(r'ОБНОВЛЕНО:\s*(\d+)', msg_str)
            if m: txt_updated.value = m.group(1)

        logs_col.controls.append(
            ft.Text(f"[{datetime.now().strftime('%H:%M:%S')}] {msg_str}", size=11, font_family="monospace", color="#E0E0E0")
        )
        if len(logs_col.controls) > 120:
            logs_col.controls.pop(0)
        page.update()

    sys.stdout = ConsoleStream(log_message)

    # Фоновая проверка соединения
    def check_network():
        while True:
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=3)
                net_dot.bgcolor = ft.Colors.GREEN_ACCENT
            except OSError:
                net_dot.bgcolor = ft.Colors.RED_ACCENT
            page.update()
            asyncio.run(asyncio.sleep(8))

    threading.Thread(target=check_network, daemon=True).start()

    # Фоновая проверка биллинга
    def check_billing():
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                core.SHEET_FILE, 
                ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            )
            gc = gspread.authorize(creds)
            sh = gc.open(core.BILLING_SHEET_NAME)
            sheet = sh.get_worksheet(0)
            data = sheet.get_all_values()
            shop_row = next((r for r in data[1:] if len(r) >= 5 and str(r[1]).strip() == str(core.MY_SHOP_ID)), None)
            if shop_row:
                date_str = shop_row[4].strip()
                expire_date = None
                for fmt in ("%d.%m.%Y", "%m.%d.%Y", "%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        expire_date = datetime.strptime(date_str, fmt)
                        break
                    except: continue
                if expire_date:
                    days_left = (expire_date - datetime.now()).days + 1
                    formatted_date = expire_date.strftime('%d.%m.%Y')
                    if days_left <= 0:
                        billing_status_text.value = f"ДОСТУП ИСТЕК: {formatted_date}"
                        billing_badge.bgcolor = "#331414"
                        billing_status_text.color = ft.Colors.RED
                    else:
                        billing_status_text.value = f"АКТИВЕН ДО: {formatted_date}"
                        billing_badge.bgcolor = "#143321"
                        billing_status_text.color = ft.Colors.GREEN
            page.update()
        except Exception:
            billing_status_text.value = "СВЯЗЬ С ТАБЛИЦЕЙ..."
            page.update()

    threading.Thread(target=check_billing, daemon=True).start()

    # Основной рабочий цикл бота
    async def worker_loop():
        circle = 1
        SYNC_INTERVAL = 40
        while is_running["val"]:
            print(f"🔄 ГЛОБАЛЬНЫЙ ЦИКЛ №{circle}")
            try:
                token_dot.bgcolor = ft.Colors.AMBER
                page.update()
                
                await asyncio.to_thread(umico_token.main_logic)
                token_dot.bgcolor = ft.Colors.GREEN_ACCENT
                page.update()

                creds = ServiceAccountCredentials.from_json_keyfile_name(
                    core.SHEET_FILE, 
                    ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                )
                gc = await asyncio.to_thread(gspread.authorize, creds)
                sh = await asyncio.to_thread(gc.open, 'Sirius')
                sheet = await asyncio.to_thread(sh.get_worksheet, 0)
                all_data = await asyncio.to_thread(sheet.get_all_values)

                # Ночной буст
                async with httpx.AsyncClient() as client:
                    current_pool = []
                    for i, r in enumerate(all_data[1:], 2):
                        if len(r) > 11 and "/product/" in r[4] and r[11] == "Satışda":
                            m = re.search(r'product/(\d+)', r[4])
                            if m: current_pool.append({"row": i, "pid": m.group(1), "raw_data": r})
                    await core.boost_prices_at_night(sheet, current_pool, client)

                # Синхронизация каталога
                if circle == 1 or circle % SYNC_INTERVAL == 0:
                    print("⚙️ ПЕРЕСБОРКА ТАБЛИЦЫ (Top Sync)...")
                    await Top.sync_with_google_sheets()

                # Репрайсинг
                await core.run_repricer()

                # Пушер
                all_data = await asyncio.to_thread(sheet.get_all_values)
                access_token = all_data[2][23]
                await pusher.start_update_process(access_token, all_data, sheet)

                print(f"✅ ЦИКЛ №{circle} ЗАВЕРШЕН!")
                circle += 1
                await asyncio.sleep(12)

            except Exception as e:
                print(f"⚠️ ОШИБКА В ЦИКЛЕ: {e}")
                token_dot.bgcolor = ft.Colors.RED
                page.update()
                await asyncio.sleep(15)

    def start_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(worker_loop())

    def toggle_run(e):
        if not is_running["val"]:
            is_running["val"] = True
            btn_start.text = "ОСТАНОВИТЬ"
            btn_start.bgcolor = ft.Colors.RED_700
            threading.Thread(target=start_thread, daemon=True).start()
        else:
            is_running["val"] = False
            btn_start.text = "ЗАПУСТИТЬ"
            btn_start.bgcolor = "#1DB954"
            print("🛑 Процесс остановлен.")
        page.update()

    def run_orders(e):
        def task():
            btn_orders.disabled = True
            btn_orders.text = "⏳ ЗАГРУЗКА..."
            page.update()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(where.track_all_orders())
            btn_orders.disabled = False
            btn_orders.text = "НОВЫЕ ЗАКАЗЫ"
            page.update()
        threading.Thread(target=task, daemon=True).start()

    btn_start = ft.ElevatedButton(
        "ЗАПУСТИТЬ",
        on_click=toggle_run,
        bgcolor="#1DB954",
        color=ft.Colors.WHITE,
        height=50,
        expand=True
    )
    btn_orders = ft.ElevatedButton(
        "НОВЫЕ ЗАКАЗЫ",
        on_click=run_orders,
        bgcolor="#262626",
        color=ft.Colors.WHITE,
        height=50,
        expand=True
    )

    page.add(
        ft.Row([
            ft.Text("BIRMARKET PREMIUM", size=18, weight=ft.FontWeight.BOLD, color="#EA207E"),
            ft.Row([
                ft.Text("NET:", size=10, color=ft.Colors.GREY), net_dot,
                ft.Text("SESSION:", size=10, color=ft.Colors.GREY), token_dot
            ], spacing=4)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        billing_badge,
        stats_row,
        ft.Row([btn_start, btn_orders], spacing=10),
        ft.Text("КОНСОЛЬ:", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_500),
        logs_container
    )

ft.app(target=main)