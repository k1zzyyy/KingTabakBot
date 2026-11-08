import asyncio
import os
import aiosqlite
import csv
import io
import aiohttp
import hashlib
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo
from collections import defaultdict
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL", "https://docs.google.com/spreadsheets/d/e/2PACX-1vRdmiCfg-6fTdd8PVGmKJQZgYUInzQodiRvZ5Ken1r2_Uh3SwbP87ZtuQwZ9Mcm6rRJ9cO7dh7Qso78/pub?output=csv")
ADMIN_IDS = [7088621971]

ADMIN_CODES = {
    "YURIY1494": "Юрий", "IGOR8546": "Игорь", "ANDREY2734": "Андрей",
    "MARYAM8975": "Марьям", "USIF2380": "Юсиф", "DANIIL9656": "Даниил",
    "ZAHAR777": "Захар"
}

POINTS_DATA = {
    "Л41": {"full": "Кинг Табак (Л41)", "address": "Лиговский проспект 41", "line": "Красная ветка", "station": "Площадь Восстания", "chat": "https://yandex.ru/chat/#/join/e7586022-f0c3-4f45-8e11-ebb2dc888cc1"},
    "Л43": {"full": "Кинг Табак (Л43)", "address": "Лиговский проспект 43", "line": "Красная ветка", "station": "Площадь Восстания", "chat": "https://yandex.ru/chat/#/join/df5a7902-2891-4c76-93d8-17beccd80d86"},
    "Л44": {"full": "Кинг Табак (Л44)", "address": "Лиговский проспект 44", "line": "Красная ветка", "station": "Площадь Восстания", "chat": "https://yandex.ru/chat/#/join/52a95507-9f66-433d-8cc1-6ed3e21fadb1"},
    "Л53": {"full": "Кинг Табак (Л53)", "address": "Лиговский проспект 53", "line": "Красная ветка", "station": "Площадь Восстания", "chat": "https://yandex.ru/chat/#/join/1248f57b-7ef4-4549-aa36-04b51539a189"},
    "Л84": {"full": "Кинг Табак (Л84)", "address": "Лиговский проспект 84", "line": "Оранжевая ветка", "station": "Лиговский проспект", "chat": "https://yandex.ru/chat/#/join/4323c784-4fda-4734-b22b-5bc60bf2d765"},
    "Л130": {"full": "Кинг Табак (Л130)", "address": "Лиговский проспект 130", "line": "Фиолетовая ветка", "station": "Обводный канал", "chat": "https://yandex.ru/chat/#/join/4d9967fe-e20b-4d7d-8ed2-db9721756c98"},
    "Н11": {"full": "Кинг Табак (Н11)", "address": "Невский проспект 11", "line": "Фиолетовая ветка", "station": "Адмиралтейская", "chat": "https://yandex.ru/chat/#/join/94252aa9-e6d0-4d55-9cdb-faa7f35c18bd"},
    "Н27": {"full": "Кинг Табак (Н27)", "address": "Невский проспект 27", "line": "Синяя ветка", "station": "Невский проспект", "chat": "https://yandex.ru/chat/#/join/13a4592f-496a-4016-8243-f0f12f25a8ad"},
    "Н54": {"full": "Кинг Табак (Н54)", "address": "Невский проспект 54", "line": "Зеленая ветка", "station": "Гостиный двор", "chat": "https://yandex.ru/chat/#/join/6efd9160-a7f4-4780-8455-4bbd4c5eaa94"},
    "Н69": {"full": "Кинг Табак (Н69)", "address": "Невский проспект 69", "line": "Зеленая ветка", "station": "Маяковская", "chat": "https://yandex.ru/chat/#/join/588df809-0493-41e1-8285-ce11139e030a"},
    "Н102": {"full": "Кинг Табак (Н102)", "address": "Невский проспект 102", "line": "Зеленая ветка", "station": "Маяковская", "chat": "https://yandex.ru/chat/#/join/3ce8a9be-9dd3-4198-94d3-4889c00e47ee"},
    "Н118": {"full": "Кинг Табак (Н118)", "address": "Невский проспект 118", "line": "Красная ветка", "station": "Площадь Восстания", "chat": "https://yandex.ru/chat/#/join/4ac26cc8-6e4e-42ac-a0dc-0788d901317b"},
    "Р1": {"full": "Кинг Табак (Р1)", "address": "Разъезжая 1", "line": "Красная ветка", "station": "Владимирская", "chat": "https://yandex.ru/chat/#/join/cf5a635e-72ef-48dc-a815-9f0167128d35"},
    "В17": {"full": "Кинг Табак (В17)", "address": "Владимирский 17", "line": "Красная ветка", "station": "Владимирская", "chat": "https://yandex.ru/chat/#/join/74b89069-67a4-41d3-a6cc-01bb56fed46a"},
    "ПС94": {"full": "Кинг Табак (ПС94)", "address": "Петроградская сторона 94", "line": "Синяя ветка", "station": "Петроградская", "chat": "https://yandex.ru/chat/#/join/450a4e98-0766-4187-96e8-1d8ded6aba0f"},
    "7ВО": {"full": "Кинг Табак (7ВО)", "address": "7 линия Васильевского острова", "line": "Зеленая ветка", "station": "Василеостровская", "chat": "https://yandex.ru/chat/#/join/5f4d3c21-0ca6-4b05-ad36-d76690243f89"},
    "8ВО": {"full": "Кинг Табак (8ВО)", "address": "8 линия Васильевского острова", "line": "Зеленая ветка", "station": "Василеостровская", "chat": "https://yandex.ru/chat/#/join/5c016f76-b479-4208-8cb8-6cd9f67285e0"},
    "ОД31": {"full": "Кинг Табак (ОД31)", "address": "Одоевского 31", "line": "Зеленая ветка", "station": "Приморская", "chat": "https://yandex.ru/chat/#/join/5d9f624d-66cb-4a24-8c40-9efcfbb32c0b"},
    "1К2": {"full": "Кинг Табак (1К2)", "address": "1я Красноармейская 2", "line": "Синяя ветка", "station": "Технологический институт", "chat": "https://yandex.ru/chat/#/join/6e61f44e-390b-4e85-8017-d6d1a9d21dab"},
    "ПП": {"full": "Кинг Табак (ПП)", "address": "Парк Победы", "line": "Синяя ветка", "station": "Парк Победы", "chat": "https://yandex.ru/chat/#/join/10a371b0-417e-4859-a2fe-3866ba5c85e7"},
    "М195": {"full": "Кинг Табак (М195)", "address": "Московский проспект 195", "line": "Синяя ветка", "station": "Московская", "chat": "https://yandex.ru/chat/#/join/dd077b12-355a-4fe2-a428-507b5efc8d6d"},
    "М197": {"full": "Кинг Табак (М197)", "address": "Московский проспект 197", "line": "Синяя ветка", "station": "Московская", "chat": "https://yandex.ru/chat/#/join/ee08d71a-f557-487a-98d6-63d03d89e1be"},
    "С38": {"full": "Кинг Табак (С38)", "address": "Садовая 38", "line": "Оранжевая ветка", "station": "Спасская", "chat": "https://yandex.ru/chat/#/join/0c66632c-aaa9-46e6-9368-bd84cb81a388"},
    "Б13": {"full": "Кинг Табак (Б13)", "address": "Большая Зеленина 13", "line": "Фиолетовая ветка", "station": "Чкаловская", "chat": "https://yandex.ru/chat/#/join/4c4536b5-2266-4c94-a9b2-0974f45a16ca"},
    "П19": {"full": "Кинг Табак (П19)", "address": "Проспект просвещения 19", "line": "Синяя ветка", "station": "Проспект просвещения", "chat": "https://yandex.ru/chat/#/join/113c02ad-219a-4e23-831c-b0d44caca9bc"},
    "К4": {"full": "Кинг Табак (К4)", "address": "Каменноостровский 4", "line": "Синяя ветка", "station": "Горьковская", "chat": "https://yandex.ru/chat/#/join/9099bb6f-f84f-4ac4-b13d-116837e1eeee"},
    "Л61КИО": {"full": "Кинг Табак (Лесная 61 Кио Кухня)", "address": "Лесной 61А", "line": "Красная ветка", "station": "Лесная", "chat": "https://yandex.ru/chat/#/join/46c266c8-2c3b-4752-8f33-8aff9b95f09f"},
    "К23": {"full": "Кинг Табак (Лесная павильон)", "address": "Лесная павильон", "line": "Красная ветка", "station": "Лесная", "chat": "https://yandex.ru/chat/#/join/7eb4d39b-1d61-4d49-8298-f12521a5905d"},
    "Л61ДОМ": {"full": "Кинг Табак (Лесная 61 Дом)", "address": "Лесная 61", "line": "Красная ветка", "station": "Лесная", "chat": "https://yandex.ru/chat/#/join/ba22d7f8-62f6-4f8b-a8d0-e2202d020ba3"},
    "Z6": {"full": "Кинг Табак (Звенигородская 6)", "address": "Звенигородская 6", "line": "Фиолетовая ветка", "station": "Звенигородская", "chat": "https://yandex.ru/chat/#/join/0703d062-8304-4762-a220-2e9f253465ad"},
    "К18": {"full": "Кинг Табак (Кирочная 18)", "address": "Кирочная 18", "line": "Красная ветка", "station": "Чернышевская", "chat": "https://yandex.ru/chat/#/join/827d95ed-22fd-4e4d-85fa-314b488a2402"}
}

