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
    coach_style TEXT DEFAULT 'balanced'
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
    active BOOLEAN DEFAULT TRUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_reports (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    report_date DATE,
    percent INTEGER
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
    current = levels[0]
    next_level = None

    for i in range(len(levels)):
        if xp >= levels[i][0]:
            current = levels[i]
            if i + 1 < len(levels):
                next_level = levels[i + 1]
    return current, next_level


def progress_bar(current, total, length=10):
    if total == 0:
        return "█" * length
    filled = int(length * current / total)
    return "█" * filled + "░" * (length - filled)


# =========================
# INTELLIGENCE
# =========================

def detect_overload(history):
    if len(history) < 3:
        return False
    last_3 = history[:3]
    if all(p == 0 for p in last_3):
        return True
    avg = sum(history) / len(history)
    if avg < 40:
        return True
    return False


def generate_feedback(percent, history):
    overload = detect_overload(history)

    if overload:
        return "overload"

    if percent == 100:
        return "excellent"
    if percent >= 60:
        return "good"
    if percent == 0:
        return "fail"
    return "medium"


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

money_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚀 Новый источник дохода")],
        [KeyboardButton(text="⬆ Увеличить доход на работе")],
    ],
    resize_keyboard=True
)

# =========================
# START FLOW
# =========================

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.set_state(CoachStates.choosing_category)
    await message.answer(
        "👋 Добро пожаловать.\n\nВ какой сфере твоя цель?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="💰 Деньги")]],
            resize_keyboard=True
        )
    )


@dp.message(CoachStates.choosing_category, F.text == "💰 Деньги")
async def choose_money(message: Message, state: FSMContext):
    await state.set_state(CoachStates.choosing_money_direction)
    await message.answer("Что именно ты хочешь?", reply_markup=money_keyboard)


@dp.message(CoachStates.choosing_money_direction)
async def set_money_goal(message: Message, state: FSMContext):
    goal = message.text

    cursor.execute(
        """
        INSERT INTO users (user_id, goal)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET goal = EXCLUDED.goal
        """,
        (message.from_user.id, goal)
    )

    habits = [
        "30 минут работы над направлением",
        "1 контакт с потенциальным клиентом",
        "15 минут обучения"
    ]

    for habit in habits:
        cursor.execute(
            "INSERT INTO habits (user_id, name) VALUES (%s, %s)",
            (message.from_user.id, habit)
        )

    await message.answer(
        "✅ План создан.\nПривычки добавлены.",
        reply_markup=main_menu
    )

    await state.clear()


# =========================
# HABITS
# =========================

@dp.message(F.text == "📋 Мои привычки")
async def list_habits(message: Message):
    cursor.execute(
        "SELECT name, current_streak, best_streak FROM habits WHERE user_id=%s AND active=TRUE",
        (message.from_user.id,)
    )
    habits = cursor.fetchall()

    if not habits:
        await message.answer("Нет активных привычек.", reply_markup=main_menu)
        return

    text = "📋 Твои привычки:\n\n"
    for name, current, best in habits:
        text += f"{name}\n🔥 {current} | 🏆 {best}\n\n"

    await message.answer(text, reply_markup=main_menu)


