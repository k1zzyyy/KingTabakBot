import asyncio
import os
import aiosqlite
import csv
import io
import aiohttp
import hashlib
from datetime import date, datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL", "https://docs.google.com/spreadsheets/d/e/2PACX-1vRdmiCfg-6fTdd8PVGmKJQZgYUInzQodiRvZ5Ken1r2_Uh3SwbP87ZtuQwZ9Mcm6rRJ9cO7dh7Qso78/pub?output=csv")
ADMIN_IDS = [7088621971] # ID Захара

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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

class DeleteShiftState(StatesGroup):
    waiting_for_user = State()

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

async def get_all_users():
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT telegram_id, name, role FROM users") as cursor:
            return await cursor.fetchall()

async def check_shift_exists(user_id, date_str, shift_type):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT id FROM shifts WHERE user_id = ? AND date = ? AND shift_type = ?", (user_id, date_str, shift_type)) as cursor:
            return await cursor.fetchone() is not None

async def add_shift_to_db(user_id, date_str, shift_type, address, replaces, replaced_by):
    if await check_shift_exists(user_id, date_str, shift_type):
        return False 
        
    async with aiosqlite.connect("king_tabak.db") as db:
        await db.execute(
            "INSERT INTO shifts (user_id, date, shift_type, address, replaces, replaced_by) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, date_str, shift_type, address, replaces, replaced_by)
        )
        await db.commit()
        return True

