from __future__ import annotations

import asyncio
import datetime
import logging

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.dispatcher.middlewares.base import BaseMiddleware

from minstock.ai import ask
from minstock.config import load_settings
from minstock.db import connect, init_db
from minstock.parsers import update_rates_periodically
from minstock.services import InventoryService


class AiQuery(StatesGroup):
    waiting = State()


class ReceiptFlow(StatesGroup):
    supplier = State()
    item_query = State()
    item = State()
    qty = State()
    price = State()
    currency = State()
    warehouse = State()
    comment = State()


class ConsumptionFlow(StatesGroup):
    item_query = State()
    item = State()
    qty = State()
    warehouse = State()
    comment = State()


settings = load_settings()
connection = connect(settings.database_path)
init_db(connection)
inventory = InventoryService(connection)
router = Router()
http_session: aiohttp.ClientSession | None = None


def is_allowed(user_id: int) -> bool:
    return not settings.admin_telegram_ids or user_id in settings.admin_telegram_ids


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and not is_allowed(user.id):
            if isinstance(event, Message):
                await event.answer("Доступ закрыт.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ закрыт.", show_alert=True)
            return None
        return await handler(event, data)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Приход", callback_data="receipt:start"),
                InlineKeyboardButton(text="➖ Расход", callback_data="consumption:start"),
            ],
            [
                InlineKeyboardButton(text="📊 Остатки", callback_data="stock"),
                InlineKeyboardButton(text="📋 Закупки", callback_data="purchases"),
            ],
            [
                InlineKeyboardButton(text="📜 История", callback_data="history:menu"),
                InlineKeyboardButton(text="❓ AI", callback_data="ai:start"),
            ],
            [
                InlineKeyboardButton(text="📎 Отчёт", callback_data="report"),
            ],
        ]
    )


