from aiogram import Router
from aiogram.types import Message

from app.access import is_admin_message
from app.i18n import is_button_text, lang_from_message, t
from app.formatters import format_front_info, split_long_message
from app.keyboards import main_keyboard
from app.repository import repo


router = Router()


@router.message(lambda message: is_button_text(message.text, "info"))
async def info_front(message: Message) -> None:
    lang = lang_from_message(message)
    front_members = await repo.get_current_front_members()
    text = await format_front_info(front_members, lang)
    for chunk in split_long_message(text):
        await message.answer(chunk)
    await message.answer(t("buttons_updated", lang), reply_markup=main_keyboard(is_admin_message(message), lang))
