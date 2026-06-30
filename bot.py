import asyncio
import os
import psycopg2
from datetime import date
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- PostgreSQL ---
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    goal TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS habits (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS habit_logs (
    id SERIAL PRIMARY KEY,
    habit_id INTEGER REFERENCES habits(id) ON DELETE CASCADE,
    log_date DATE NOT NULL
)
""")

conn.commit()

# =========================
# FSM
# =========================

class Form(StatesGroup):
    waiting_for_goal = State()
    waiting_for_habit = State()

# =========================
# Клавиатуры
# =========================

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎯 Моя цель")],
        [KeyboardButton(text="➕ Добавить привычку")],
        [KeyboardButton(text="✅ Отметить привычку")],
        [KeyboardButton(text="📋 Мои привычки")],
        [KeyboardButton(text="📊 Статистика")],
    ],
    resize_keyboard=True
)

start_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚀 Начать")]],
    resize_keyboard=True
)

# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в систему личного роста.\n\n"
        "Здесь ты будешь двигаться к своей цели через ежедневные привычки.\n\n"
        "Готов начать?",
        reply_markup=start_keyboard
    )

@dp.message(F.text == "🚀 Начать")
async def ask_goal(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_goal)
    await message.answer("Напиши свою главную цель на 3 месяца:")

@dp.message(Form.waiting_for_goal)
async def save_goal(message: Message, state: FSMContext):
    cursor.execute(
        "INSERT INTO users (user_id, goal) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET goal = EXCLUDED.goal",
        (message.from_user.id, message.text)
    )
    conn.commit()

    await message.answer(
        f"✅ Цель сохранена:\n\n🎯 {message.text}\n\n"
        "Теперь создай первую привычку 👇",
        reply_markup=main_menu
    )

    await state.clear()

# =========================
# МЕНЮ
# =========================

@dp.message(F.text == "🎯 Моя цель")
async def show_goal(message: Message):
    cursor.execute(
        "SELECT goal FROM users WHERE user_id = %s",
        (message.from_user.id,)
    )
    result = cursor.fetchone()

    if result:
        await message.answer(f"🎯 Твоя цель:\n\n{result[0]}")
    else:
        await message.answer("Сначала установи цель через 🚀 Начать")

@dp.message(F.text == "➕ Добавить привычку")
async def add_habit(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_habit)
    await message.answer("Напиши название новой привычки:")

@dp.message(Form.waiting_for_habit)
async def save_habit(message: Message, state: FSMContext):
    cursor.execute(
        "INSERT INTO habits (user_id, name) VALUES (%s, %s)",
        (message.from_user.id, message.text)
    )
    conn.commit()

    await message.answer(
        f"✅ Привычка добавлена:\n\n📌 {message.text}",
        reply_markup=main_menu
    )

    await state.clear()

@dp.message(F.text == "📋 Мои привычки")
async def list_habits(message: Message):
    cursor.execute(
        "SELECT id, name FROM habits WHERE user_id = %s",
        (message.from_user.id,)
    )
    habits = cursor.fetchall()

    if not habits:
        await message.answer("У тебя пока нет привычек.")
        return

    text = "📋 Твои привычки:\n\n"
    for habit in habits:
        text += f"{habit[0]}. {habit[1]}\n"

    await message.answer(text)

@dp.message(F.text == "✅ Отметить привычку")
async def check_habit(message: Message):
    cursor.execute(
        "SELECT id, name FROM habits WHERE user_id = %s",
        (message.from_user.id,)
    )
    habits = cursor.fetchall()

    if not habits:
        await message.answer("У тебя нет привычек.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=habit[1], callback_data=f"check_{habit[0]}")]
            for habit in habits
        ]
    )

    await message.answer("Выбери привычку:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("check_"))
async def mark_habit(callback: CallbackQuery):
    habit_id = int(callback.data.split("_")[1])

    cursor.execute(
        "INSERT INTO habit_logs (habit_id, log_date) VALUES (%s, %s)",
        (habit_id, date.today())
    )
    conn.commit()

    await callback.answer("✅ Отмечено")
    await callback.message.edit_text("✅ Привычка отмечена на сегодня")

@dp.message(F.text == "📊 Статистика")
async def stats(message: Message):
    cursor.execute("""
        SELECT COUNT(*) FROM habit_logs hl
        JOIN habits h ON h.id = hl.habit_id
        WHERE h.user_id = %s AND hl.log_date = %s
    """, (message.from_user.id, date.today()))

    today_count = cursor.fetchone()[0]

    await message.answer(
        f"📊 Сегодня выполнено привычек: {today_count}"
    )

# =========================

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())