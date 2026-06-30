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
    first_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

# На случай если таблицы уже были созданы раньше без этих колонок
cursor.execute("""
ALTER TABLE users
ADD COLUMN IF NOT EXISTS first_name TEXT
""")

cursor.execute("""
ALTER TABLE users
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
""")

cursor.execute("""
ALTER TABLE habits
ADD COLUMN IF NOT EXISTS current_streak INTEGER DEFAULT 0
""")

cursor.execute("""
ALTER TABLE habits
ADD COLUMN IF NOT EXISTS best_streak INTEGER DEFAULT 0
""")

cursor.execute("""
ALTER TABLE habits
ADD COLUMN IF NOT EXISTS last_check DATE
""")


# =========================
# FSM
# =========================

class Form(StatesGroup):
    waiting_for_goal = State()
    waiting_for_habit = State()


# =========================
# KEYBOARDS
# =========================

start_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚀 Начать")]
    ],
    resize_keyboard=True
)

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


# =========================
# HELPERS
# =========================

def get_user_goal(user_id: int):
    cursor.execute(
        "SELECT goal FROM users WHERE user_id = %s",
        (user_id,)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def get_best_streak(user_id: int):
    cursor.execute(
        "SELECT MAX(best_streak) FROM habits WHERE user_id = %s",
        (user_id,)
    )
    result = cursor.fetchone()
    return result[0] or 0


async def send_morning_message_to_user(bot: Bot, user_id: int, first_name: str, goal: str):
    best_streak = get_best_streak(user_id)

    name = first_name if first_name else "друг"

    text = (
        f"☀️ Доброе утро, {name}!\n\n"
        f"🎯 Твоя цель:\n{goal if goal else 'Пока не установлена'}\n\n"
        f"🔥 Твой лучший streak: {best_streak} дней\n\n"
        "Сегодня не нужно менять всю жизнь.\n"
        "Достаточно сделать маленькое действие и не прервать движение.\n\n"
        "Вечером не забудь отметить привычки ✅"
    )

    try:
        await bot.send_message(user_id, text, reply_markup=main_menu)
    except Exception as e:
        print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")


async def morning_broadcast(bot: Bot):
    cursor.execute("SELECT user_id, first_name, goal FROM users")
    users = cursor.fetchall()

    for user_id, first_name, goal in users:
        await send_morning_message_to_user(bot, user_id, first_name, goal)


# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в систему личного роста.\n\n"
        "Здесь ты будешь двигаться к своей цели через ежедневные привычки.\n\n"
        "Как это работает:\n"
        "1. Ставишь цель на 3 месяца\n"
        "2. Создаёшь 1–5 привычек\n"
        "3. Каждый день отмечаешь выполнение\n"
        "4. Следишь за серией и прогрессом\n\n"
        "Готов начать?",
        reply_markup=start_keyboard
    )


@dp.message(F.text == "🚀 Начать")
async def ask_goal(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_goal)

    await message.answer(
        "🎯 Напиши свою главную цель на ближайшие 3 месяца.\n\n"
        "Примеры:\n"
        "• Увеличить доход до 200 000 ₽\n"
        "• Похудеть на 7 кг\n"
        "• Запустить свой проект\n"
        "• Читать каждый день\n\n"
        "Напиши цель одним сообщением:"
    )


@dp.message(Form.waiting_for_goal)
async def save_goal(message: Message, state: FSMContext):
    cursor.execute(
        """
        INSERT INTO users (user_id, goal, first_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET goal = EXCLUDED.goal,
                      first_name = EXCLUDED.first_name
        """,
        (message.from_user.id, message.text, message.from_user.first_name)
    )

    await message.answer(
        f"✅ Цель сохранена:\n\n"
        f"🎯 {message.text}\n\n"
        "Теперь следующий шаг — создать привычку, которая будет приближать тебя к цели.\n\n"
        "Нажми кнопку:\n"
        "➕ Добавить привычку",
        reply_markup=main_menu
    )

    await state.clear()


# =========================
# GOAL
# =========================

@dp.message(F.text == "🎯 Моя цель")
async def show_goal(message: Message):
    goal = get_user_goal(message.from_user.id)

    if goal:
        await message.answer(
            f"🎯 Твоя текущая цель:\n\n{goal}\n\n"
            "Двигайся к ней через маленькие ежедневные действия."
        )
    else:
        await message.answer(
            "У тебя пока нет цели.\n\n"
            "Нажми 🚀 Начать, чтобы установить цель.",
            reply_markup=start_keyboard
        )


# =========================
# ADD HABIT
# =========================

@dp.message(F.text == "➕ Добавить привычку")
async def add_habit(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_habit)

    await message.answer(
        "Напиши название новой привычки.\n\n"
        "Примеры:\n"
        "• Читать 20 минут\n"
        "• Сделать зарядку\n"
        "• Не есть сладкое\n"
        "• Сделать 1 шаг по проекту\n"
        "• Учить английский 15 минут"
    )


@dp.message(Form.waiting_for_habit)
async def save_habit(message: Message, state: FSMContext):
    goal = get_user_goal(message.from_user.id)

    if not goal:
        await message.answer(
            "Сначала нужно установить цель.\n\n"
            "Нажми 🚀 Начать.",
            reply_markup=start_keyboard
        )
        await state.clear()
        return

    cursor.execute(
        "INSERT INTO habits (user_id, name) VALUES (%s, %s)",
        (message.from_user.id, message.text)
    )

    await message.answer(
        f"✅ Привычка добавлена:\n\n"
        f"📌 {message.text}\n\n"
        "Теперь каждый день отмечай её выполнение через кнопку:\n"
        "✅ Отметить привычку",
        reply_markup=main_menu
    )

    await state.clear()


