import asyncio
import os
import psycopg2
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
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

conn.commit()

# --- Состояния ---
class Form(StatesGroup):
    waiting_for_goal = State()
    waiting_for_habit = State()

# --- Кнопка ---
start_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚀 Начать")]
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет 👋\n\n"
        "Я твой бот личностного роста.\n"
        "Я помогу тебе сфокусироваться на главной цели.\n\n"
        "Готов начать?",
        reply_markup=start_keyboard
    )

@dp.message(F.text == "🚀 Начать")
async def ask_goal(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_goal)
    await message.answer(
        "Напиши свою главную цель на ближайшие 3 месяца:"
    )

@dp.message(Form.waiting_for_goal)
async def save_goal(message: Message, state: FSMContext):
    cursor.execute(
        "INSERT INTO users (user_id, goal) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET goal = EXCLUDED.goal",
        (message.from_user.id, message.text)
    )
    conn.commit()

    await message.answer(
        f"✅ Цель сохранена:\n\n🎯 {message.text}"
    )

    await state.clear()

@dp.message(Command("goal"))
async def show_goal(message: Message):
    cursor.execute(
        "SELECT goal FROM users WHERE user_id = %s",
        (message.from_user.id,)
    )
    result = cursor.fetchone()

    if result:
        await message.answer(
            f"🎯 Твоя текущая цель:\n\n{result[0]}"
        )
    else:
        await message.answer(
            "У тебя пока нет сохранённой цели.\n\nНажми 🚀 Начать"
        )

@dp.message(Command("addhabit"))
async def add_habit(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_habit)
    await message.answer(
        "Напиши название новой привычки:"
    )

@dp.message(Form.waiting_for_habit)
async def save_habit(message: Message, state: FSMContext):
    cursor.execute(
        "INSERT INTO habits (user_id, name) VALUES (%s, %s)",
        (message.from_user.id, message.text)
    )
    conn.commit()

    await message.answer(
        f"✅ Привычка добавлена:\n\n📌 {message.text}"
    )

    await state.clear()

@dp.message(Command("habits"))
async def list_habits(message: Message):
    cursor.execute(
        "SELECT id, name FROM habits WHERE user_id = %s",
        (message.from_user.id,)
    )
    habits = cursor.fetchall()

    if not habits:
        await message.answer("У тебя пока нет привычек.")
        return

    response = "📋 Твои привычки:\n\n"
    for habit in habits:
        response += f"{habit[0]}. {habit[1]}\n"

    await message.answer(response)

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())