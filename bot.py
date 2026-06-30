import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()

# Временное хранилище целей
user_goals = {}

# Кнопка "Начать"
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
async def ask_goal(message: Message):
    await message.answer(
        "Отлично 💪\n\n"
        "Напиши свою главную цель на ближайшие 3 месяца:"
    )

@dp.message()
async def save_goal(message: Message):
    user_goals[message.from_user.id] = message.text
    
    await message.answer(
        f"✅ Цель сохранена:\n\n"
        f"🎯 {message.text}\n\n"
        "Скоро начнём работать над ней."
    )

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())