@dp.message(F.text == "✅ Отметить привычку")
async def mark_list(message: Message):
    cursor.execute(
        "SELECT id, name FROM habits WHERE user_id=%s AND active=TRUE",
        (message.from_user.id,)
    )
    habits = cursor.fetchall()

    keyboard = [
        [InlineKeyboardButton(text=name, callback_data=f"check_{hid}")]
        for hid, name in habits
    ]

    await message.answer(
        "Выбери привычку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@dp.callback_query(F.data.startswith("check_"))
async def mark(callback: CallbackQuery):
    habit_id = int(callback.data.split("_")[1])
    today = date.today()

    cursor.execute(
        "SELECT current_streak, best_streak, last_check FROM habits WHERE id=%s",
        (habit_id,)
    )
    current, best, last = cursor.fetchone()

    if last == today:
        await callback.answer("Уже отмечено")
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

    cursor.execute(
        "SELECT xp FROM users WHERE user_id=%s",
        (callback.from_user.id,)
    )
    xp = cursor.fetchone()[0] or 0
    xp += 10
    cursor.execute(
        "UPDATE users SET xp=%s WHERE user_id=%s",
        (xp, callback.from_user.id)
    )

    level, _ = get_level_data(xp)

    await callback.message.edit_text(
        f"🔥 Выполнено!\n⭐ XP: {xp}\n🎮 Уровень: {level[1]}"
    )


# =========================
# EVENING REVIEW
# =========================

async def evening_broadcast(bot: Bot):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for (user_id,) in users:
        cursor.execute(
            "SELECT COUNT(*) FROM habits WHERE user_id=%s AND active=TRUE",
            (user_id,)
        )
        total = cursor.fetchone()[0]

        if total == 0:
            continue

        cursor.execute(
            "SELECT COUNT(*) FROM habits WHERE user_id=%s AND last_check=%s AND active=TRUE",
            (user_id, date.today())
        )
        completed = cursor.fetchone()[0]

        percent = int((completed / total) * 100)

        cursor.execute(
            "INSERT INTO daily_reports (user_id, report_date, percent) VALUES (%s, %s, %s)",
            (user_id, date.today(), percent)
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🧠 Разбор дня", callback_data="review")]
            ]
        )

        try:
            await bot.send_message(
                user_id,
                f"🌙 Сегодня выполнено {percent}%.\nГотов к разбору?",
                reply_markup=keyboard
            )
        except:
            pass


@dp.callback_query(F.data == "review")
async def review(callback: CallbackQuery):
    user_id = callback.from_user.id

    cursor.execute("""
        SELECT percent FROM daily_reports
        WHERE user_id=%s
        ORDER BY report_date DESC
        LIMIT 7
    """, (user_id,))

    history = [row[0] for row in cursor.fetchall()]
    today = history[0] if history else 0

    state = generate_feedback(today, history)

    if state == "overload":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Упростить систему", callback_data="simplify")],
                [InlineKeyboardButton(text="❌ Оставить", callback_data="keep")]
            ]
        )
        await callback.message.edit_text(
            "⚠ Перегруз системы.\nУпростим привычки?",
            reply_markup=keyboard
        )
        return

    responses = {
        "excellent": "🔥 Отличная дисциплина.",
        "good": "👍 Неплохо. Можно лучше.",
        "medium": "⚖ День частично продуктивный.",
        "fail": "🧠 Срыв — это сигнал, не конец."
    }

    await callback.message.edit_text(responses.get(state))


@dp.callback_query(F.data == "simplify")
async def simplify(callback: CallbackQuery):
    user_id = callback.from_user.id

    cursor.execute("""
        SELECT id FROM habits
        WHERE user_id=%s AND active=TRUE
        ORDER BY best_streak DESC
    """, (user_id,))
    habits = cursor.fetchall()

    if len(habits) <= 2:
        await callback.answer("Уже минимум.")
        return

    for habit in habits[2:]:
        cursor.execute(
            "UPDATE habits SET active=FALSE WHERE id=%s",
            (habit[0],)
        )

    await callback.message.edit_text(
        "✅ Оставлены 2 ключевые привычки.\nФокус = результат."
    )


# =========================
# LEVEL
# =========================

@dp.message(F.text == "🏅 Мой уровень")
async def level(message: Message):
    cursor.execute("SELECT xp FROM users WHERE user_id=%s", (message.from_user.id,))
    xp = cursor.fetchone()[0] or 0

    current, next_level = get_level_data(xp)

    if next_level:
        xp_into = xp - current[0]
        xp_needed = next_level[0] - current[0]
        bar = progress_bar(xp_into, xp_needed)
        text = f"{current[1]}\n⭐ XP: {xp}\n{bar}\n{xp_into}/{xp_needed}"
    else:
        text = f"👑 Максимальный уровень\n⭐ XP: {xp}"

    await message.answer(text, reply_markup=main_menu)


# =========================
# MAIN
# =========================

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)

    scheduler.add_job(
        evening_broadcast,
        trigger="cron",
        hour=21,
        minute=0,
        args=[bot]
    )
    scheduler.start()

    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())