def rows_keyboard(prefix: str, rows: list, label_fields: tuple[str, ...]) -> InlineKeyboardMarkup:
    keyboard = []
    for row in rows:
        label = " | ".join(str(row[field]) for field in label_fields)
        keyboard.append([InlineKeyboardButton(text=label[:60], callback_data=f"{prefix}:{row['id']}")])
    keyboard.append([InlineKeyboardButton(text="Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def format_qty(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def parse_positive_float(value: str) -> float | None:
    try:
        number = float(value.replace(",", ".").strip())
    except ValueError:
        return None
    return number if number > 0 else None


@router.message(Command("start"))
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("MiniStock: выберите действие.", reply_markup=main_menu())


@router.message(Command("id"))
async def show_id(message: Message) -> None:
    if message.from_user:
        await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.message(Command("help"))
async def help_message(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start - меню\n"
        "/id - узнать Telegram ID\n"
        "/add_supplier Название; контакт\n"
        "/add_item артикул; название; ед; min; срок_поставки_дней"
    )


@router.message(Command("add_supplier"))
async def add_supplier(message: Message) -> None:
    payload = (message.text or "").removeprefix("/add_supplier").strip()
    if not payload:
        await message.answer("Формат: <code>/add_supplier Название; контакт</code>")
        return
    name, _, contact = payload.partition(";")
    try:
        inventory.add_supplier(name, contact)
    except Exception as error:
        await message.answer(f"Не удалось добавить поставщика: {error}")
        return
    await message.answer("Поставщик добавлен.")


@router.message(Command("add_item"))
async def add_item(message: Message) -> None:
    payload = (message.text or "").removeprefix("/add_item").strip()
    parts = [part.strip() for part in payload.split(";")]
    if len(parts) != 5:
        await message.answer(
            "Формат: <code>/add_item артикул; название; ед; min; срок_поставки_дней</code>"
        )
        return
    article, name, unit, min_stock, lead_time_days = parts
    try:
        inventory.add_item(article, name, unit, float(min_stock.replace(",", ".")), int(lead_time_days))
    except Exception as error:
        await message.answer(f"Не удалось добавить товар: {error}")
        return
    await message.answer("Товар добавлен.")


@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Действие отменено.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "receipt:start")
async def receipt_start(callback: CallbackQuery, state: FSMContext) -> None:
    suppliers = inventory.list_suppliers()
    if not suppliers:
        await callback.message.edit_text(
            "Сначала добавьте поставщика командой:\n<code>/add_supplier Название; контакт</code>",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return
    await state.set_state(ReceiptFlow.supplier)
    await callback.message.edit_text("Выберите поставщика:", reply_markup=rows_keyboard("receipt:supplier", suppliers, ("name",)))
    await callback.answer()


@router.callback_query(ReceiptFlow.supplier, F.data.startswith("receipt:supplier:"))
async def receipt_supplier(callback: CallbackQuery, state: FSMContext) -> None:
    supplier_id = int(callback.data.rsplit(":", 1)[1])
    await state.update_data(supplier_id=supplier_id)
    await state.set_state(ReceiptFlow.item_query)
    await callback.message.edit_text("Введите артикул или часть названия товара:")
    await callback.answer()


@router.message(ReceiptFlow.item_query)
async def receipt_item_query(message: Message, state: FSMContext) -> None:
    rows = inventory.search_items(message.text or "")
    if not rows:
        await message.answer("Ничего не найдено. Повторите поиск или добавьте товар через /add_item.")
        return
    await state.set_state(ReceiptFlow.item)
    await message.answer("Выберите товар:", reply_markup=rows_keyboard("receipt:item", rows, ("article", "name")))


@router.callback_query(ReceiptFlow.item, F.data.startswith("receipt:item:"))
async def receipt_item(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(item_id=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ReceiptFlow.qty)
    await callback.message.edit_text("Введите количество:")
    await callback.answer()


@router.message(ReceiptFlow.qty)
async def receipt_qty(message: Message, state: FSMContext) -> None:
    qty = parse_positive_float(message.text or "")
    if qty is None:
        await message.answer("Введите положительное число.")
        return
    await state.update_data(qty=qty)
    await state.set_state(ReceiptFlow.price)
    await message.answer("Введите цену за единицу:")


@router.message(ReceiptFlow.price)
async def receipt_price(message: Message, state: FSMContext) -> None:
    price = parse_positive_float(message.text or "")
    if price is None:
        await message.answer("Введите положительное число.")
        return
    await state.update_data(price=price)
    await state.set_state(ReceiptFlow.currency)
    await message.answer("Выберите валюту:", reply_markup=rows_keyboard("receipt:currency", inventory.list_currencies(), ("code",)))


@router.callback_query(ReceiptFlow.currency, F.data.startswith("receipt:currency:"))
async def receipt_currency(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(currency_id=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ReceiptFlow.warehouse)
    await callback.message.edit_text("Выберите склад:", reply_markup=rows_keyboard("receipt:warehouse", inventory.list_warehouses(), ("name",)))
    await callback.answer()


@router.callback_query(ReceiptFlow.warehouse, F.data.startswith("receipt:warehouse:"))
async def receipt_warehouse(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(warehouse_id=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ReceiptFlow.comment)
    await callback.message.edit_text("Комментарий или номер документа. Если не нужно, отправьте '-'.")
    await callback.answer()


@router.message(ReceiptFlow.comment)
async def receipt_finish(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    comment = "" if (message.text or "").strip() == "-" else (message.text or "").strip()
    inventory.record_receipt(created_by=message.from_user.id, comment=comment, **data)
    await state.clear()
    await message.answer("Приход записан.", reply_markup=main_menu())


@router.callback_query(F.data == "consumption:start")
async def consumption_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ConsumptionFlow.item_query)
    await callback.message.edit_text("Введите артикул или часть названия товара:")
    await callback.answer()


@router.message(ConsumptionFlow.item_query)
async def consumption_item_query(message: Message, state: FSMContext) -> None:
    rows = inventory.search_items(message.text or "")
    if not rows:
        await message.answer("Ничего не найдено. Повторите поиск или добавьте товар через /add_item.")
        return
    await state.set_state(ConsumptionFlow.item)
    await message.answer("Выберите товар:", reply_markup=rows_keyboard("consumption:item", rows, ("article", "name")))


@router.callback_query(ConsumptionFlow.item, F.data.startswith("consumption:item:"))
async def consumption_item(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(item_id=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ConsumptionFlow.qty)
    await callback.message.edit_text("Введите количество:")
    await callback.answer()


@router.message(ConsumptionFlow.qty)
async def consumption_qty(message: Message, state: FSMContext) -> None:
    qty = parse_positive_float(message.text or "")
    if qty is None:
        await message.answer("Введите положительное число.")
        return
    await state.update_data(qty=qty)
    await state.set_state(ConsumptionFlow.warehouse)
    await message.answer("Выберите склад:", reply_markup=rows_keyboard("consumption:warehouse", inventory.list_warehouses(), ("name",)))


@router.callback_query(ConsumptionFlow.warehouse, F.data.startswith("consumption:warehouse:"))
async def consumption_warehouse(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(warehouse_id=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ConsumptionFlow.comment)
    await callback.message.edit_text("Введите номер заказа или комментарий. Если не нужно, отправьте '-'.")
    await callback.answer()


@router.message(ConsumptionFlow.comment)
async def consumption_finish(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    comment = "" if (message.text or "").strip() == "-" else (message.text or "").strip()
    current_qty = inventory.stock_for_item_warehouse(data["item_id"], data["warehouse_id"])
    if data["qty"] > current_qty:
        await message.answer(
            f"Недостаточно на складе. Сейчас есть {format_qty(current_qty)}, "
            f"списать пытаетесь {format_qty(data['qty'])}. Расход не записан."
        )
        return
    inventory.record_consumption(created_by=message.from_user.id, comment=comment, **data)
    await state.clear()
    await message.answer("Расход записан.", reply_markup=main_menu())


@router.callback_query(F.data == "stock")
async def stock(callback: CallbackQuery) -> None:
    rows = inventory.stock_rows()
    if not rows:
        text = "Номенклатура пустая. Добавьте товар через /add_item."
    else:
        lines = ["<b>Остатки</b>"]
        for row in rows[:30]:
            lines.append(
                f"{row['article']} {row['name']}: МСК {format_qty(row['msk_qty'])}, "
                f"ТВЕРЬ {format_qty(row['tver_qty'])}, всего {format_qty(row['total_qty'])} {row['unit']}"
            )
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "purchases")
async def purchases(callback: CallbackQuery) -> None:
    rows = inventory.purchase_rows()
    if not rows:
        text = "Закупка пока не требуется."
    else:
        lines = ["<b>К заказу</b>"]
        for row in rows[:30]:
            lines.append(f"{row['article']} {row['name']}: {format_qty(row['need_qty'])} {row['unit']}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "history:menu")
async def history_menu(callback: CallbackQuery) -> None:
    text = "Выберите период истории:"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="За 7 дней", callback_data="history:days:7")],
            [InlineKeyboardButton(text="За 30 дней", callback_data="history:days:30")],
            [InlineKeyboardButton(text="За 90 дней", callback_data="history:days:90")],
            [InlineKeyboardButton(text="За год", callback_data="history:days:365")],
            [InlineKeyboardButton(text="Отмена", callback_data="cancel")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("history:days:"))
async def history_show(callback: CallbackQuery) -> None:
    days = int(callback.data.rsplit(":", 1)[1])
    rows = inventory.history(days=days)
    if not rows:
        text = f"За последние {days} дн. движений нет."
    else:
        lines = [f"<b>История за {days} дн.</b>"]
        for row in rows[:30]:
            sign = "➕" if row["type"] == "receipt" else "➖"
            lines.append(
                f"{row['created_at'][:10]} {sign} {row['article']} "
                f"{format_qty(row['qty'])} {row['unit']} — {row['warehouse']}"
            )
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "ai:start")
async def ai_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not settings.gemini_api_key:
        await callback.message.edit_text(
            "AI не настроен. Добавьте <code>GEMINI_API_KEY</code> в .env\n"
            "Получить ключ: https://aistudio.google.com/apikey",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return
    await state.set_state(AiQuery.waiting)
    await callback.message.edit_text(
        "Задайте вопрос на русском:\n"
        "Например: <i>сколько ножей 2мм осталось на твери?</i>\n"
        "Или: <i>что и когда покупали у Иванова в этом месяце?</i>"
    )
    await callback.answer()


@router.message(AiQuery.waiting)
async def ai_query(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    await state.clear()
    msg = await message.answer("⏳ Думаю...")
    result = await ask(
        question=message.text.strip(),
        db_conn=connection,
        db_path=settings.database_path,
        gemini_api_key=settings.gemini_api_key,
        http_session=http_session,
    )
    await msg.edit_text(result, reply_markup=main_menu())


@router.callback_query(F.data == "report")
async def report(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Формирую отчёт...", reply_markup=main_menu())
    await callback.answer()
    try:
        excel_data = inventory.generate_excel()
        input_file = BufferedInputFile(
            file=excel_data,
            filename=f"minstock_{datetime.date.today().isoformat()}.xlsx",
        )
        await callback.message.answer_document(input_file, caption="Отчёт MiniStock")
    except Exception:
        await callback.message.answer("Ошибка при формировании отчёта. Установлен ли openpyxl?")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    session = AiohttpSession(proxy=settings.telegram_proxy_url) if settings.telegram_proxy_url else None
    bot = Bot(
        token=settings.telegram_bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.message.middleware(AccessMiddleware())
    dispatcher.callback_query.middleware(AccessMiddleware())
    dispatcher.include_router(router)

    global http_session
    async with aiohttp.ClientSession() as http_session:
        asyncio.create_task(update_rates_periodically(connection, http_session))
        await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