def get_point_info(query):
    query_upper = query.strip().upper()
    if query_upper in POINTS_DATA: return query_upper, POINTS_DATA[query_upper]
    for key, pt in POINTS_DATA.items():
        if pt["address"].upper() in query_upper: return key, pt
    return None, None

async def fetch_live_names_from_sheet():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SHEET_CSV_URL) as response:
                if response.status != 200: return None
                text = await response.text()
        if "<html" in text.lower(): return None

        f = io.StringIO(text)
        delimiter = ',' if text.split('\n')[0].count(',') > text.split('\n')[0].count(';') else ';'
        rows = list(csv.reader(f, delimiter=delimiter))
        if len(rows) < 2: return None

        header_idx = -1
        for idx, row in enumerate(rows[:10]): 
            if any(d in " ".join(str(c).upper() for c in row) for d in ["ВТ", "СР", "ПН"]):
                header_idx = idx; break
        if header_idx == -1: return None

        col_to_day = {i: int(''.join(filter(str.isdigit, str(cell)))) for i, cell in enumerate(rows[header_idx]) if any(c.isdigit() for c in str(cell))}
        
        names_dict = {}
        for row in rows[header_idx + 1:]:
            if len(row) < 2: continue
            if row[0].strip(): curr_addr = row[0].strip()
            s_type = row[1].strip().capitalize() if len(row) > 1 else ""
            if s_type not in ("День", "Дневная", "Ночь", "Ночная"): continue 

            for col in col_to_day.keys():
                if col >= len(row): continue
                val = row[col].strip().replace('\xa0', ' ')
                if val and val not in ("⬆️", "⬇️", "↑", "↓") and not set(val).issubset({'-', '—', ' '}):
                    names_dict[val.lower()] = val
        return names_dict
    except Exception as e:
        print(f"Ошибка при скачивании таблицы: {e}")
        return None

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
MONTHS_RU = {1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь", 7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"}

class AuthState(StatesGroup):
    waiting_for_code = State()
class RegState(StatesGroup):
    waiting_for_name = State()
class PointState(StatesGroup):
    waiting_for_query = State()
class AddShiftState(StatesGroup):
    waiting_for_user = State()
    waiting_for_date = State()
    waiting_for_type = State()
    waiting_for_address = State()
    waiting_for_replaces = State()
    waiting_for_replaced_by = State()
class ImportState(StatesGroup):
    waiting_for_gsheet_date = State()
class AutoSyncState(StatesGroup):
    waiting_for_sync_date = State()
class DeleteUserState(StatesGroup):
    waiting_for_name = State()
class DeleteShiftState(StatesGroup):
    waiting_for_name = State()
    waiting_for_month = State()
class ChangeNameState(StatesGroup):
    waiting_for_new_name = State()
class TransactionState(StatesGroup):
    waiting_for_fine = State()
    waiting_for_bonus = State()
class SellerListState(StatesGroup):
    waiting_for_add_name = State()
    waiting_for_remove_name = State()

async def init_db():
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, name TEXT, role TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (telegram_id INTEGER PRIMARY KEY, name TEXT, code TEXT UNIQUE)")
        await db.execute("CREATE TABLE IF NOT EXISTS shifts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, date TEXT, shift_type TEXT, address TEXT, replaces TEXT, replaced_by TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount INTEGER, date TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS valid_names (name TEXT PRIMARY KEY)")
        await db.commit()

