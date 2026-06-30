import asyncio
import os
import psycopg2
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

dp = Dispatcher()

# --- Подключение к PostgreSQL ---
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# --- Таблица пользователей ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    goal TEXT
)
""")

# --- Таблица привычек ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS habits (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

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
async def add_habit(message: Message):
    await message.answer(
        "Напиши название новой привычки:"
    )

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

@dp.message()
async def handle_text(message: Message):
    text = message.text

    # Проверяем есть ли цель
    cursor.execute(
        "SELECT goal FROM users WHERE user_id = %s",
        (message.from_user.id,)
    )
    existing_goal = cursor.fetchone()

    # Если цели нет — сохраняем как цель
    if not existing_goal:
        cursor.execute(
            "INSERT INTO users (user_id, goal) VALUES (%s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET goal = EXCLUDED.goal",
            (message.from_user.id, text)
        )
        conn.commit()

        await message.answer(
            f"✅ Цель сохранена:\n\n🎯 {text}"
        )
        return

    # Иначе — добавляем как привычку
    cursor.execute(
        "INSERT INTO habits (user_id, name) VALUES (%s, %s)",
        (message.from_user.id, text)
    )
    conn.commit()

    await message.answer(
        f"✅ Привычка добавлена:\n\n📌 {text}"
    )

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())