from aiogram import Router
from aiogram.types import Message

from app.access import is_admin_message
from app.formatters import format_front_history, format_front_statistics, split_long_message
from app.i18n import is_button_text, lang_from_message, t
from app.keyboards import main_keyboard
from app.repository import repo


router = Router()


async def _answer_chunks(message: Message, text: str) -> None:
    chunks = split_long_message(text)
    for chunk in chunks:
        await message.answer(chunk)


@router.message(lambda message: is_button_text(message.text, "history"))
async def show_history(message: Message) -> None:
    lang = lang_from_message(message)
    rows = await repo.get_front_history(limit=20)
    await _answer_chunks(message, format_front_history(rows, lang))


@router.message(lambda message: is_button_text(message.text, "statistics"))
async def show_statistics(message: Message) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await message.answer(
            t("admin_only", lang),
            reply_markup=main_keyboard(False, lang),
        )
        return

    stats = await repo.get_front_statistics(days=30)
    await _answer_chunks(message, format_front_statistics(stats, lang))