async def get_setting(key):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(key, value):
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def get_schedule_text():
    last_month, last_year = await get_setting("last_loaded_month"), await get_setting("last_loaded_year")
    if last_month and last_year:
        try: return f"{MONTHS_RU.get(int(last_month), last_month).lower()} {last_year}"
        except ValueError: return "неизвестно"
    return "пока не загружено"

async def get_user(telegram_id):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT name, role FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def get_admin(telegram_id):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT name FROM admins WHERE telegram_id = ?", (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def get_admin_by_code(code):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT telegram_id FROM admins WHERE code = ?", (code,)) as cursor:
            return await cursor.fetchone()

async def save_admin(telegram_id, name, code):
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("INSERT OR REPLACE INTO admins (telegram_id, name, code) VALUES (?, ?, ?)", (telegram_id, name, code))
        await db.commit()

async def get_user_by_name(name):
    clean_name = str(name).strip().replace('\xa0', ' ').lower()
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT telegram_id, name FROM users") as cursor:
            all_users = await cursor.fetchall()
            for uid, db_name in all_users:
                if clean_name in db_name.lower():
                    return (uid, db_name)
            return None

async def save_user(telegram_id, name, role):
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("INSERT OR REPLACE INTO users (telegram_id, name, role) VALUES (?, ?, ?)", (telegram_id, name, role))
        await db.commit()

async def update_user_role(telegram_id, new_role):
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (new_role, telegram_id))
        await db.commit()

async def update_user_name(telegram_id, new_name):
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("UPDATE users SET name = ? WHERE telegram_id = ?", (new_name, telegram_id))
        await db.commit()

async def delete_user_from_db(telegram_id):
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        await db.execute("DELETE FROM shifts WHERE user_id = ?", (telegram_id,))
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT telegram_id, name, role FROM users") as cursor:
            return await cursor.fetchall()

async def get_next_shift(user_id):
    now = datetime.now(MOSCOW_TZ)
    today_str = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT date, shift_type, address, replaces, replaced_by FROM shifts WHERE user_id = ? AND date >= ? ORDER BY date ASC", (user_id, today_str)) as cursor:
            shifts = await cursor.fetchall()
    for s in shifts:
        s_date, s_type, addr, repl, repl_by = s
        start_hour = 10 if "День" in s_type else 22
        s_dt = datetime.strptime(f"{s_date} {start_hour}:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=MOSCOW_TZ)
        if now < s_dt: return s
    return None

async def get_user_shifts_months(user_id):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT DISTINCT substr(date, 1, 7) FROM shifts WHERE user_id = ? ORDER BY date DESC", (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_user_shifts_by_month(user_id, year_month):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT id, date, shift_type, address, replaces, replaced_by FROM shifts WHERE user_id = ? AND date LIKE ? ORDER BY date", (user_id, f"{year_month}-%")) as cursor:
            return await cursor.fetchall()

async def delete_shift_by_id(shift_id):
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))
        await db.commit()

async def clear_shifts_for_month(month, year):
    prefix = f"{year}-{month:02d}-%"
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("DELETE FROM shifts WHERE date LIKE ?", (prefix,))
        await db.commit()

async def add_transaction(user_id, t_type, amount, date_str):
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("INSERT INTO transactions (user_id, type, amount, date) VALUES (?, ?, ?, ?)", (user_id, t_type, amount, date_str))
        await db.commit()

async def get_transactions_sum(user_id, start_date, end_date, t_type):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = ? AND date >= ? AND date <= ?", (user_id, t_type, start_date, end_date)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result[0] else 0

async def daily_closing_reminder_worker():
    while True:
        now = datetime.now(MOSCOW_TZ)
        target_time = time(21, 45, 0)
        target_datetime = datetime.combine(now.date(), target_time, MOSCOW_TZ)
        if now >= target_datetime: target_datetime += timedelta(days=1)
        await asyncio.sleep((target_datetime - now).total_seconds())
        try:
            today_str = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
            async with aiosqlite.connect("king_tabak.db") as db:
                async with db.execute("SELECT DISTINCT user_id FROM shifts WHERE date = ? AND (shift_type LIKE '%День%' OR shift_type = 'Дневная')", (today_str,)) as cursor:
                    users = await cursor.fetchall()
            for (uid,) in users:
                try:
                    await bot.send_message(uid, "⏰ <b>Напоминание!</b>\n\nКоллеги, не забудьте закрыть смену ровно в 22:00!", parse_mode="HTML")
                    await asyncio.sleep(0.1)
                except: pass
        except: pass
        await asyncio.sleep(60)

async def shift_reminders_worker():
    last_day, last_night = None, None
    while True:
        now = datetime.now(MOSCOW_TZ)
        if now.hour == 16 and now.minute < 5 and last_day != now.date():
            last_day = now.date()
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            async with aiosqlite.connect("king_tabak.db") as db:
                async with db.execute("SELECT user_id, address FROM shifts WHERE date = ? AND (shift_type LIKE '%День%' OR shift_type = 'Дневная')", (tomorrow,)) as cursor:
                    shifts = await cursor.fetchall()
            for uid, addr in shifts:
                try:
                    await bot.send_message(uid, f"☀️ Привет! Завтра в 10:00 у тебя смена на точке <b>{addr}</b>", parse_mode="HTML")
                    await asyncio.sleep(0.1)
                except: pass
        if now.hour == 12 and now.minute < 5 and last_night != now.date():
            last_night = now.date()
            today = now.strftime("%Y-%m-%d")
            async with aiosqlite.connect("king_tabak.db") as db:
                async with db.execute("SELECT user_id, address FROM shifts WHERE date = ? AND (shift_type LIKE '%Ночь%' OR shift_type = 'Ночная')", (today,)) as cursor:
                    shifts = await cursor.fetchall()
            for uid, addr in shifts:
                try:
                    await bot.send_message(uid, f"🌙 Привет! Сегодня в 22:00 у тебя смена на точке <b>{addr}</b>", parse_mode="HTML")
                    await asyncio.sleep(0.1)
                except: pass
        await asyncio.sleep(60)

