import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from dotenv import load_dotenv

from db import (
    init_db, search_performers, get_performer, count_performers,
    list_performers, import_csv, set_discipline_rating, get_discipline_rating
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USERS = {
    int(x.strip()) for x in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
    if x.strip().isdigit()
}
PAGE_SIZE = 10

MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="🧰 По специальности")],
        [KeyboardButton(text="📋 Все исполнители"), KeyboardButton(text="ℹ️ Помощь")],
    ],
    resize_keyboard=True,
)

def is_allowed(user_id: int) -> bool:
    # Пустой список разрешённых идентификаторов по умолчанию запрещает доступ: указать разрешённые Telegram ID
    return user_id in ALLOWED_USERS

def performer_card(p: dict) -> str:
    stars = "★" if p["willing_to_work"] else "☆"
    stars += "★" if p["has_tools"] else "☆"
    stars += "★" if p["has_car"] else "☆"
    discipline = get_discipline_rating(p["id"])
    stars += "★" if discipline and discipline["score"] else "☆"
    discipline_text = "Не оценена"
    if discipline:
        discipline_text = f'{discipline["score"]}/1 — оценил(а) {discipline["author_name"]}, {discipline["rated_at"]}'
    return (
        f'<b>{p["full_name"]}</b>\n'
        f'Специальность: {p["specialty"] or "не указана"}\n'
        f'Телефон: {p["phone"] or "не указан"}\n\n'
        f'Критерии: {stars}\n'
        f'Готов сотрудничать: {"да" if p["willing_to_work"] else "нет/не подтверждено"}\n'
        f'Есть инструмент: {"да" if p["has_tools"] else "нет/не указано"}\n'
        f'Есть автомобиль: {"да" if p["has_car"] else "нет/не указано"}\n'
        f'Дисциплина: {discipline_text}\n\n'
        f'Комментарий: {p["comment"] or "нет"}\n'
        f'ID: <code>{p["id"]}</code>'
    )

async def show_page(message: Message, page: int = 0, query: str | None = None, specialty: str | None = None):
    offset = page * PAGE_SIZE
    if query is not None:
        rows = search_performers(query, limit=PAGE_SIZE, offset=offset)
        total = count_performers(query=query)
        title = f'Результаты поиска: «{query}»'
    elif specialty is not None:
        rows = search_performers(specialty, limit=PAGE_SIZE, offset=offset, specialty_only=True)
        total = count_performers(query=specialty, specialty_only=True)
        title = f'Специальность: «{specialty}»'
    else:
        rows = list_performers(limit=PAGE_SIZE, offset=offset)
        total = count_performers()
        title = "Все исполнители"
    if not rows:
        await message.answer("Ничего не найдено.")
        return
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    text = f"<b>{title}</b>\nНайдено: {total}. Страница {page + 1}/{pages}\n\n"
    text += "\n\n".join(performer_card(p) for p in rows)
    if page + 1 < pages:
        text += f"\n\nЧтобы открыть следующую страницу, отправьте: <code>/page {page + 1}</code>"
    await message.answer(text, parse_mode="HTML")

async def main():
    if not TOKEN:
        raise RuntimeError("Укажите TELEGRAM_BOT_TOKEN в файле .env")
    init_db()
    # Опциональный однократный импорт из data/performers.csv
    csv_path = Path("data/performers.csv")
    if csv_path.exists() and count_performers() == 0:
        import_csv(str(csv_path))

    bot = Bot(TOKEN)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message):
        if not is_allowed(message.from_user.id):
            await message.answer(
                f"Доступ не настроен для вашего аккаунта.\nВаш Telegram ID: {message.from_user.id}\n"
                "Попросите администратора добавить ID в TELEGRAM_ALLOWED_USERS."
            )
            return
        await message.answer("Адресная книга исполнителей готова к работе.", reply_markup=MENU)

    @dp.message(Command("help"))
    @dp.message(F.text == "ℹ️ Помощь")
    async def help_handler(message: Message):
        if not is_allowed(message.from_user.id):
            return
        await message.answer(
            "Команды:\n"
            "• /search Иванов — поиск по ФИО, телефону и специальности\n"
            "• /specialty Электрик — поиск по специальности\n"
            "• /all — весь каталог\n"
            "• /page 1 — открыть страницу каталога (нумерация с 0)\n"
            "• /rate ID 1 — отметить дисциплину как хорошую\n"
            "• /rate ID 0 — отметить дисциплину как неудовлетворительную\n\n"
            "Оценка дисциплины сохраняет автора и дату. Команды изменения контактов добавим следующим этапом."
        )

    @dp.message(Command("search"))
    @dp.message(F.text == "🔎 Поиск")
    async def search_handler(message: Message):
        if not is_allowed(message.from_user.id):
            return
        query = message.text.partition(" ")[2].strip() if message.text else ""
        if not query:
            await message.answer("Введите запрос, например: /search Иванов или /search 999123")
            return
        await show_page(message, query=query)

    @dp.message(Command("specialty"))
    @dp.message(F.text == "🧰 По специальности")
    async def specialty_handler(message: Message):
        if not is_allowed(message.from_user.id):
            return
        query = message.text.partition(" ")[2].strip() if message.text else ""
        if not query:
            await message.answer("Введите специальность, например: /specialty Электрик")
            return
        await show_page(message, specialty=query)

    @dp.message(Command("all"))
    @dp.message(F.text == "📋 Все исполнители")
    async def all_handler(message: Message):
        if not is_allowed(message.from_user.id):
            return
        await show_page(message)

    @dp.message(Command("page"))
    async def page_handler(message: Message):
        if not is_allowed(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("Формат: /page 1")
            return
        await show_page(message, page=int(parts[1]))

    @dp.message(Command("rate"))
    async def rate_handler(message: Message):
        if not is_allowed(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in {"0", "1"}:
            await message.answer("Формат: /rate ID 1 (хорошая дисциплина) или /rate ID 0")
            return
        p = get_performer(int(parts[1]))
        if not p:
            await message.answer("Исполнитель с таким ID не найден.")
            return
        author = message.from_user.full_name or str(message.from_user.id)
        rated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        set_discipline_rating(p["id"], int(parts[2]), message.from_user.id, author, rated_at)
        await message.answer("Оценка дисциплины сохранена вместе с автором и датой.")

    @dp.message()
    async def fallback(message: Message):
        if not is_allowed(message.from_user.id):
            return
        if message.text:
            await show_page(message, query=message.text.strip())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
