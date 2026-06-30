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

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    goal TEXT
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

@dp.message(F.text == "🚀 Начать")
async def ask_goal(message: Message):
    await message.answer(
        "Отлично 💪\n\n"
        "Напиши свою главную цель на ближайшие 3 месяца:"
    )

@dp.message()
async def save_goal(message: Message):
    cursor.execute(
        "INSERT INTO users (user_id, goal) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET goal = EXCLUDED.goal",
        (message.from_user.id, message.text)
    )
    conn.commit()

    await message.answer(
        f"✅ Цель сохранена:\n\n"
        f"🎯 {message.text}\n\n"
        "Теперь она хранится в PostgreSQL 💾"
    )

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())