async def process_and_save_sheet(month, year, is_auto=False, notify_users=True):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SHEET_CSV_URL) as response:
                if response.status != 200: return False, "Ошибка Google."
                text = await response.text()
        if "<html" in text.lower(): return False, "Не CSV."

        current_hash = hashlib.md5(text.encode()).hexdigest()
        if await get_setting("last_sheet_hash") == current_hash and is_auto: return True, "Без изменений."

        f = io.StringIO(text)
        delimiter = ',' if text.split('\n')[0].count(',') > text.split('\n')[0].count(';') else ';'
        rows = list(csv.reader(f, delimiter=delimiter))
        if len(rows) < 2: return False, "Пустая таблица."

        header_idx = -1
        for idx, row in enumerate(rows[:10]): 
            if any(d in " ".join(str(c).upper() for c in row) for d in ["ВТ", "СР", "ПН"]):
                header_idx = idx; break
        if header_idx == -1: return False, "Нет заголовков."

        col_to_day = {i: int(''.join(filter(str.isdigit, str(cell)))) for i, cell in enumerate(rows[header_idx]) if any(c.isdigit() for c in str(cell))}
        
        parsed_shifts, missing_names, all_names = [], set(), set()
        curr_addr = ""
        
        async with aiosqlite.connect("king_tabak.db") as db:
            async with db.execute("SELECT telegram_id, name FROM users") as cursor:
                all_users_db = await cursor.fetchall()
                users_dict = {db_name.lower().strip(): (uid, db_name) for uid, db_name in all_users_db}

        for row in rows[header_idx + 1:]:
            if len(row) < 2: continue
            if row[0].strip(): curr_addr = row[0].strip()
            s_type = row[1].strip().capitalize() if len(row) > 1 else ""
            if s_type not in ("День", "Дневная", "Ночь", "Ночная"): continue 

            for col, day in col_to_day.items():
                if col >= len(row): continue
                val = row[col].strip().replace('\xa0', ' ')
                if val and val not in ("⬆️", "⬇️", "↑", "↓") and not set(val).issubset({'-', '—', ' '}):
                    all_names.add(val)
                    clean_val = val.lower()
                    user_info = None
                    for db_lower, u_info in users_dict.items():
                        if db_lower in clean_val or clean_val in db_lower:
                            user_info = u_info
                            break
                    if not user_info: missing_names.add(val)
                    try:
                        parsed_shifts.append({
                            'user_id': user_info[0] if user_info else None, 
                            'name': val, 
                            'date': datetime(year, month, day).strftime("%Y-%m-%d"), 
                            'type': s_type, 
                            'addr': curr_addr
                        })
                    except: pass

        if all_names:
            async with aiosqlite.connect("king_tabak.db") as db:
                for n in all_names: await db.execute("INSERT OR IGNORE INTO valid_names (name) VALUES (?)", (n,))
                await db.commit()

        locs = defaultdict(list)
        for s in parsed_shifts: locs[s['addr']].append(s)

        new_shifts_data = {}
        insert_data = []
        for addr, shifts in locs.items():
            shifts.sort(key=lambda x: (x['date'], 0 if "День" in x['type'] else 1)) 
            for i in range(len(shifts)):
                if shifts[i]['user_id']:
                    shift_tuple = (
                        shifts[i]['date'], shifts[i]['type'], shifts[i]['addr'],
                        shifts[i-1]['name'] if i > 0 else "-",
                        shifts[i+1]['name'] if i < len(shifts) - 1 else "-"
                    )
                    insert_data.append((shifts[i]['user_id'],) + shift_tuple)
                    uid = shifts[i]['user_id']
                    if uid not in new_shifts_data: new_shifts_data[uid] = set()
                    new_shifts_data[uid].add(shift_tuple)

        if not insert_data:
            return False, "❌ Импорт отменен: не найдено ни одной смены для зарегистрированных пользователей.\n\nСмены за этот месяц НЕ удалены."

        old_shifts_data = {}
        async with aiosqlite.connect("king_tabak.db") as db:
            async with db.execute("SELECT user_id, date, shift_type, address, replaces, replaced_by FROM shifts WHERE date LIKE ?", (f"{year}-{month:02d}-%",)) as cursor:
                for row in await cursor.fetchall():
                    uid = row[0]
                    if uid not in old_shifts_data: old_shifts_data[uid] = set()
                    old_shifts_data[uid].add(row[1:])

        await clear_shifts_for_month(month, year)
        
        async with aiosqlite.connect("king_tabak.db") as db:
            await db.executemany("INSERT INTO shifts (user_id, date, shift_type, address, replaces, replaced_by) VALUES (?, ?, ?, ?, ?, ?)", insert_data)
            await db.commit()

        await set_setting("last_sheet_hash", current_hash)
        await set_setting("last_loaded_month", str(month))
        await set_setting("last_loaded_year", str(year))
        
        if notify_users:
            notified_users = set()
            all_uids = set(old_shifts_data.keys()).union(set(new_shifts_data.keys()))
            for uid in all_uids:
                if old_shifts_data.get(uid, set()) != new_shifts_data.get(uid, set()):
                    notified_users.add(uid)
                    
            for uid in notified_users:
                try: await bot.send_message(uid, "🔔 <b>Внимание!</b> Твое расписание изменилось. Проверь смены!", parse_mode="HTML")
                except: pass

        msg = f"✅ Импорт завершен! Смен: {len(insert_data)}."
        if missing_names and notify_users: msg += f"\n⚠️ Нет в базе: {', '.join(list(missing_names)[:10])}..."
        return True, msg
    except Exception as e: return False, str(e)

async def auto_sync_worker():
    while True:
        await asyncio.sleep(600) 
        try:
            m, y = await get_setting("sync_month"), await get_setting("sync_year")
            if m and y: await process_and_save_sheet(int(m), int(y), is_auto=True)
        except: pass

def get_main_menu(is_admin=False):
    kb = [
        [KeyboardButton(text="📅 Мои смены"), KeyboardButton(text="⏰ Ближайшая смена")],
        [KeyboardButton(text="💰 Зарплата"), KeyboardButton(text="👤 Личный кабинет")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="🗺 Точки")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)

def get_salary_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔻 Штраф"), KeyboardButton(text="🔺 Докид")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ], resize_keyboard=True)

def get_cabinet_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📈 Сменить ставку"), KeyboardButton(text="✏️ Сменить фамилию")],
        [KeyboardButton(text="👑 Войти как админ")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ], resize_keyboard=True)

def get_cancel_point_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Назад в меню")]], resize_keyboard=True)

def get_start_inline_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Продавец", callback_data="role_seller")
    builder.button(text="👑 Админ", callback_data="role_admin")
    builder.adjust(2)
    return builder.as_markup()

