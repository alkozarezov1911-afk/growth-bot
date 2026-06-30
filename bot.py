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
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# =========================
# DATABASE
# =========================

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    goal TEXT,
    xp INTEGER DEFAULT 0,
    first_name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS habits (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    last_check DATE
)
""")

# =========================
# LEVEL SYSTEM
# =========================

def get_level_data(xp: int):
    levels = [
        (0, "🥉 Новичок"),
        (100, "🥈 Дисциплинированный"),
        (300, "🥇 Машина"),
        (700, "🏆 Мастер"),
        (1500, "👑 Легенда"),
    ]

    current_level = levels[0]
    next_level = None

    for i in range(len(levels)):
        if xp >= levels[i][0]:
            current_level = levels[i]
            if i + 1 < len(levels):
                next_level = levels[i + 1]

    return current_level, next_level


def progress_bar(current, total, length=10):
    if total == 0:
        return "█" * length
    filled = int(length * current / total)
    return "█" * filled + "░" * (length - filled)


# =========================
# FSM
# =========================

class CoachStates(StatesGroup):
    choosing_category = State()
    choosing_money_direction = State()
    waiting_for_habit = State()


# =========================
# KEYBOARDS
# =========================

start_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚀 Начать")]],
    resize_keyboard=True
)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎯 Моя цель")],
        [KeyboardButton(text="➕ Добавить привычку")],
        [KeyboardButton(text="✅ Отметить привычку")],
        [KeyboardButton(text="📋 Мои привычки")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🏅 Мой уровень")],
    ],
    resize_keyboard=True
)

money_directions_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⬆ Увеличить доход на работе")],
        [KeyboardButton(text="🚀 Новый источник дохода")],
        [KeyboardButton(text="📈 Запустить проект")],
        [KeyboardButton(text="🧠 Освоить навык")],
        [KeyboardButton(text="💳 Финансовая дисциплина")],
    ],
    resize_keyboard=True
)

# =========================
# MORNING ROUTINE
# =========================

async def morning_broadcast(bot: Bot):
    cursor.execute("SELECT user_id, first_name, goal FROM users")
    users = cursor.fetchall()

    for user_id, first_name, goal in users:
        cursor.execute(
            "SELECT MAX(best_streak) FROM habits WHERE user_id = %s",
            (user_id,)
        )
        best = cursor.fetchone()[0] or 0

        text = (
            f"☀ Доброе утро, {first_name or ''}!\n\n"
            f"🎯 Твоя цель: {goal}\n\n"
            f"🔥 Лучший streak: {best} дней\n\n"
            "Сегодня главное — сделать хотя бы 1 шаг.\n"
            "Вечером не забудь отметить привычки ✅"
        )

        try:
            await bot.send_message(user_id, text, reply_markup=main_menu)
        except:
            pass


# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.set_state(CoachStates.choosing_category)

    await message.answer(
        "👋 Добро пожаловать в коуч‑режим.\n\n"
        "В какой сфере твоя цель?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="💰 Деньги")]],
            resize_keyboard=True
        )
    )


@dp.message(CoachStates.choosing_category, F.text == "💰 Деньги")
async def choose_money_direction(message: Message, state: FSMContext):
    await state.set_state(CoachStates.choosing_money_direction)
    await message.answer("Что именно ты хочешь?", reply_markup=money_directions_keyboard)


@dp.message(CoachStates.choosing_money_direction)
async def generate_plan(message: Message, state: FSMContext):
    direction = message.text

    plans = {
        "⬆ Увеличить доход на работе": [
            "30 минут развития ключевого навыка",
            "1 улучшение рабочего процесса",
            "Записывать достижения"
        ],
        "🚀 Новый источник дохода": [
            "30 минут работы над направлением",
            "1 контакт с потенциальным клиентом",
            "15 минут обучения"
        ],
        "📈 Запустить проект": [
            "1 тест гипотезы",
            "1 разговор с клиентом",
            "Анализ конкурентов"
        ],
        "🧠 Освоить навык": [
            "40 минут обучения",
            "Практическое применение",
            "Мини‑проект каждую неделю"
        ],
        "💳 Финансовая дисциплина": [
            "Записывать расходы",
            "Планировать бюджет",
            "Откладывать 10%"
        ],
    }

    if direction not in plans:
        await message.answer("Выбери вариант из кнопок.")
        return

    cursor.execute(
        """
        INSERT INTO users (user_id, goal, first_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET goal = EXCLUDED.goal
        """,
        (message.from_user.id, direction, message.from_user.first_name)
    )

    for habit in plans[direction]:
        cursor.execute(
            "INSERT INTO habits (user_id, name) VALUES (%s, %s)",
            (message.from_user.id, habit)
        )

    await message.answer(
        f"✅ Цель установлена: {direction}\n\n"
        "📌 Привычки созданы автоматически.",
        reply_markup=main_menu
    )

    await state.clear()


# =========================
# HABITS
# =========================

@dp.message(F.text == "➕ Добавить привычку")
async def add_habit(message: Message, state: FSMContext):
    await state.set_state(CoachStates.waiting_for_habit)
    await message.answer("Напиши название новой привычки:")


@dp.message(CoachStates.waiting_for_habit)
async def save_habit(message: Message, state: FSMContext):
    cursor.execute(
        "INSERT INTO habits (user_id, name) VALUES (%s, %s)",
        (message.from_user.id, message.text)
    )

    await message.answer("✅ Привычка добавлена!", reply_markup=main_menu)
    await state.clear()


@dp.message(F.text == "📋 Мои привычки")
async def list_habits(message: Message):
    cursor.execute(
        "SELECT name, current_streak, best_streak FROM habits WHERE user_id = %s",
        (message.from_user.id,)
    )
    habits = cursor.fetchall()

    if not habits:
        await message.answer("Нет привычек.", reply_markup=main_menu)
        return

    text = "📋 Твои привычки:\n\n"
    for name, current, best in habits:
        text += f"{name}\n🔥 {current} | 🏆 {best}\n\n"

    await message.answer(text, reply_markup=main_menu)


@dp.message(F.text == "✅ Отметить привычку")
async def check_habit(message: Message):
    cursor.execute(
        "SELECT id, name FROM habits WHERE user_id = %s",
        (message.from_user.id,)
    )
    habits = cursor.fetchall()

    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"check_{hid}")]
        for hid, name in habits
    ]

    await message.answer(
        "Выбери привычку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("check_"))
async def mark_habit(callback: CallbackQuery):
    habit_id = int(callback.data.split("_")[1])
    today = date.today()

    cursor.execute(
        "SELECT current_streak, best_streak, last_check, name FROM habits WHERE id=%s",
        (habit_id,)
    )
    current, best, last, name = cursor.fetchone()

    if last == today:
        await callback.answer("Сегодня уже отмечено ✅")
        return

    if last == today - timedelta(days=1):
        current += 1
    else:
        current = 1

    if current > best:
        best = current

    cursor.execute(
        "UPDATE habits SET current_streak=%s, best_streak=%s, last_check=%s WHERE id=%s",
        (current, best, today, habit_id)
    )

    # XP
    cursor.execute("SELECT xp FROM users WHERE user_id=%s", (callback.from_user.id,))
    xp = cursor.fetchone()[0] or 0
    xp += 10
    cursor.execute("UPDATE users SET xp=%s WHERE user_id=%s", (xp, callback.from_user.id))

    level, next_level = get_level_data(xp)

    await callback.answer("✅")
    await callback.message.edit_text(
        f"🔥 {name} выполнена!\n\n"
        f"Серия: {current}\n"
        f"⭐ XP: {xp}\n"
        f"🎮 Уровень: {level[1]}"
    )


# =========================
# LEVEL
# =========================

@dp.message(F.text == "🏅 Мой уровень")
async def show_level(message: Message):
    cursor.execute("SELECT xp FROM users WHERE user_id=%s", (message.from_user.id,))
    xp = cursor.fetchone()[0] or 0

    current_level, next_level = get_level_data(xp)

    if next_level:
        xp_current = current_level[0]
        xp_next = next_level[0]

        xp_into = xp - xp_current
        xp_needed = xp_next - xp_current

        bar = progress_bar(xp_into, xp_needed)

        text = (
            f"🎮 {current_level[1]}\n"
            f"⭐ XP: {xp}\n\n"
            f"{bar}\n"
            f"{xp_into}/{xp_needed} XP\n"
            f"Следующий: {next_level[1]}"
        )
    else:
        text = f"👑 Максимальный уровень!\n⭐ XP: {xp}"

    await message.answer(text, reply_markup=main_menu)


# =========================
# MAIN
# =========================

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)

    scheduler.add_job(
        morning_broadcast,
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