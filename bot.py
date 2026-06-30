import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message

TOKEN = "8624342975:AAG8_NoTtSeKBQMMsQazIYu_642yNtTiZf4"
dp = Dispatcher()

@dp.message()
async def echo(message: Message):
    print("Получено сообщение:", message.text)
    await message.answer("Я получил твоё сообщение ✅")

async def main():
    print("Бот запускается...")
    bot = Bot(token=TOKEN)

    await bot.delete_webhook(drop_pending_updates=True)

    print("Бот запущен и ждёт сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())