def get_admin_inline_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить смену", callback_data="adm_add_shift")
    builder.button(text="❌ Удалить смену", callback_data="adm_delete_shift")
    builder.button(text="❌ Удалить пользователя", callback_data="adm_delete_user")
    builder.button(text="👥 Список продавцов", callback_data="adm_list_sellers") 
    builder.button(text="⚡ Авто-синхронизация", callback_data="adm_toggle_auto")
    builder.button(text="🔄 Загрузить вручную", callback_data="adm_import_gsheet")
    builder.button(text="🔙 Закрыть меню", callback_data="adm_back")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if user:
        name, role = user
        try: rate_val = int(role)
        except: rate_val = 0
        is_admin = bool(await get_admin(message.from_user.id))
        sched_info = await get_schedule_text()
        await message.answer(f"Привет!\nРасписание: <b>{sched_info}</b>\nТвоя ставка: <b>{rate_val} ₽</b>.", reply_markup=get_main_menu(is_admin), parse_mode="HTML")
        return

    admin = await get_admin(message.from_user.id)
    if admin:
        await message.answer(f"Привет, {admin[0]}!", reply_markup=get_admin_inline_kb())
        return

    await message.answer("Привет! Я бот расписания сети Кинг Табак.\n\n<b>Кто ты?</b>", reply_markup=get_start_inline_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "role_seller")
