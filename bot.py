import asyncio
import os
import psycopg2
from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
scheduler = AsyncIOScheduler()

# =========================
# DATABASE
# =========================

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
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    last_check DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
# KEYBOARDS
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
# MORNING ROUTINE
# =========================

async def morning_message(bot: Bot):
    cursor.execute("SELECT user_id, goal FROM users")
    users = cursor.fetchall()

    for user_id, goal in users:
        cursor.execute(
            "SELECT MAX(best_streak) FROM habits WHERE user_id = %s",
            (user_id,)
        )
        best = cursor.fetchone()[0] or 0

        text = (
            "☀ Доброе утро!\n\n"
            f"🎯 Твоя цель:\n{goal}\n\n"
            f"🔥 Твой лучший streak: {best} дней\n\n"
            "Сегодня важно не прервать серию.\n"
            "Отметь привычки вечером ✅"
        )

        try:
            await bot.send_message(user_id, text, reply_markup=main_menu)
        except:
            pass

# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в систему личного роста.\n\n"
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
        f"✅ Цель сохранена:\n\n🎯 {message.text}",
        reply_markup=main_menu
    )

    await state.clear()

# =========================
# HABITS & STREAK
# =========================

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

    await message.answer("✅ Привычка добавлена!", reply_markup=main_menu)
    await state.clear()

@dp.message(F.text == "✅ Отметить привычку")
async def check_habit(message: Message):
    cursor.execute(
        "SELECT id, name FROM habits WHERE user_id = %s",
        (message.from_user.id,)
    )
    habits = cursor.fetchall()

    if not habits:
        await message.answer("Нет привычек.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=h[1], callback_data=f"check_{h[0]}")]
            for h in habits
        ]
    )

    await message.answer("Выбери привычку:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("check_"))
async def mark(callback: CallbackQuery):
    habit_id = int(callback.data.split("_")[1])
    today = date.today()

    cursor.execute(
        "SELECT current_streak, best_streak, last_check FROM habits WHERE id = %s",
        (habit_id,)
    )
    habit = cursor.fetchone()

    if not habit:
        return

    current, best, last = habit

    if last == today:
        await callback.answer("Уже отмечено")
        return

    if last == today - timedelta(days=1):
        current += 1
    else:
        current = 1

    if current > best:
        best = current

    cursor.execute("""
        UPDATE habits
        SET current_streak=%s,
            best_streak=%s,
            last_check=%s
        WHERE id=%s
    """, (current, best, today, habit_id))

    conn.commit()

    await callback.answer("✅")
    await callback.message.edit_text(
        f"🔥 Текущая серия: {current}\n🏆 Рекорд: {best}"
    )

# =========================

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)

    scheduler.add_job(
        morning_message,
        trigger="cron",
        hour=9,
        minute=0,
        args=[bot]
    )
    scheduler.start()

    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())