# =========================
# LIST HABITS
# =========================

@dp.message(F.text == "📋 Мои привычки")
async def list_habits(message: Message):
    cursor.execute(
        """
        SELECT id, name, current_streak, best_streak, last_check
        FROM habits
        WHERE user_id = %s
        ORDER BY id
        """,
        (message.from_user.id,)
    )

    habits = cursor.fetchall()

    if not habits:
        await message.answer(
            "У тебя пока нет привычек.\n\n"
            "Нажми ➕ Добавить привычку.",
            reply_markup=main_menu
        )
        return

    text = "📋 Твои привычки:\n\n"

    for habit_id, name, current_streak, best_streak, last_check in habits:
        status = "✅ сегодня выполнено" if last_check == date.today() else "⏳ сегодня ещё не отмечено"

        text += (
            f"{habit_id}. {name}\n"
            f"   🔥 Серия: {current_streak} дней\n"
            f"   🏆 Рекорд: {best_streak} дней\n"
            f"   {status}\n\n"
        )

    await message.answer(text, reply_markup=main_menu)


# =========================
# CHECK HABIT
# =========================

@dp.message(F.text == "✅ Отметить привычку")
async def check_habit(message: Message):
    cursor.execute(
        """
        SELECT id, name, last_check
        FROM habits
        WHERE user_id = %s
        ORDER BY id
        """,
        (message.from_user.id,)
    )

    habits = cursor.fetchall()

    if not habits:
        await message.answer(
            "У тебя пока нет привычек.\n\n"
            "Сначала нажми ➕ Добавить привычку.",
            reply_markup=main_menu
        )
        return

    buttons = []

    for habit_id, name, last_check in habits:
        if last_check == date.today():
            button_text = f"✅ {name}"
        else:
            button_text = f"⬜ {name}"

        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"check_{habit_id}"
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "Выбери привычку, которую выполнил сегодня:",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("check_"))
async def mark_habit(callback: CallbackQuery):
    habit_id = int(callback.data.split("_")[1])
    today = date.today()

    cursor.execute(
        """
        SELECT current_streak, best_streak, last_check, name
        FROM habits
        WHERE id = %s
        """,
        (habit_id,)
    )

    habit = cursor.fetchone()

    if not habit:
        await callback.answer("Привычка не найдена")
        return

    current_streak, best_streak, last_check, habit_name = habit

    if last_check == today:
        await callback.answer("Сегодня уже отмечено ✅")
        return

    if last_check == today - timedelta(days=1):
        current_streak += 1
    else:
        current_streak = 1

    if current_streak > best_streak:
        best_streak = current_streak

    cursor.execute(
        """
        UPDATE habits
        SET current_streak = %s,
            best_streak = %s,
            last_check = %s
        WHERE id = %s
        """,
        (current_streak, best_streak, today, habit_id)
    )

    await callback.answer("✅ Отмечено")

    await callback.message.edit_text(
        f"🔥 Привычка выполнена!\n\n"
        f"📌 {habit_name}\n\n"
        f"Текущая серия: {current_streak} дней\n"
        f"Лучший результат: {best_streak} дней\n\n"
        "Продолжай. Главное — не идеальность, а движение."
    )


# =========================
# STATS
# =========================

@dp.message(F.text == "📊 Статистика")
async def stats(message: Message):
    user_id = message.from_user.id
    today = date.today()

    cursor.execute(
        "SELECT COUNT(*) FROM habits WHERE user_id = %s",
        (user_id,)
    )
    total_habits = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM habits
        WHERE user_id = %s AND last_check = %s
        """,
        (user_id, today)
    )
    completed_today = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT MAX(best_streak)
        FROM habits
        WHERE user_id = %s
        """,
        (user_id,)
    )
    best_streak = cursor.fetchone()[0] or 0

    if total_habits == 0:
        await message.answer(
            "📊 Статистика пока пустая.\n\n"
            "Добавь первую привычку через ➕ Добавить привычку.",
            reply_markup=main_menu
        )
        return

    percent = round((completed_today / total_habits) * 100)

    await message.answer(
        f"📊 Твоя статистика на сегодня:\n\n"
        f"✅ Выполнено: {completed_today} из {total_habits}\n"
        f"📈 Прогресс дня: {percent}%\n"
        f"🏆 Лучший streak: {best_streak} дней\n\n"
        "Даже один маленький шаг сегодня — это вклад в будущего тебя.",
        reply_markup=main_menu
    )


# =========================
# TEST MORNING
# =========================

@dp.message(Command("testmorning"))
async def test_morning(message: Message, bot: Bot):
    goal = get_user_goal(message.from_user.id)

    await send_morning_message_to_user(
        bot=bot,
        user_id=message.from_user.id,
        first_name=message.from_user.first_name,
        goal=goal
    )


# =========================
# FALLBACK
# =========================

@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Я пока понимаю только кнопки меню 👇\n\n"
        "Выбери действие:",
        reply_markup=main_menu
    )


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