async def cb_role_seller(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="role_back")
    await callback.message.edit_text("Напиши свою <b>Фамилию</b> (как в таблице):", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(RegState.waiting_for_name)
    await callback.answer()

@dp.callback_query(F.data == "role_admin")
async def cb_role_admin(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="role_back")
    await callback.message.edit_text("Введи <b>специальный код администратора</b>:", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(AuthState.waiting_for_code)
    await callback.answer()

@dp.callback_query(F.data == "role_back")
async def cb_role_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Привет! Я бот расписания сети Кинг Табак.\n\n<b>Кто ты?</b>", reply_markup=get_start_inline_kb(), parse_mode="HTML")
    await callback.answer()

@dp.message(F.text == "👑 Войти как админ")
async def btn_login_as_admin(message: types.Message, state: FSMContext):
    admin = await get_admin(message.from_user.id)
    if admin:
        await message.answer(f"Ты уже авторизован как {admin[0]}!", reply_markup=get_admin_inline_kb())
        return
    await message.answer("Введи <b>специальный код администратора</b>:", parse_mode="HTML")
    await state.set_state(AuthState.waiting_for_code)

@dp.message(AuthState.waiting_for_code)
async def process_admin_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if code not in ADMIN_CODES:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад", callback_data="role_back")
        await message.answer("❌ Неверный код администратора. Попробуй еще раз или вернись назад.", reply_markup=builder.as_markup())
        return
    name = ADMIN_CODES[code]
    bound_admin = await get_admin_by_code(code)
    if bound_admin and bound_admin[0] != message.from_user.id:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад", callback_data="role_back")
        await message.answer("❌ Этот код уже привязан к другому аккаунту!", reply_markup=builder.as_markup())
        await state.clear()
        return
    await save_admin(message.from_user.id, name, code)
    await message.answer(f"Привет, {name}! Ты успешно авторизован.", reply_markup=get_admin_inline_kb())
    await state.clear()

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    admin = await get_admin(message.from_user.id)
    if not admin:
        await message.answer("Введи <b>специальный код администратора</b>:", parse_mode="HTML")
        await state.set_state(AuthState.waiting_for_code)
        return
    await state.clear()
    await message.answer("⚙️ <b>Админ-панель</b>", reply_markup=get_admin_inline_kb(), parse_mode="HTML")

@dp.message(RegState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_input = message.text.strip().replace('\xa0', ' ')
    msg = await message.answer("⏳ Проверяю фамилию в базе...")
    
    clean_input = user_input.lower()
    matched_name = None
    
    live_names = await fetch_live_names_from_sheet()
    if live_names is not None:
        for name_lower, name_orig in live_names.items():
            if clean_input == name_lower or clean_input in name_lower:
                matched_name = name_orig
                break
                
    if not matched_name:
        async with aiosqlite.connect("king_tabak.db") as db:
            async with db.execute("SELECT name FROM valid_names") as cursor:
                db_names = await cursor.fetchall()
                for (db_name,) in db_names:
                    if clean_input == db_name.lower() or clean_input in db_name.lower():
                        matched_name = db_name
                        break

    if not matched_name:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад", callback_data="role_back")
        await msg.edit_text("❌ <b>Что-то пошло не так.</b>\nФамилия не найдена в расписании.", reply_markup=builder.as_markup(), parse_mode="HTML")
        return

    await msg.edit_text(f"✅ <b>Успешная регистрация!</b>\nТвоя фамилия найдена: {matched_name}")
    
    await state.update_data(name=matched_name)
    kb = [[KeyboardButton(text="2800 ₽"), KeyboardButton(text="3100 ₽"), KeyboardButton(text="3500 ₽")]]
    await message.answer("Выбери свою ставку:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.in_(["2800 ₽", "3100 ₽", "3500 ₽"]))
async def process_role(message: types.Message, state: FSMContext):
    if await state.get_state() != RegState.waiting_for_name.state: return
    role = message.text.replace(" ₽", "")
    user_data = await state.get_data()
    name = user_data.get("name")
    await save_user(message.from_user.id, name, role)
    m, y = await get_setting("last_loaded_month"), await get_setting("last_loaded_year")
    if m and y:
        await message.answer("⏳ Подгружаю смены...")
        await process_and_save_sheet(int(m), int(y), is_auto=False, notify_users=False)
    await message.answer(f"Регистрация завершена!\nФамилия: {name}\nТвоя ставка: <b>{role} ₽</b>", reply_markup=get_main_menu(False), parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "🔙 Назад в меню")
async def cmd_back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    is_admin = bool(await get_admin(message.from_user.id))
    await message.answer("Главное меню:", reply_markup=get_main_menu(is_admin))

@dp.message(F.text == "🗺 Точки")
async def btn_points(message: types.Message, state: FSMContext):
    is_admin = bool(await get_admin(message.from_user.id))
    if not is_admin: return 
    
    await message.answer("Введи сокращенное название точки (например: Н27, Л44):", reply_markup=get_cancel_point_menu())
    await state.set_state(PointState.waiting_for_query)

@dp.message(PointState.waiting_for_query)
async def process_point_query(message: types.Message, state: FSMContext):
    is_admin = bool(await get_admin(message.from_user.id))
    if not is_admin: return
    
    query = message.text.strip().replace('\xa0', ' ')
    key, pt = get_point_info(query)
    
    if pt:
        text = (f"🗺 <b>Информация о точке {key}</b>\n\n"
                f"🏢 <b>Название:</b> {pt['full']}\n"
                f"📍 <b>Адрес:</b> {pt['address']}\n"
                f"🚇 <b>Ветка:</b> {pt['line']}\n"
                f"🚉 <b>Станция:</b> {pt['station']}\n"
                f"💬 <b>Чат:</b> {pt['chat']}")
        await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu(True))
    else:
        await message.answer(f"❌ Точка <b>{query}</b> не найдена в базе. Проверь название.", parse_mode="HTML")
        
    await state.clear()

@dp.message(F.text == "📅 Мои смены")
async def btn_my_shifts(message: types.Message):
    months = await get_user_shifts_months(message.from_user.id)
    if not months: return await message.answer("У тебя пока нет смен.")
    kb, row = [], []
    for (ym,) in months:
        y, m = ym.split("-")
        row.append(KeyboardButton(text=f"{MONTHS_RU.get(int(m), m)} {y}"))
        if len(row) == 2: kb.append(row); row = []
    if row: kb.append(row)
    kb.append([KeyboardButton(text="🔙 Назад в меню")])
    await message.answer("Выбери месяц:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.regexp(r"^(Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь) \d{4}$"))
async def btn_my_shifts_month(message: types.Message):
    m_name, y = message.text.split()
    m_num = list(MONTHS_RU.keys())[list(MONTHS_RU.values()).index(m_name)]
    shifts = await get_user_shifts_by_month(message.from_user.id, f"{y}-{m_num:02d}")
    if not shifts: return await message.answer("Смен нет.")
    text = f"📅 <b>Смены за {m_name} {y}:</b>\n\n"
    for s in shifts:
        text += f"📆 {s[1]} ({s[2]})\n📍 {s[3]}\n🔄 Сменяю: {s[4]}\n👤 Сменяет: {s[5]}\n\n"
    await message.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📅 Другой месяц")], [KeyboardButton(text="🔙 Назад в меню")]], resize_keyboard=True))

@dp.message(F.text == "📅 Другой месяц")
async def btn_another_month(message: types.Message): await btn_my_shifts(message)

@dp.message(F.text == "⏰ Ближайшая смена")
async def btn_next_shift(message: types.Message):
    shift = await get_next_shift(message.from_user.id)
    if not shift: return await message.answer("Предстоящих смен нет.")
    
    date_str, s_type, addr, repl, repl_by = shift
    text = (f"⏰ <b>Ближайшая смена:</b>\n\n📆 {date_str}\n🕒 {s_type}\n📍 {addr}\n🔄 Сменяешь: {repl}\n👤 Сменяет: {repl_by}")
    
    is_admin = bool(await get_admin(message.from_user.id))
    if is_admin:
        builder = InlineKeyboardBuilder()
        builder.button(text="🗺 Инфо о точке", callback_data=f"point_info_{addr}")
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    else:
        await message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data.startswith("point_info_"))
async def cb_point_info(callback: types.CallbackQuery):
    is_admin = bool(await get_admin(callback.from_user.id))
    if not is_admin:
        await callback.answer("У вас нет прав для просмотра этой информации.", show_alert=True)
        return
        
    query = callback.data.replace("point_info_", "").strip().replace('\xa0', ' ')
    key, pt = get_point_info(query)
    
    if pt:
        text = (f"🗺 <b>Информация о точке {key}</b>\n\n"
                f"🏢 <b>Название:</b> {pt['full']}\n"
                f"📍 <b>Адрес:</b> {pt['address']}\n"
                f"🚇 <b>Ветка:</b> {pt['line']}\n"
                f"🚉 <b>Станция:</b> {pt['station']}\n"
                f"💬 <b>Чат:</b> {pt['chat']}")
        await callback.message.answer(text, parse_mode="HTML")
    else:
        await callback.message.answer(f"❌ Информация о точке <b>{query}</b> пока не добавлена в базу.", parse_mode="HTML")
    
    await callback.answer()

@dp.message(F.text == "💰 Зарплата")
async def btn_salary(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user: return
    today = date.today()
    if 10 <= today.day < 25: start, end = today.replace(day=10), today.replace(day=25)
    elif today.day >= 25: start = today.replace(day=25); end = date(today.year+1,1,10) if today.month==12 else date(today.year,today.month+1,10)
    else: start = date(today.year-1,12,25) if today.month==1 else date(today.year,today.month-1,25); end = today.replace(day=10)

    s_str, e_str = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    e_inc = (end - timedelta(days=1)).strftime("%Y-%m-%d")
    
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT COUNT(*) FROM shifts WHERE user_id = ? AND date >= ? AND date < ?", (message.from_user.id, s_str, e_str)) as cur:
            count = (await cur.fetchone())[0]

    try: rate = int(user[1])
    except: rate = 0
    base = count * rate
    fines = await get_transactions_sum(message.from_user.id, s_str, e_inc, "fine")
    bonuses = await get_transactions_sum(message.from_user.id, s_str, e_inc, "bonus")
    
    text = (f"💳 <b>Расчетный лист</b>\n━━━━━━━━━━━━━━━━━━━━\n🗓 {start.strftime('%d.%m')} — {(end-timedelta(days=1)).strftime('%d.%m')}\n"
            f"💸 Выплата: <b>{end.strftime('%d.%m.%Y')}</b>\n\n🕒 Смен: <b>{count}</b>\n💵 Ставка: <b>{rate} ₽</b>\n⚙️ Оклад: <b>{base} ₽</b>\n\n"
            f"🔻 Штрафы: <b>-{fines} ₽</b>\n🔺 Докиды: <b>+{bonuses} ₽</b>\n━━━━━━━━━━━━━━━━━━━━\n💰 <b>К ВЫПЛАТЕ: {base - fines + bonuses} ₽</b>")
    await message.answer(text, parse_mode="HTML", reply_markup=get_salary_menu())

@dp.message(F.text == "🔻 Штраф")
async def btn_add_fine(message: types.Message, state: FSMContext):
    await message.answer("Введи сумму штрафа:")
    await state.set_state(TransactionState.waiting_for_fine)

@dp.message(TransactionState.waiting_for_fine)
async def process_fine(message: types.Message, state: FSMContext):
    try: amount = int(message.text.strip())
    except: return await message.answer("Ошибка. Введи число.")
    await add_transaction(message.from_user.id, "fine", amount, date.today().strftime("%Y-%m-%d"))
    await message.answer(f"✅ Штраф {amount} ₽ применен.", reply_markup=get_salary_menu())
    await state.clear()

@dp.message(F.text == "🔺 Докид")
async def btn_add_bonus(message: types.Message, state: FSMContext):
    await message.answer("Введи сумму докида:")
    await state.set_state(TransactionState.waiting_for_bonus)

@dp.message(TransactionState.waiting_for_bonus)
async def process_bonus(message: types.Message, state: FSMContext):
    try: amount = int(message.text.strip())
    except: return await message.answer("Ошибка. Введи число.")
    await add_transaction(message.from_user.id, "bonus", amount, date.today().strftime("%Y-%m-%d"))
    await message.answer(f"✅ Докид {amount} ₽ добавлен.", reply_markup=get_salary_menu())
    await state.clear()

@dp.message(F.text == "👤 Личный кабинет")
async def btn_cabinet(message: types.Message):
    await message.answer("👤 <b>Личный кабинет</b>", reply_markup=get_cabinet_menu(), parse_mode="HTML")

@dp.message(F.text == "📈 Сменить ставку")
async def btn_change_rate(message: types.Message):
    kb = [[KeyboardButton(text="2800 ₽"), KeyboardButton(text="3100 ₽"), KeyboardButton(text="3500 ₽")], [KeyboardButton(text="🔙 Назад в меню")]]
    await message.answer("Выбери новую ставку:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "✏️ Сменить фамилию")
async def btn_change_name(message: types.Message, state: FSMContext):
    await message.answer("Введи новую фамилию:")
    await state.set_state(ChangeNameState.waiting_for_new_name)

@dp.message(ChangeNameState.waiting_for_new_name)
async def process_change_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip().replace('\xa0', ' ')
    msg = await message.answer("⏳ Проверяю фамилию в базе...")
    
    clean_input = new_name.lower()
    matched_name = None
    
    live_names = await fetch_live_names_from_sheet()
    if live_names is not None:
        for name_lower, name_orig in live_names.items():
            if clean_input == name_lower or clean_input in name_lower:
                matched_name = name_orig
                break
                
    if not matched_name:
        async with aiosqlite.connect("king_tabak.db") as db:
            async with db.execute("SELECT name FROM valid_names") as cursor:
                db_names = await cursor.fetchall()
                for (db_name,) in db_names:
                    if clean_input == db_name.lower() or clean_input in db_name.lower():
                        matched_name = db_name
                        break

    if not matched_name:
        return await msg.edit_text("❌ <b>Что-то пошло не так.</b>\nФамилия не найдена в расписании.", parse_mode="HTML")

    await update_user_name(message.from_user.id, matched_name)
    is_admin = bool(await get_admin(message.from_user.id))
    await msg.edit_text(f"✅ Фамилия изменена на <b>{matched_name}</b>!", reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "adm_back")
async def cb_adm_back(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data == "adm_toggle_auto")
async def cb_adm_toggle_auto(callback: types.CallbackQuery, state: FSMContext):
    m = await get_setting("sync_month")
    if m:
        await set_setting("sync_month", ""); await set_setting("sync_year", "")
        await callback.message.edit_text("❌ Автосинхронизация выключена.", reply_markup=get_admin_inline_kb())
    else:
        await callback.message.edit_text("Введи месяц и год (напр. 10 2026):")
        await state.set_state(AutoSyncState.waiting_for_sync_date)
    await callback.answer()

@dp.message(AutoSyncState.waiting_for_sync_date)
async def process_auto_date(message: types.Message, state: FSMContext):
    try:
        m, y = map(int, message.text.split())
        await set_setting("sync_month", str(m)); await set_setting("sync_year", str(y))
        _, msg = await process_and_save_sheet(m, y, is_auto=False)
        await message.answer(f"✅ Автосинхронизация на {m:02d}.{y}\n{msg}", reply_markup=get_admin_inline_kb())
    except: await message.answer("Ошибка формата.")
    await state.clear()

@dp.callback_query(F.data == "adm_import_gsheet")
async def cb_adm_import(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи месяц и год (напр. 10 2026):")
    await state.set_state(ImportState.waiting_for_gsheet_date)
    await callback.answer()

@dp.message(ImportState.waiting_for_gsheet_date)
async def process_import_date(message: types.Message, state: FSMContext):
    try: m, y = map(int, message.text.split())
    except: return await message.answer("Ошибка формата.")
    await message.answer("⏳ Скачиваю...")
    _, msg = await process_and_save_sheet(m, y, is_auto=False)
    await message.answer(msg, reply_markup=get_admin_inline_kb())
    await state.clear()

@dp.callback_query(F.data == "adm_list_sellers")
async def cb_adm_list_sellers(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS and not await get_admin(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return
        
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT name FROM valid_names") as cursor:
            all_names = [row[0] for row in await cursor.fetchall()]
            
        async with db.execute("SELECT name FROM users") as cursor:
            registered_users = [row[0].lower() for row in await cursor.fetchall()]
            
    if not all_names:
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Внести фамилию", callback_data="adm_add_name")
        builder.button(text="🔙 Назад", callback_data="admin_panel")
        await callback.message.edit_text("Список пуст. Сначала загрузите расписание или добавьте вручную.", reply_markup=builder.as_markup())
        return

    reg_names = []
    unreg_names = []
    
    for name in all_names:
        is_reg = any(name.lower() in reg or reg in name.lower() for reg in registered_users)
        if is_reg:
            reg_names.append(name)
        else:
            unreg_names.append(name)
            
    reg_names.sort()
    unreg_names.sort()
    
    text = "👥 <b>Список продавцов:</b>\n\n"
    if reg_names:
        text += "<b>✅ Зарегистрированы:</b>\n"
        for name in reg_names:
            text += f"• {name}\n"
        text += "\n"
    
    if unreg_names:
        text += "<b>❌ Не зарегистрированы:</b>\n"
        for name in unreg_names:
            text += f"• {name}\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Внести фамилию", callback_data="adm_add_name")
    builder.button(text="➖ Исключить фамилию", callback_data="adm_remove_name")
    builder.button(text="🔙 Назад", callback_data="admin_panel")
    builder.adjust(2, 1)

    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await callback.message.answer(part, parse_mode="HTML")
        await callback.message.answer("Управление списком:", reply_markup=builder.as_markup())
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
    await callback.answer()

@dp.callback_query(F.data == "adm_add_name")
async def cb_adm_add_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи фамилию, которую нужно внести в список (в неавторизованные):")
    await state.set_state(SellerListState.waiting_for_add_name)
    await callback.answer()

@dp.message(SellerListState.waiting_for_add_name)
async def process_add_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip().replace('\xa0', ' ')
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("INSERT OR IGNORE INTO valid_names (name) VALUES (?)", (new_name,))
        await db.commit()
    
    await message.answer(f"✅ Фамилия <b>{new_name}</b> добавлена в базу неавторизованных.", parse_mode="HTML")
    await state.clear()
    await cb_adm_list_sellers(message)

@dp.callback_query(F.data == "adm_remove_name")
async def cb_adm_remove_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи фамилию, которую нужно исключить из базы:")
    await state.set_state(SellerListState.waiting_for_remove_name)
    await callback.answer()

@dp.message(SellerListState.waiting_for_remove_name)
async def process_remove_name(message: types.Message, state: FSMContext):
    rem_name = message.text.strip().replace('\xa0', ' ')
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("DELETE FROM valid_names WHERE LOWER(name) LIKE ?", (f"%{rem_name.lower()}%",))
        await db.commit()
    
    await message.answer(f"✅ Фамилия <b>{rem_name}</b> удалена из базы.", parse_mode="HTML")
    await state.clear()
    await cb_adm_list_sellers(message)

@dp.callback_query(F.data == "adm_delete_user")
async def cb_adm_del_user(callback: types.CallbackQuery, state: FSMContext):
    users = await get_all_users()
    text = "Пользователи:\n" + "\n".join([f"• {u[1]} ({u[2]}₽)" for u in users])
    await callback.message.edit_text(f"{text}\n\nВведи фамилию для удаления (или 'Отмена'):")
    await state.set_state(DeleteUserState.waiting_for_name)
    await callback.answer()

@dp.message(DeleteUserState.waiting_for_name)
async def process_del_user(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена": return await cmd_admin(message, state)
    user = await get_user_by_name(message.text.strip())
    if user:
        await delete_user_from_db(user[0])
        await message.answer(f"✅ {user[1]} удален.", reply_markup=get_admin_inline_kb())
    else: await message.answer("Не найден.", reply_markup=get_admin_inline_kb())
    await state.clear()

@dp.callback_query(F.data == "adm_delete_shift")
async def cb_adm_del_shift(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи фамилию сотрудника для удаления смены:")
    await state.set_state(DeleteShiftState.waiting_for_name)
    await callback.answer()

@dp.message(DeleteShiftState.waiting_for_name)
async def process_del_shift_name(message: types.Message, state: FSMContext):
    user = await get_user_by_name(message.text.strip())
    if not user: return await message.answer("Не найден.")
    await state.update_data(target_id=user[0])
    await message.answer("Введи месяц и год смены (напр. 10 2026):")
    await state.set_state(DeleteShiftState.waiting_for_month)

@dp.message(DeleteShiftState.waiting_for_month)
async def process_del_shift_month(message: types.Message, state: FSMContext):
    try: m, y = map(int, message.text.split())
    except: return await message.answer("Ошибка формата.")
    data = await state.get_data()
    shifts = await get_user_shifts_by_month(data['target_id'], f"{y}-{m:02d}")
    if not shifts: return await message.answer("Смен нет.", reply_markup=get_admin_inline_kb())
    
    kb = [[KeyboardButton(text=f"Удалить {s[1]} ({s[2]})")] for s in shifts]
    kb.append([KeyboardButton(text="🔙 Назад в меню")])
    btn_map = {f"Удалить {s[1]} ({s[2]})": s[0] for s in shifts}
    await state.update_data(btn_map=btn_map)
    await message.answer("Выбери смену:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("Удалить "))
async def process_del_shift_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text in data.get('btn_map', {}):
        await delete_shift_by_id(data['btn_map'][message.text])
        await message.answer("✅ Смена удалена.", reply_markup=get_admin_inline_kb())
        await state.clear()

@dp.callback_query(F.data == "adm_add_shift")
async def cb_adm_add_shift(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи фамилию сотрудника:")
    await state.set_state(AddShiftState.waiting_for_user)
    await callback.answer()

@dp.message(AddShiftState.waiting_for_user)
async def process_add_shift_user(message: types.Message, state: FSMContext):
    user = await get_user_by_name(message.text.strip())
    if not user: return await message.answer("Не найден.")
    await state.update_data(target_id=user[0])
    await message.answer("Введи дату (ГГГГ-ММ-ДД):")
    await state.set_state(AddShiftState.waiting_for_date)

@dp.message(AddShiftState.waiting_for_date)
async def process_add_shift_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text)
    await message.answer("Тип смены:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Дневная"), KeyboardButton(text="Ночная")]], resize_keyboard=True))
    await state.set_state(AddShiftState.waiting_for_type)

@dp.message(AddShiftState.waiting_for_type)
async def process_add_shift_type(message: types.Message, state: FSMContext):
    await state.update_data(s_type=message.text)
    await message.answer("Адрес точки:")
    await state.set_state(AddShiftState.waiting_for_address)

@dp.message(AddShiftState.waiting_for_address)
async def process_add_shift_addr(message: types.Message, state: FSMContext):
    await state.update_data(addr=message.text)
    await message.answer("Кого сменяешь? (или '-')")
    await state.set_state(AddShiftState.waiting_for_replaces)

@dp.message(AddShiftState.waiting_for_replaces)
async def process_add_shift_repl(message: types.Message, state: FSMContext):
    await state.update_data(repl=message.text)
    await message.answer("Кто сменяет? (или '-')")
    await state.set_state(AddShiftState.waiting_for_replaced_by)

@dp.message(AddShiftState.waiting_for_replaced_by)
async def process_add_shift_repl_by(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("INSERT INTO shifts (user_id, date, shift_type, address, replaces, replaced_by) VALUES (?, ?, ?, ?, ?, ?)",
                         (data['target_id'], data['date'], data['s_type'], data['addr'], data['repl'], message.text))
        await db.commit()
    await message.answer("✅ Смена добавлена!", reply_markup=get_admin_inline_kb())
    await state.clear()

async def main():
    await init_db()
    asyncio.create_task(auto_sync_worker())
    asyncio.create_task(daily_closing_reminder_worker())
    asyncio.create_task(shift_reminders_worker())
    print("Бот запущен...", flush=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
