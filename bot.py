import asyncio
import os
import psycopg2
import random
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# =========================
# DATABASE
# =========================

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    amount INTEGER,
    description TEXT,
    category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# =========================
# CATEGORY LOGIC
# =========================

def detect_category(description, amount):
    text = description.lower()

    if amount > 0:
        return "💰 Доход"

    if any(word in text for word in ["кофе", "еда", "продукт", "ресторан"]):
        return "🍔 Еда"

    if any(word in text for word in ["аренда", "квартира", "жилье"]):
        return "🏠 Жильё"

    if any(word in text for word in ["такси", "бензин", "метро"]):
        return "🚗 Транспорт"

    if any(word in text for word in ["кино", "игра", "развлеч"]):
        return "🎮 Развлечения"

    if any(word in text for word in ["аптека", "врач"]):
        return "💊 Здоровье"

    return "📦 Другое"


def parse_transaction(text):
    text = text.strip()
    if text.startswith("+") or text.startswith("-"):
        try:
            parts = text.split(" ", 1)
            amount = int(parts[0])
            description = parts[1] if len(parts) > 1 else "без описания"
            return amount, description
        except:
            return None
    return None


def get_balance(user_id):
    cursor.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = %s",
        (user_id,)
    )
    return cursor.fetchone()[0]


def get_category_count_today(user_id, category):
    cursor.execute("""
        SELECT COUNT(*)
        FROM transactions
        WHERE user_id = %s
        AND category = %s
        AND created_at::date = CURRENT_DATE
    """, (user_id, category))
    return cursor.fetchone()[0]


# =========================
# HUMOR & TIPS
# =========================

FOOD_JOKES = [
    "🍔 Желудок доволен. Бюджет — не очень.",
    "☕ Ты уже спонсируешь кофейню.",
    "🍕 Вкусно жить не запретишь."
]

TRANSPORT_JOKES = [
    "🚖 Такси? Ноги ещё работают.",
    "⛽ Машина ест больше тебя."
]

FUN_JOKES = [
    "🎮 Сначала кайф, потом отчёт.",
    "🍿 Развлечения — дорогое удовольствие."
]

BIG_SPEND = [
    "💣 Серьёзная трата. Ты уверен?",
    "🔥 Бюджет только что почувствовал боль.",
    "💸 Это было громко."
]

INCOME_JOKES = [
    "💰 Деньги пришли. Не слей их за выходные.",
    "🤑 Богатей. Но с умом."
]

TIPS = [
    "💡 Совет: откладывай 10% сразу.",
    "💡 Совет: мелкие траты в год — это большие деньги.",
    "💡 Совет: подписки — тихий убийца бюджета.",
    "💡 Совет: попробуй правило 24 часов перед покупкой."
]

# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "💰 Финансовый тренер.\n\n"
        "Пиши операции так:\n"
        "+150000 зарплата\n"
        "-350 кофе\n\n"
        "Команды:\n"
        "/balance — баланс\n"
        "/report — отчёт за месяц\n"
        "/categories — расходы по категориям"
    )

# =========================
# BALANCE
# =========================

@dp.message(Command("balance"))
async def balance(message: Message):
    total = get_balance(message.from_user.id)
    await message.answer(f"💰 Баланс: {total} ₽")

# =========================
# REPORT
# =========================

@dp.message(Command("report"))
async def report(message: Message):
    user_id = message.from_user.id
    now = datetime.now()
    month_start = now.replace(day=1)

    cursor.execute("""
        SELECT amount FROM transactions
        WHERE user_id = %s AND created_at >= %s
    """, (user_id, month_start))

    rows = cursor.fetchall()

    income = sum(r[0] for r in rows if r[0] > 0)
    expense = sum(r[0] for r in rows if r[0] < 0)

    await message.answer(
        f"📊 Отчёт за месяц:\n\n"
        f"Доходы: {income} ₽\n"
        f"Расходы: {abs(expense)} ₽\n"
        f"Баланс: {income + expense} ₽"
    )

# =========================
# CATEGORY REPORT
# =========================

@dp.message(Command("categories"))
async def categories(message: Message):
    user_id = message.from_user.id
    now = datetime.now()
    month_start = now.replace(day=1)

    cursor.execute("""
        SELECT category, SUM(amount)
        FROM transactions
        WHERE user_id = %s
        AND amount < 0
        AND created_at >= %s
        GROUP BY category
    """, (user_id, month_start))

    rows = cursor.fetchall()

    if not rows:
        await message.answer("Нет данных.")
        return

    text = "📊 Расходы по категориям:\n\n"
    for category, total in rows:
        text += f"{category}: {abs(total)} ₽\n"

    await message.answer(text)

# =========================
# TRANSACTION HANDLER
# =========================

@dp.message()
async def handle_transaction(message: Message):
    parsed = parse_transaction(message.text)

    if not parsed:
        await message.answer("Формат: +1000 зарплата или -350 кофе")
        return

    amount, description = parsed
    category = detect_category(description, amount)

    cursor.execute(
        "INSERT INTO transactions (user_id, amount, description, category) VALUES (%s, %s, %s, %s)",
        (message.from_user.id, amount, description, category)
    )

    total = get_balance(message.from_user.id)

    if amount > 0:
        joke = random.choice(INCOME_JOKES)
        response = f"✅ Доход {amount} ₽\n💰 Баланс: {total} ₽\n\n{joke}"
    else:
        response = f"✅ Расход {abs(amount)} ₽\n💰 Баланс: {total} ₽"

        if abs(amount) > 10000:
            response += f"\n\n{random.choice(BIG_SPEND)}"

        if category == "🍔 Еда":
            response += f"\n\n{random.choice(FOOD_JOKES)}"
        elif category == "🚗 Транспорт":
            response += f"\n\n{random.choice(TRANSPORT_JOKES)}"
        elif category == "🎮 Развлечения":
            response += f"\n\n{random.choice(FUN_JOKES)}"

        count_today = get_category_count_today(message.from_user.id, category)
        if count_today >= 3:
            response += f"\n\n🤨 Уже {count_today} раза сегодня по категории {category}."

    if random.random() < 0.35:
        response += f"\n\n{random.choice(TIPS)}"

    await message.answer(response)

# =========================

async def main():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())