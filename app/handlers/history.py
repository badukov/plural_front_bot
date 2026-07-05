from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.formatters import format_front_history, format_front_statistics, split_long_message
from app.i18n import is_button_text, lang_from_callback, lang_from_message
from app.keyboards import history_keyboard, statistics_keyboard
from app.repository import repo


router = Router()


async def _answer_chunks(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    chunks = split_long_message(text)
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        await message.answer(chunk, parse_mode="HTML", reply_markup=markup)


@router.message(lambda message: is_button_text(message.text, "history"))
async def show_history(message: Message) -> None:
    lang = lang_from_message(message)
    rows = await repo.get_front_history(limit=20)
    await _answer_chunks(message, format_front_history(rows, lang), history_keyboard(lang))


@router.message(lambda message: is_button_text(message.text, "statistics"))
async def show_statistics(message: Message) -> None:
    lang = lang_from_message(message)
    stats = await repo.get_front_statistics(days=30)
    await _answer_chunks(message, format_front_statistics(stats, lang), statistics_keyboard(lang))


@router.callback_query(lambda callback: callback.data == "hist:stats")
async def show_statistics_callback(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    await callback.answer()
    if not callback.message:
        return

    stats = await repo.get_front_statistics(days=30)
    await _answer_chunks(callback.message, format_front_statistics(stats, lang), statistics_keyboard(lang))


@router.callback_query(lambda callback: callback.data == "hist:history")
async def show_history_callback(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    await callback.answer()
    if not callback.message:
        return

    rows = await repo.get_front_history(limit=20)
    await _answer_chunks(callback.message, format_front_history(rows, lang), history_keyboard(lang))
