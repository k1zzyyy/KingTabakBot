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
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL", "https://docs.google.com/spreadsheets/d/e/2PACX-1vRdmiCfg-6fTdd8PVGmKJQZgYUInzQodiRvZ5Ken1r2_Uh3SwbP87ZtuQwZ9Mcm6rRJ9cO7dh7Qso78/pub?output=csv")
ADMIN_IDS = [7088621971] # ID Захара

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ЧАСОВОЙ ПОЯС ---
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# --- СЛОВАРЬ МЕСЯЦЕВ ---
MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

# --- СОСТОЯНИЯ ---
class RegState(StatesGroup):
    waiting_for_name = State()

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

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, name TEXT, role TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS shifts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, date TEXT, shift_type TEXT, address TEXT, replaces TEXT, replaced_by TEXT)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                user_id INTEGER, 
                type TEXT, 
                amount INTEGER, 
                date TEXT
            )
        """)
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS valid_names (name TEXT PRIMARY KEY)")
        
        await db.execute("UPDATE users SET role = '2800' WHERE role LIKE '%LvL1%' OR role = 'стажер' OR role = 'Стажер'")
        await db.execute("UPDATE users SET role = '3100' WHERE role LIKE '%LvL2%' OR role = 'продавец' OR role = 'Продавец'")
        await db.execute("UPDATE users SET role = '3500' WHERE role LIKE '%LvL3%' OR role = 'экзаминированный' OR role = 'Экзаминированный'")
        
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
    last_month = await get_setting("last_loaded_month")
    last_year = await get_setting("last_loaded_year")
    
    if last_month and last_year:
        try:
            month_int = int(last_month)
            month_name = MONTHS_RU.get(month_int, last_month).lower()
            return f"{month_name} {last_year}"
        except ValueError:
            return "неизвестно"
    return "пока не загружено"

async def get_user(telegram_id):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT name, role FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def get_user_by_name(name):
    clean_name = str(name).strip()
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT telegram_id, name FROM users WHERE name LIKE ?", (f"%{clean_name}%",)) as cursor:
            return await cursor.fetchone()

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
        async with db.execute(
            "SELECT date, shift_type, address, replaces, replaced_by FROM shifts WHERE user_id = ? AND date >= ? ORDER BY date ASC",
            (user_id, today_str)
        ) as cursor:
            shifts = await cursor.fetchall()
            
    for s in shifts:
        s_date, s_type, addr, repl, repl_by = s
        start_hour = 10 if "День" in s_type else 22
        s_dt = datetime.strptime(f"{s_date} {start_hour}:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=MOSCOW_TZ)
        if now < s_dt:
            return s
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
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, date) VALUES (?, ?, ?, ?)",
            (user_id, t_type, amount, date_str)
        )
        await db.commit()

async def get_transactions_sum(user_id, start_date, end_date, t_type):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute(
            "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = ? AND date >= ? AND date <= ?",
            (user_id, t_type, start_date, end_date)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result[0] else 0

# --- ФОНОВЫЕ ВОРКЕРЫ ---
async def daily_closing_reminder_worker():
    while True:
        now = datetime.now(MOSCOW_TZ)
        target_time = time(21, 45, 0)
        target_datetime = datetime.combine(now.date(), target_time, MOSCOW_TZ)
        
        if now >= target_datetime:
            target_datetime += timedelta(days=1)
            
        seconds_until_target = (target_datetime - now).total_seconds()
        await asyncio.sleep(seconds_until_target)
        
        try:
            today_str = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
            async with aiosqlite.connect("king_tabak.db") as db:
                query = """
                    SELECT DISTINCT user_id FROM shifts 
                    WHERE date = ? AND (shift_type LIKE '%День%' OR shift_type = 'Дневная')
                """
                async with db.execute(query, (today_str,)) as cursor:
                    users_to_notify = await cursor.fetchall()
                    
            for (uid,) in users_to_notify:
                try:
                    await bot.send_message(uid, "⏰ <b>Напоминание!</b>\n\nКоллеги, не забудьте закрыть смену ровно в 22:00!", parse_mode="HTML")
                    await asyncio.sleep(0.1)
                except Exception: pass
        except Exception as e:
            pass
        await asyncio.sleep(60)

async def shift_reminders_worker():
    last_day_rem = None
    last_night_rem = None
    
    while True:
        now = datetime.now(MOSCOW_TZ)
        
        if now.hour == 16 and now.minute < 5 and last_day_rem != now.date():
            last_day_rem = now.date()
            tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            async with aiosqlite.connect("king_tabak.db") as db:
                async with db.execute("SELECT user_id, address FROM shifts WHERE date = ? AND (shift_type LIKE '%День%' OR shift_type = 'Дневная')", (tomorrow_str,)) as cursor:
                    shifts = await cursor.fetchall()
            for uid, addr in shifts:
                try:
                    await bot.send_message(uid, f"☀️ Привет! Завтра в 10:00 у тебя смена на точке <b>{addr}</b>", parse_mode="HTML")
                    await asyncio.sleep(0.1)
                except Exception: pass

        if now.hour == 12 and now.minute < 5 and last_night_rem != now.date():
            last_night_rem = now.date()
            today_str = now.strftime("%Y-%m-%d")
            async with aiosqlite.connect("king_tabak.db") as db:
                async with db.execute("SELECT user_id, address FROM shifts WHERE date = ? AND (shift_type LIKE '%Ночь%' OR shift_type = 'Ночная')", (today_str,)) as cursor:
                    shifts = await cursor.fetchall()
            for uid, addr in shifts:
                try:
                    await bot.send_message(uid, f"🌙 Привет! Сегодня в 22:00 у тебя смена на точке <b>{addr}</b>", parse_mode="HTML")
                    await asyncio.sleep(0.1)
                except Exception: pass
        
        await asyncio.sleep(60)

# --- ПАРСИНГ ТАБЛИЦЫ ---
async def process_and_save_sheet(month, year, is_auto=False, notify_users=True):
    try:
        async with aiohttp.ClientSession() as session_http:
            async with session_http.get(SHEET_CSV_URL) as response:
                if response.status != 200:
                    return False, f"Ошибка скачивания: {response.status}"
                text = await response.text()
        
        if "<html" in text.lower() or "<!doctype html" in text.lower():
            return False, "Ошибка: По ссылке не CSV."

        current_hash = hashlib.md5(text.encode()).hexdigest()
        last_hash = await get_setting("last_sheet_hash")
        if last_hash == current_hash and is_auto:
            return True, "Без изменений."

        f = io.StringIO(text)
        delimiter = ',' if text.split('\n')[0].count(',') > text.split('\n')[0].count(';') else ';'
        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)

        if len(rows) < 2:
            return False, "Таблица пустая."

        header_row_index = -1
        for idx, row in enumerate(rows[:10]): 
            row_str = " ".join(str(cell).upper() for cell in row)
            if "ВТ" in row_str or "СР" in row_str or "ПН" in row_str:
                header_row_index = idx
                break
        
        if header_row_index == -1:
            return False, "Нет заголовков с днями."
            
        day_headers = rows[header_row_index]
        col_to_day = {}
        for i, cell in enumerate(day_headers):
            digits = ''.join(filter(str.isdigit, str(cell)))
            if digits: col_to_day[i] = int(digits)

        parsed_shifts = []
        missing_names = set() 
        all_names_in_sheet = set()
        current_address = ""
        
        for row in rows[header_row_index + 1:]:
            if len(row) < 2: continue
            address_cell = row[0].strip()
            if address_cell: current_address = address_cell
            
            shift_type = row[1].strip().capitalize() if len(row) > 1 else ""
            if shift_type not in ("День", "Дневная", "Ночь", "Ночная"): continue 

            for col_idx, day_num in col_to_day.items():
                if col_idx >= len(row): continue
                cell_value = row[col_idx].strip()
                if cell_value and cell_value not in ("---", "——", "—", "⬆️", "⬇️", "↑", "↓"):
                    all_names_in_sheet.add(cell_value)
                    user = await get_user_by_name(cell_value)
                    user_id = user[0] if user else None
                    if not user: missing_names.add(cell_value)
                    try:
                        shift_date = datetime(year, month, day_num).strftime("%Y-%m-%d")
                        parsed_shifts.append({
                            'user_id': user_id, 'name': cell_value, 'date': shift_date,
                            'shift_type': shift_type, 'address': current_address
                        })
                    except Exception: pass

        if all_names_in_sheet:
            async with aiosqlite.connect("king_tabak.db") as db:
                for name in all_names_in_sheet:
                    await db.execute("INSERT OR IGNORE INTO valid_names (name) VALUES (?)", (name,))
                await db.commit()

        locations = defaultdict(list)
        for shift in parsed_shifts: locations[shift['address']].append(shift)

        notified_users = set()
        await clear_shifts_for_month(month, year)

        insert_data = []
        for addr, shifts in locations.items():
            shifts.sort(key=lambda s: (s['date'], 0 if "День" in s['shift_type'] else 1)) 
            for i in range(len(shifts)):
                replaces_name = shifts[i-1]['name'] if i > 0 else "-"
                replaced_by_name = shifts[i+1]['name'] if i < len(shifts) - 1 else "-"
                if shifts[i]['user_id'] is not None:
                    insert_data.append((
                        shifts[i]['user_id'], shifts[i]['date'], shifts[i]['shift_type'],
                        shifts[i]['address'], replaces_name, replaced_by_name
                    ))
                    notified_users.add(shifts[i]['user_id'])

        success_count = 0
        if insert_data:
            async with aiosqlite.connect("king_tabak.db") as db:
                await db.executemany(
                    "INSERT INTO shifts (user_id, date, shift_type, address, replaces, replaced_by) VALUES (?, ?, ?, ?, ?, ?)",
                    insert_data
                )
                await db.commit()
            success_count = len(insert_data)

        await set_setting("last_sheet_hash", current_hash)
        await set_setting("last_loaded_month", str(month))
        await set_setting("last_loaded_year", str(year))
        
        if notified_users and notify_users:
            for uid in notified_users:
                try: await bot.send_message(uid, "🔔 <b>Внимание!</b> Обновлено расписание смен.", parse_mode="HTML")
                except Exception: pass

        result_msg = f"✅ Импорт завершен!\nДобавлено смен: {success_count}."
        if missing_names and notify_users:
            result_msg += f"\n⚠️ Нет в базе: {', '.join(list(missing_names)[:10])}..."
        return True, result_msg

    except Exception as e:
        return False, f"Ошибка: {str(e)}"

async def auto_sync_worker():
    while True:
        await asyncio.sleep(600) 
        try:
            sync_month = await get_setting("sync_month")
            sync_year = await get_setting("sync_year")
            if sync_month and sync_year:
                await process_and_save_sheet(int(sync_month), int(sync_year), is_auto=True)
        except Exception: pass

# --- КЛАВИАТУРЫ (ТОЛЬКО REPLY) ---
def get_main_menu():
    kb = [
        [KeyboardButton(text="📅 Мои смены"), KeyboardButton(text="⏰ Ближайшая смена")],
        [KeyboardButton(text="💰 Зарплата"), KeyboardButton(text="👤 Личный кабинет")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)

def get_salary_menu():
    kb = [
        [KeyboardButton(text="🔻 Штраф"), KeyboardButton(text="🔺 Докид")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_cabinet_menu():
    kb = [
        [KeyboardButton(text="📈 Сменить ставку"), KeyboardButton(text="✏️ Сменить фамилию")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_menu(auto_status="Выкл"):
    kb = [
        [KeyboardButton(text="➕ Добавить смену"), KeyboardButton(text="❌ Удалить смену")],
        [KeyboardButton(text="❌ Удалить пользователя"), KeyboardButton(text="⚡ Авто-синх")],
        [KeyboardButton(text="🔄 Загрузить вручную"), KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- СТАРТ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if user:
        name, role = user
        try: rate_val = int(role)
        except: rate_val = 0
        
        sched_info = await get_schedule_text()
        await message.answer(
            f"Привет!\nЗагружено расписание на: <b>{sched_info}</b>\nТвоя ставка: <b>{rate_val} ₽</b>.", 
            reply_markup=get_main_menu(), 
            parse_mode="HTML"
        )
    else:
        await message.answer("Привет! Я бот расписания сети Кинг Табак.\n\nНапиши свою <b>Фамилию</b> (как в таблице):", reply_markup=get_main_menu(), parse_mode="HTML")
        await state.set_state(RegState.waiting_for_name)

@dp.message(F.text == "🔙 Назад в меню")
async def cmd_back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.clear()
    await message.answer("⚙️ Админ-панель:", reply_markup=get_admin_menu())

# --- РЕГИСТРАЦИЯ ---
@dp.message(RegState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT COUNT(*) FROM valid_names") as cursor:
            count = (await cursor.fetchone())[0]
        if count > 0:
            async with db.execute("SELECT name FROM valid_names WHERE name LIKE ?", (f"%{user_input}%",)) as cursor:
                valid = await cursor.fetchone()
            if not valid:
                await message.answer("❌ <b>Ошибка:</b> Фамилия не зарегистрирована в расписании.", parse_mode="HTML")
                return

    await state.update_data(name=user_input)
    
    kb = [[KeyboardButton(text="2800 ₽"), KeyboardButton(text="3100 ₽"), KeyboardButton(text="3500 ₽")]]
    await message.answer("Теперь выбери свою ставку:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.in_(["2800 ₽", "3100 ₽", "3500 ₽"]))
async def process_role(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != RegState.waiting_for_name.state: return # Защита от нажатия кнопок ставки вне регистрации

    role = message.text.replace(" ₽", "")
    user_data = await state.get_data()
    name = user_data.get("name")
    await save_user(message.from_user.id, name, role)
    
    sched_info = await get_schedule_text()
    last_month = await get_setting("last_loaded_month")
    last_year = await get_setting("last_loaded_year")
    
    if last_month and last_year:
        await message.answer("⏳ Подгружаю твои смены...")
        await process_and_save_sheet(int(last_month), int(last_year), is_auto=False, notify_users=False)
    
    await message.answer(
        f"Регистрация завершена!\nФамилия: {name}\nТвоя ставка: <b>{role} ₽</b>", 
        reply_markup=get_main_menu(), 
        parse_mode="HTML"
    )
    await state.clear()

# --- МОИ СМЕНЫ ---
@dp.message(F.text == "📅 Мои смены")
async def btn_my_shifts(message: types.Message):
    months = await get_user_shifts_months(message.from_user.id)
    if not months:
        await message.answer("У тебя пока нет смен в расписании.")
    else:
        kb = []
        row = []
        for (ym,) in months:
            year, month_num = ym.split("-")
            month_name = MONTHS_RU.get(int(month_num), month_num)
            row.append(KeyboardButton(text=f"{month_name} {year}"))
            if len(row) == 2:
                kb.append(row)
                row = []
        if row: kb.append(row)
        kb.append([KeyboardButton(text="🔙 Назад в меню")])
        
        await message.answer("Выбери месяц:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.regexp(r"^(Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь) \d{4}$"))
async def btn_my_shifts_month(message: types.Message):
    month_name, year = message.text.split()
    month_num = list(MONTHS_RU.keys())[list(MONTHS_RU.values()).index(month_name)]
    ym = f"{year}-{month_num:02d}"
    
    shifts = await get_user_shifts_by_month(message.from_user.id, ym)
    if not shifts:
        await message.answer("За этот месяц смен нет.")
    else:
        text = f"📅 <b>Твои смены за {month_name} {year}:</b>\n\n"
        for s in shifts:
            _, date_str, s_type, addr, repl, repl_by = s
            text += f"📆 {date_str} ({s_type})\n📍 {addr}\n🔄 Сменяю: {repl}\n👤 Сменяет: {repl_by}\n\n"
        
        kb = [[KeyboardButton(text="📅 Другой месяц")], [KeyboardButton(text="🔙 Назад в меню")]]
        await message.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "📅 Другой месяц")
async def btn_another_month(message: types.Message):
    await btn_my_shifts(message)

# --- БЛИЖАЙШАЯ СМЕНА ---
@dp.message(F.text == "⏰ Ближайшая смена")
async def btn_next_shift(message: types.Message):
    shift = await get_next_shift(message.from_user.id)
    if not shift:
        await message.answer("У тебя нет предстоящих смен.")
    else:
        date_str, s_type, addr, repl, repl_by = shift
        text = (f"⏰ <b>Твоя ближайшая смена:</b>\n\n📆 Дата: {date_str}\n🕒 Тип: {s_type}\n📍 Адрес: {addr}\n🔄 Сменяешь: {repl}\n👤 Сменяет тебя: {repl_by}")
        await message.answer(text, parse_mode="HTML")

# --- ЗАРПЛАТА ---
@dp.message(F.text == "💰 Зарплата")
async def btn_salary(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user: return
    name, role = user
    today = date.today()
    
    if 10 <= today.day < 25:
        start_date, end_date = today.replace(day=10), today.replace(day=25)
    elif today.day >= 25:
        start_date = today.replace(day=25)
        end_date = date(today.year + 1, 1, 10) if today.month == 12 else date(today.year, today.month + 1, 10)
    else:
        start_date = date(today.year - 1, 12, 25) if today.month == 1 else date(today.year, today.month - 1, 25)
        end_date = today.replace(day=10)

    start_str, end_str = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    end_inclusive_str = (end_date - timedelta(days=1)).strftime("%Y-%m-%d") 

    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT COUNT(*) FROM shifts WHERE user_id = ? AND date >= ? AND date < ?", (message.from_user.id, start_str, end_str)) as cursor:
            count = (await cursor.fetchone())[0]

    try: rate = int(role)
    except: rate = 0
        
    base_salary = count * rate
    total_fines = await get_transactions_sum(message.from_user.id, start_str, end_inclusive_str, "fine")
    total_bonuses = await get_transactions_sum(message.from_user.id, start_str, end_inclusive_str, "bonus")
    final_salary = base_salary - total_fines + total_bonuses

    text = (
        f"💳 <b>Расчетный лист</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🗓 Период: {start_date.strftime('%d.%m')} — {(end_date - timedelta(days=1)).strftime('%d.%m')}\n"
        f"💸 Дата выплаты: <b>{end_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"🕒 Отработано смен: <b>{count}</b>\n"
        f"💵 Твоя ставка: <b>{rate} ₽</b>\n"
        f"⚙️ Оклад за смены: <b>{base_salary} ₽</b>\n\n"
        f"🔻 Вычтено (штрафы): <b>-{total_fines} ₽</b>\n"
        f"🔺 Начислено (докиды): <b>+{total_bonuses} ₽</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>К ВЫПЛАТЕ: {final_salary} ₽</b>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_salary_menu())

# --- ШТРАФЫ И ДОКИДЫ ---
@dp.message(F.text == "🔻 Штраф")
async def btn_add_fine(message: types.Message, state: FSMContext):
    await message.answer("🔻 Введи сумму штрафа (только число, например: 3000):")
    await state.set_state(TransactionState.waiting_for_fine)

@dp.message(TransactionState.waiting_for_fine)
async def process_fine(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Ошибка! Введи положительное число.")
        return

    today_str = date.today().strftime("%Y-%m-%d")
    await add_transaction(message.from_user.id, "fine", amount, today_str)
    await message.answer(f"✅ Штраф <b>{amount} ₽</b> применен.", reply_markup=get_salary_menu(), parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "🔺 Докид")
async def btn_add_bonus(message: types.Message, state: FSMContext):
    await message.answer("🔺 Введи сумму докида (только число, например: 1000):")
    await state.set_state(TransactionState.waiting_for_bonus)

@dp.message(TransactionState.waiting_for_bonus)
async def process_bonus(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Ошибка! Введи положительное число.")
        return

    today_str = date.today().strftime("%Y-%m-%d")
    await add_transaction(message.from_user.id, "bonus", amount, today_str)
    await message.answer(f"✅ Докид <b>{amount} ₽</b> добавлен.", reply_markup=get_salary_menu(), parse_mode="HTML")
    await state.clear()

# --- ЛИЧНЫЙ КАБИНЕТ ---
@dp.message(F.text == "👤 Личный кабинет")
async def btn_cabinet(message: types.Message):
    await message.answer("👤 <b>Личный кабинет</b>\nВыбери действие:", reply_markup=get_cabinet_menu(), parse_mode="HTML")

@dp.message(F.text == "📈 Сменить ставку")
async def btn_change_rate(message: types.Message):
    kb = [[KeyboardButton(text="2800 ₽"), KeyboardButton(text="3100 ₽"), KeyboardButton(text="3500 ₽")], [KeyboardButton(text="🔙 Назад в меню")]]
    await message.answer("Выбери новую ставку:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "✏️ Сменить фамилию")
async def btn_change_name(message: types.Message, state: FSMContext):
    await message.answer("Введи свою новую <b>Фамилию</b>:", parse_mode="HTML")
    await state.set_state(ChangeNameState.waiting_for_new_name)

@dp.message(ChangeNameState.waiting_for_new_name)
async def process_change_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT name FROM valid_names WHERE name LIKE ?", (f"%{new_name}%",)) as cursor:
            valid = await cursor.fetchone()
        if not valid:
            await message.answer("❌ <b>Ошибка:</b> Фамилия не зарегистрирована в расписании.", parse_mode="HTML")
            return

    await update_user_name(message.from_user.id, new_name)
    await message.answer(f"✅ Твоя фамилия изменена на <b>{new_name}</b>!", reply_markup=get_main_menu(), parse_mode="HTML")
    await state.clear()

# Обработка выбора ставки (в личном кабинете)
@dp.message(F.text.in_(["2800 ₽", "3100 ₽", "3500 ₽"]))
async def process_cabinet_role(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == RegState.waiting_for_name.state: return # уже обработано выше
    
    new_rate = message.text.replace(" ₽", "")
    await update_user_role(message.from_user.id, new_rate)
    await message.answer(f"✅ Твоя ставка изменена на <b>{new_rate} ₽</b>!", reply_markup=get_main_menu(), parse_mode="HTML")

# --- АДМИН ПАНЕЛЬ ---
@dp.message(F.text == "⚡ Авто-синх")
async def btn_toggle_auto(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    auto_month = await get_setting("sync_month")
    if auto_month:
        await set_setting("sync_month", "")
        await set_setting("sync_year", "")
        await message.answer("❌ Автосинхронизация выключена.")
    else:
        await message.answer("Введи месяц и год для автосинхронизации (например: 10 2026):")
        await state.set_state(AutoSyncState.waiting_for_sync_date)

@dp.message(AutoSyncState.waiting_for_sync_date)
async def process_toggle_auto_date(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        month_str, year_str = message.text.split()
        month, year = int(month_str), int(year_str)
        await set_setting("sync_month", str(month))
        await set_setting("sync_year", str(year))
        
        success, msg = await process_and_save_sheet(month, year, is_auto=False)
        await message.answer(f"✅ Автосинхронизация включена на {month:02d}.{year}!\n\n{msg}", reply_markup=get_admin_menu())
    except ValueError:
        await message.answer("❌ Неверный формат. Напиши месяц и год через пробел.")
    await state.clear()

@dp.message(F.text == "🔄 Загрузить вручную")
async def btn_import_gsheet(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Введи месяц и год для загрузки (например: 10 2026):")
    await state.set_state(ImportState.waiting_for_gsheet_date)

@dp.message(ImportState.waiting_for_gsheet_date)
async def process_gsheet_date(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        month_str, year_str = message.text.split()
        month, year = int(month_str), int(year_str)
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return

    await message.answer("⏳ Скачиваю...")
    success, result_msg = await process_and_save_sheet(month, year, is_auto=False, notify_users=True)
    await message.answer(result_msg, reply_markup=get_admin_menu())
    await state.clear()

@dp.message(F.text == "❌ Удалить пользователя")
async def btn_delete_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    users = await get_all_users()
    text = "Список пользователей:\n"
    for uid, name, role in users:
        text += f"• {name} ({role}₽)\n"
    text += "\nВведи фамилию пользователя для удаления (или 'Отмена'):"
    await message.answer(text)
    await state.set_state(DeleteUserState.waiting_for_name)

@dp.message(DeleteUserState.waiting_for_name)
async def process_delete_user(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    if message.text.lower() == "отмена":
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        await state.clear()
        return
        
    user = await get_user_by_name(message.text.strip())
    if user:
        await delete_user_from_db(user[0])
        await message.answer(f"✅ Пользователь {message.text} и его смены удалены.", reply_markup=get_admin_menu())
    else:
        await message.answer("❌ Пользователь не найден.", reply_markup=get_admin_menu())
    await state.clear()

@dp.message(F.text == "❌ Удалить смену")
async def btn_delete_shift_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Введи фамилию сотрудника, у которого нужно удалить смену:")
    await state.set_state(DeleteShiftState.waiting_for_name)

@dp.message(DeleteShiftState.waiting_for_name)
async def process_delete_shift_name(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    user = await get_user_by_name(message.text.strip())
    if not user:
        await message.answer("❌ Пользователь не найден.")
        await state.clear()
        return
        
    await state.update_data(target_id=user[0])
    await message.answer("Введи месяц и год смены для удаления (например: 10 2026):")
    await state.set_state(DeleteShiftState.waiting_for_month)

@dp.message(DeleteShiftState.waiting_for_month)
async def process_delete_shift_month(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        month, year = map(int, message.text.split())
        ym = f"{year}-{month:02d}"
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return
        
    data = await state.get_data()
    target_id = data['target_id']
    shifts = await get_user_shifts_by_month(target_id, ym)
    
    if not shifts:
        await message.answer("За этот месяц смен нет.", reply_markup=get_admin_menu())
        await state.clear()
        return
        
    kb = []
    for s in shifts:
        s_id, s_date, s_type, s_addr, _, _ = s
        kb.append([KeyboardButton(text=f"Удалить {s_date} ({s_type}) {s_addr}")])
    kb.append([KeyboardButton(text="🔙 Назад в меню")])
    
    # Сохраняем маппинг кнопок в стейт, чтобы потом удалить
    btn_map = {f"Удалить {s[1]} ({s[2]}) {s[3]}": s[0] for s in shifts}
    await state.update_data(btn_map=btn_map)
    
    await message.answer("Выбери смену для удаления (нажми кнопку):", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("Удалить "))
async def process_delete_shift_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_map = data.get('btn_map', {})
    if message.text in btn_map:
        shift_id = btn_map[message.text]
        await delete_shift_by_id(shift_id)
        await message.answer("✅ Смена удалена!", reply_markup=get_admin_menu())
        await state.clear()

# --- ДОБАВЛЕНИЕ СМЕНЫ ---
@dp.message(F.text == "➕ Добавить смену")
async def btn_add_shift(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    users = await get_all_users()
    text = "Список пользователей:\n"
    for uid, name, role in users:
        text += f"• {name}\n"
    text += "\nВведи фамилию сотрудника, кому добавляем смену:"
    await message.answer(text)
    await state.set_state(AddShiftState.waiting_for_user)

@dp.message(AddShiftState.waiting_for_user)
async def process_add_shift_user(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    user = await get_user_by_name(message.text.strip())
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return
    await state.update_data(target_user_id=user[0])
    await message.answer("Введи дату смены (ГГГГ-ММ-ДД):")
    await state.set_state(AddShiftState.waiting_for_date)

@dp.message(AddShiftState.waiting_for_date)
async def process_add_shift_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text)
    kb = [[KeyboardButton(text="Дневная"), KeyboardButton(text="Ночная")]]
    await message.answer("Тип смены:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(AddShiftState.waiting_for_type)

@dp.message(AddShiftState.waiting_for_type)
async def process_add_shift_type(message: types.Message, state: FSMContext):
    await state.update_data(shift_type=message.text)
    await message.answer("Адрес точки:")
    await state.set_state(AddShiftState.waiting_for_address)

@dp.message(AddShiftState.waiting_for_address)
async def process_add_shift_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("Кого сменяешь? (или '-')")
    await state.set_state(AddShiftState.waiting_for_replaces)

@dp.message(AddShiftState.waiting_for_replaces)
async def process_add_shift_replaces(message: types.Message, state: FSMContext):
    await state.update_data(replaces=message.text)
    await message.answer("Кто сменяет? (или '-')")
    await state.set_state(AddShiftState.waiting_for_replaced_by)

@dp.message(AddShiftState.waiting_for_replaced_by)
async def process_add_shift_replaced_by(message: types.Message, state: FSMContext):
    await state.update_data(replaced_by=message.text)
    data = await state.get_data()
    
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute(
            "INSERT INTO shifts (user_id, date, shift_type, address, replaces, replaced_by) VALUES (?, ?, ?, ?, ?, ?)",
            (data['target_user_id'], data['date'], data['shift_type'], data['address'], data['replaces'], message.text)
        )
        await db.commit()
        
    await message.answer("✅ Смена добавлена!", reply_markup=get_admin_menu())
    await state.clear()

# --- ЗАПУСК ---
async def main():
    await init_db()
    asyncio.create_task(auto_sync_worker())
    asyncio.create_task(daily_closing_reminder_worker())
    asyncio.create_task(shift_reminders_worker())
    
    print("Бот запущен...", flush=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