async def get_user_shifts(user_id):
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute("SELECT id, date, shift_type, address, replaces, replaced_by FROM shifts WHERE user_id = ? ORDER BY date", (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_next_shift(user_id):
    today_str = date.today().strftime("%Y-%m-%d")
    async with aiosqlite.connect("king_tabak.db") as db:
        async with db.execute(
            "SELECT date, shift_type, address, replaces, replaced_by FROM shifts WHERE user_id = ? AND date >= ? ORDER BY date ASC LIMIT 1",
            (user_id, today_str)
        ) as cursor:
            return await cursor.fetchone()

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

# --- ПАРСИНГ ТАБЛИЦЫ ---
async def process_and_save_sheet(month, year, is_auto=False):
    try:
        async with aiohttp.ClientSession() as session_http:
            async with session_http.get(SHEET_CSV_URL) as response:
                if response.status != 200:
                    return False, f"Ошибка скачивания. Google вернул код: {response.status}"
                text = await response.text()
        
        if "<html" in text.lower() or "<!doctype html" in text.lower():
            return False, "Ошибка: По ссылке скачалась веб-страница."

        current_hash = hashlib.md5(text.encode()).hexdigest()
        last_hash = await get_setting("last_sheet_hash")
        
        if last_hash == current_hash and is_auto:
            return True, "Данные не изменились, синхронизация не требуется."

        f = io.StringIO(text)
        delimiter = ','
        first_line = text.split('\n')[0]
        if first_line.count(';') > first_line.count(','):
            delimiter = ';'

        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)

        if len(rows) < 2:
            return False, "Таблица пустая или неверный формат."

        header_row_index = -1
        for idx, row in enumerate(rows[:10]): 
            row_str = " ".join(str(cell).upper() for cell in row)
            if "ВТ" in row_str or "СР" in row_str or "ПН" in row_str:
                header_row_index = idx
                break
        
        if header_row_index == -1:
            return False, "Не смог найти строку с днями недели (1ВТ, 2СР...)."
            
        day_headers = rows[header_row_index]
        col_to_day = {}
        for i, cell in enumerate(day_headers):
            digits = ''.join(filter(str.isdigit, str(cell)))
            if digits:
                col_to_day[i] = int(digits)

        if not col_to_day:
            return False, "Не удалось найти даты."

        parsed_shifts = []
        missing_names = set() 
        current_address = ""
        
        for row in rows[header_row_index + 1:]:
            if len(row) < 2: continue
            
            address_cell = row[0].strip()
            if address_cell:
                current_address = address_cell
            
            shift_type = row[1].strip().capitalize() if len(row) > 1 else ""
            if shift_type not in ("День", "Дневная", "Ночь", "Ночная"):
                continue 

            for col_idx, day_num in col_to_day.items():
                if col_idx >= len(row): continue
                
                cell_value = row[col_idx].strip()
                if cell_value and cell_value not in ("---", "——", "—", "⬆️", "⬇️", "↑", "↓"):
                    
                    user = await get_user_by_name(cell_value)
                    user_id = user[0] if user else None
                    if not user:
                        missing_names.add(cell_value)
                        
                    try:
                        shift_date = datetime(year, month, day_num).strftime("%Y-%m-%d")
                        parsed_shifts.append({
                            'user_id': user_id,
                            'name': cell_value,
                            'date': shift_date,
                            'shift_type': shift_type,
                            'address': current_address
                        })
                    except Exception:
                        pass

        locations = defaultdict(list)
        for shift in parsed_shifts:
            locations[shift['address']].append(shift)

        def sort_key(s):
            type_weight = 0 if "День" in s['shift_type'] else 1
            return (s['date'], type_weight)

        success_count = 0
        notified_users = set()

        await clear_shifts_for_month(month, year)

        for addr, shifts in locations.items():
            shifts.sort(key=sort_key) 
            for i in range(len(shifts)):
                replaces_name = shifts[i-1]['name'] if i > 0 else "-"
                replaced_by_name = shifts[i+1]['name'] if i < len(shifts) - 1 else "-"
                
                if shifts[i]['user_id'] is not None:
                    added = await add_shift_to_db(
                        shifts[i]['user_id'], 
                        shifts[i]['date'], 
                        shifts[i]['shift_type'], 
                        shifts[i]['address'], 
                        replaces_name, 
                        replaced_by_name
                    )
                    if added:
                        success_count += 1
                        notified_users.add(shifts[i]['user_id'])

        await set_setting("last_sheet_hash", current_hash)
        
        if notified_users:
            for uid in notified_users:
                try:
                    await bot.send_message(uid, "🔔 <b>Внимание!</b> Обновлено расписание смен.\nЗайди в бота и нажми «📅 Мои смены».", parse_mode="HTML")
                except Exception:
                    pass

        result_msg = f"✅ Импорт завершен!\nДобавлено смен: {success_count}."
        if missing_names:
            missing_list = list(missing_names)
            result_text = f"\n⚠️ Этих людей нет в базе (всего {len(missing_list)} чел.):\n{', '.join(missing_list[:10])}..."
            result_msg += result_text
            
        return True, result_msg

    except Exception as e:
        return False, f"Ошибка при чтении: {str(e)}"

async def auto_sync_worker():
    while True:
        await asyncio.sleep(600) 
        try:
            sync_month = await get_setting("sync_month")
            sync_year = await get_setting("sync_year")
            if sync_month and sync_year:
                success, msg = await process_and_save_sheet(int(sync_month), int(sync_year), is_auto=True)
        except Exception:
            pass

# --- МЕНЮ ---
def get_main_menu(is_admin=False):
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Мои смены", callback_data="my_shifts")
    builder.button(text="⏰ Ближайшая смена", callback_data="next_shift")
    builder.button(text="💰 Зарплата", callback_data="salary")
    builder.button(text="🔻 Штраф", callback_data="add_fine")
    builder.button(text="🔺 Докид", callback_data="add_bonus")
    builder.button(text="📈 Сменить ставку", callback_data="change_rate")
    builder.button(text="✏️ Сменить фамилию", callback_data="change_name")
    if is_admin:
        builder.button(text="⚙️ Админ-панель", callback_data="admin_panel")
    builder.adjust(1)
    return builder.as_markup()

# --- СТАРТ И РЕГИСТРАЦИЯ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user:
        name, role = user
        is_admin = message.from_user.id in ADMIN_IDS
        try:
            rate_val = int(role)
        except (ValueError, TypeError):
            rate_val = 0
        await message.answer(f"Привет!\nТвоя ставка: <b>{rate_val} ₽</b>.\nВыбери действие:", reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    else:
        await message.answer("Привет! Я бот расписания сети Кинг Табак.\n\nНапиши свою <b>Фамилию</b> (так, как она записана в таблице):", parse_mode="HTML")
        await state.set_state(RegState.waiting_for_name)

@dp.message(RegState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    builder = InlineKeyboardBuilder()
    builder.button(text="2800 ₽", callback_data="role_2800")
    builder.button(text="3100 ₽", callback_data="role_3100")
    builder.button(text="3500 ₽", callback_data="role_3500")
    builder.adjust(1)
    await message.answer("Теперь выбери свою ставку:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("role_"))
async def process_role(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    user_data = await state.get_data()
    name = user_data.get("name")
    await save_user(callback.from_user.id, name, role)
    
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.answer(f"Регистрация завершена!\nФамилия: {name}\nТвоя ставка: <b>{role} ₽</b>\n\n(Попроси админа обновить расписание).", reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    await state.clear()
    await callback.answer()

# --- ШТРАФЫ И ДОКИДЫ ---
@dp.callback_query(F.data == "add_fine")
async def btn_add_fine(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🔻 <b>Оформление штрафа</b>\n\nВведи сумму штрафа (только число, например: <code>3000</code>):", parse_mode="HTML")
    await state.set_state(TransactionState.waiting_for_fine)
    await callback.answer()

@dp.message(TransactionState.waiting_for_fine)
async def process_fine(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Ошибка! Введи положительное число (без букв, минусов и пробелов).")
        return

    today_str = date.today().strftime("%Y-%m-%d")
    await add_transaction(message.from_user.id, "fine", amount, today_str)
    
    is_admin = message.from_user.id in ADMIN_IDS
    # КРАСИВОЕ СООБЩЕНИЕ ОБ УСПЕХЕ
    await message.answer(
        f"✅ <b>Штраф успешно применен!</b>\n\n"
        f"Из вашей зарплаты вычтено: <b>{amount} ₽</b>.\n"
        f"Эта сумма автоматически уменьшит итоговый расчет при следующей выплате.", 
        reply_markup=get_main_menu(is_admin), 
        parse_mode="HTML"
    )
    await state.clear()

@dp.callback_query(F.data == "add_bonus")
async def btn_add_bonus(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🔺 <b>Оформление докида</b>\n\nВведи сумму докида (только число, например: <code>1000</code>):", parse_mode="HTML")
    await state.set_state(TransactionState.waiting_for_bonus)
    await callback.answer()

@dp.message(TransactionState.waiting_for_bonus)
async def process_bonus(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Ошибка! Введи положительное число (без букв, минусов и пробелов).")
        return

    today_str = date.today().strftime("%Y-%m-%d")
    await add_transaction(message.from_user.id, "bonus", amount, today_str)
    
    is_admin = message.from_user.id in ADMIN_IDS
    # КРАСИВОЕ СООБЩЕНИЕ ОБ УСПЕХЕ
    await message.answer(
        f"✅ <b>Докид успешно добавлен!</b>\n\n"
        f"К вашей зарплате прибавлено: <b>{amount} ₽</b>.\n"
        f"Эта сумма автоматически увеличит итоговый расчет при следующей выплате.", 
        reply_markup=get_main_menu(is_admin), 
        parse_mode="HTML"
    )
    await state.clear()

# --- СМЕНА СТАВКИ И ФАМИЛИИ ---
@dp.callback_query(F.data == "change_rate")
async def btn_change_rate(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user: return
    name, role = user
    builder = InlineKeyboardBuilder()

    if role not in ("2800", "3100", "3500"):
        builder.button(text="Ставка 2800 ₽", callback_data="rate_2800")
        builder.button(text="Ставка 3100 ₽", callback_data="rate_3100")
        builder.button(text="Ставка 3500 ₽", callback_data="rate_3500")
        msg_text = "Выбери свою ставку заново:"
    else:
        if role == "2800":
            builder.button(text="⬆️ Повысить до 3100 ₽", callback_data="rate_3100")
            msg_text = "Твоя текущая ставка: <b>2800 ₽</b>.\nХочешь повысить?"
        elif role == "3100":
            builder.button(text="⬇️ Понизить до 2800 ₽", callback_data="rate_2800")
            builder.button(text="⬆️ Повысить до 3500 ₽", callback_data="rate_3500")
            msg_text = "Твоя текущая ставка: <b>3100 ₽</b>.\nЧто хочешь сделать?"
        elif role == "3500":
            builder.button(text="⬇️ Понизить до 3100 ₽", callback_data="rate_3100")
            msg_text = "Твоя текущая ставка: <b>3500 ₽</b>.\nХочешь понизить?"
    
    builder.button(text="🔙 Отмена", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.answer(msg_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("rate_"))
async def process_rate_change(callback: types.CallbackQuery):
    new_rate = callback.data.split("_")[1]
    await update_user_role(callback.from_user.id, new_rate)
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.answer(f"✅ Твоя ставка изменена на <b>{new_rate} ₽</b>!", parse_mode="HTML", reply_markup=get_main_menu(is_admin))
    await callback.answer()

@dp.callback_query(F.data == "change_name")
async def btn_change_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи свою новую <b>Фамилию</b>:", parse_mode="HTML")
    await state.set_state(ChangeNameState.waiting_for_new_name)
    await callback.answer()

@dp.message(ChangeNameState.waiting_for_new_name)
async def process_change_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    await update_user_name(message.from_user.id, new_name)
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(f"✅ Твоя фамилия изменена на <b>{new_name}</b>!\n(Попроси админа загрузить расписание заново).", reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    await state.clear()

# --- МОИ СМЕНЫ / БЛИЖАЙШАЯ / ЗАРПЛАТА ---
@dp.callback_query(F.data == "my_shifts")
async def btn_my_shifts(callback: types.CallbackQuery):
    shifts = await get_user_shifts(callback.from_user.id)
    if not shifts:
        await callback.message.answer("У тебя пока нет смен в расписании.")
    else:
        text = "📅 <b>Твои смены:</b>\n\n"
        for s in shifts:
            _, date_str, s_type, addr, repl, repl_by = s
            text += f"📆 {date_str} ({s_type})\n📍 {addr}\n🔄 Сменяю: {repl}\n👤 Сменяет: {repl_by}\n\n"
        await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "next_shift")
async def btn_next_shift(callback: types.CallbackQuery):
    shift = await get_next_shift(callback.from_user.id)
    if not shift:
        await callback.message.answer("У тебя нет предстоящих смен.")
    else:
        date_str, s_type, addr, repl, repl_by = shift
        text = (f"⏰ <b>Твоя ближайшая смена:</b>\n\n📆 Дата: {date_str}\n🕒 Тип: {s_type}\n📍 Адрес: {addr}\n🔄 Сменяешь: {repl}\n👤 Сменяет тебя: {repl_by}")
        await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "salary")
async def btn_salary(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
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
        async with db.execute("SELECT COUNT(*) FROM shifts WHERE user_id = ? AND date >= ? AND date < ?", (callback.from_user.id, start_str, end_str)) as cursor:
            count = (await cursor.fetchone())[0]

    try: rate = int(role)
    except: rate = 0
        
    base_salary = count * rate

    total_fines = await get_transactions_sum(callback.from_user.id, start_str, end_inclusive_str, "fine")
    total_bonuses = await get_transactions_sum(callback.from_user.id, start_str, end_inclusive_str, "bonus")

    final_salary = base_salary - total_fines + total_bonuses

    # КРАСИВЫЙ ВЫВОД
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
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# --- АДМИН ПАНЕЛЬ ---
@dp.callback_query(F.data == "admin_panel")
async def btn_admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У тебя нет прав администратора!", show_alert=True)
        return
    
    auto_month = await get_setting("sync_month")
    auto_year = await get_setting("sync_year")
    auto_status = f"Вкл ({auto_month}.{auto_year})" if auto_month else "Выкл"

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить смену", callback_data="add_shift")
    builder.button(text="❌ Удалить смену", callback_data="delete_shift")
    builder.button(text="⚡ Авто-синхронизация", callback_data="toggle_auto")
    builder.button(text=f"🔄 Загрузить вручную", callback_data="import_gsheet")
    builder.button(text="🔙 Назад в меню", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.answer(f"⚙️ Админ-панель:\nАвтосинхронизация: <b>{auto_status}</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "toggle_auto")
async def btn_toggle_auto(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    
    auto_month = await get_setting("sync_month")
    if auto_month:
        await set_setting("sync_month", "")
        await set_setting("sync_year", "")
        await callback.message.answer("❌ Автосинхронизация выключена.")
    else:
        await callback.message.answer("Введи месяц и год для автосинхронизации (например: <b>10 2026</b>):", parse_mode="HTML")
        await state.set_state(AutoSyncState.waiting_for_sync_date)
    await callback.answer()

@dp.message(AutoSyncState.waiting_for_sync_date)
async def process_toggle_auto_date(message: types.Message, state: FSMContext):
    try:
        month_str, year_str = message.text.split()
        month, year = int(month_str), int(year_str)
        await set_setting("sync_month", str(month))
        await set_setting("sync_year", str(year))
        
        success, msg = await process_and_save_sheet(month, year, is_auto=False)
        await message.answer(f"✅ Автосинхронизация включена на {month:02d}.{year}!\n\nПервичная загрузка: {msg}")
    except ValueError:
        await message.answer("❌ Неверный формат. Напиши месяц и год через пробел (например, 10 2026).")
    await state.clear()

@dp.callback_query(F.data == "back_to_main")
async def btn_back_to_main(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu(is_admin))
    await callback.answer()

@dp.callback_query(F.data == "delete_shift")
async def btn_delete_shift(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    users = await get_all_users()
    builder = InlineKeyboardBuilder()
    for uid, name, role in users:
        builder.button(text=f"{name} ({role}₽)", callback_data=f"deluser_{uid}")
    builder.adjust(2)
    await callback.message.answer("У кого удаляем смену?", reply_markup=builder.as_markup())
    await state.set_state(DeleteShiftState.waiting_for_user)
    await callback.answer()

@dp.callback_query(DeleteShiftState.waiting_for_user, F.data.startswith("deluser_"))
async def process_delete_user(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    shifts = await get_user_shifts(user_id)
    if not shifts:
        await callback.message.answer("У этого сотрудника нет смен.")
        await state.clear()
        return
    builder = InlineKeyboardBuilder()
    for shift in shifts:
        s_id, s_date, s_type, s_addr, _, _ = shift
        builder.button(text=f"❌ {s_date} ({s_type}) - {s_addr}", callback_data=f"delshift_{s_id}")
    builder.button(text="🔙 Отмена", callback_data="admin_panel")
    builder.adjust(1)
    await callback.message.answer("Выбери смену для удаления:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("delshift_"))
async def process_delete_shift(callback: types.CallbackQuery, state: FSMContext):
    shift_id = int(callback.data.split("_")[1])
    await delete_shift_by_id(shift_id)
    await callback.message.answer("✅ Смена удалена!")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "add_shift")
async def btn_add_shift(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    users = await get_all_users()
    builder = InlineKeyboardBuilder()
    for uid, name, role in users:
        builder.button(text=name, callback_data=f"shift_user_{uid}")
    builder.adjust(2)
    await callback.message.answer("Кому добавляем смену?", reply_markup=builder.as_markup())
    await state.set_state(AddShiftState.waiting_for_user)
    await callback.answer()

@dp.callback_query(AddShiftState.waiting_for_user, F.data.startswith("shift_user_"))
async def process_shift_user(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user_id=user_id)
    await callback.message.answer("Введи дату смены <b>ГГГГ-ММ-ДД</b>:", parse_mode="HTML")
    await state.set_state(AddShiftState.waiting_for_date)
    await callback.answer()

@dp.message(AddShiftState.waiting_for_date)
async def process_shift_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text)
    builder = InlineKeyboardBuilder()
    builder.button(text="Дневная", callback_data="type_Дневная")
    builder.button(text="Ночная", callback_data="type_Ночная")
    await message.answer("Тип смены:", reply_markup=builder.as_markup())
    await state.set_state(AddShiftState.waiting_for_type)

@dp.callback_query(AddShiftState.waiting_for_type, F.data.startswith("type_"))
async def process_shift_type(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(shift_type=callback.data.split("_")[1])
    await callback.message.answer("Адрес точки:")
    await state.set_state(AddShiftState.waiting_for_address)
    await callback.answer()

@dp.message(AddShiftState.waiting_for_address)
async def process_shift_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("Кого сменяешь? (или '-')")
    await state.set_state(AddShiftState.waiting_for_replaces)

@dp.message(AddShiftState.waiting_for_replaces)
async def process_shift_replaces(message: types.Message, state: FSMContext):
    await state.update_data(replaces=message.text)
    await message.answer("Кто сменяет? (или '-')")
    await state.set_state(AddShiftState.waiting_for_replaced_by)

@dp.message(AddShiftState.waiting_for_replaced_by)
async def process_shift_replaced_by(message: types.Message, state: FSMContext):
    await state.update_data(replaced_by=message.text)
    data = await state.get_data()
    added = await add_shift_to_db(data['target_user_id'], data['date'], data['shift_type'], data['address'], data['replaces'], message.text)
    if added:
        await message.answer("✅ Смена добавлена!", reply_markup=get_main_menu(True))
    else:
        await message.answer("⚠️ Такая смена уже есть!", reply_markup=get_main_menu(True))
    await state.clear()

@dp.callback_query(F.data == "import_gsheet")
async def btn_import_gsheet(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.answer("Введи месяц и год для загрузки (например: <b>10 2026</b>):", parse_mode="HTML")
    await state.set_state(ImportState.waiting_for_gsheet_date)
    await callback.answer()

@dp.message(ImportState.waiting_for_gsheet_date)
async def process_gsheet_date(message: types.Message, state: FSMContext):
    try:
        month_str, year_str = message.text.split()
        month, year = int(month_str), int(year_str)
    except ValueError:
        await message.answer("❌ Неверный формат. Напиши два числа через пробел.")
        return

    await message.answer("⏳ Скачиваю и обновляю данные...")
    success, result_msg = await process_and_save_sheet(month, year, is_auto=False)
    await message.answer(result_msg)
    await state.clear()

# --- ЗАПУСК ---
async def main():
    await init_db()
    asyncio.create_task(auto_sync_worker())
    
    print("Бот запущен...", flush=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
