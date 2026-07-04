from aiogram import Router
from aiogram.types import Message

from app.access import is_admin_message
from app.formatters import format_front_info, split_long_message
from app.keyboards import BTN_INFO, main_keyboard
from app.repository import repo


router = Router()


@router.message(lambda message: message.text == BTN_INFO)
async def info_front(message: Message) -> None:
    front_members = await repo.get_current_front_members()
    text = await format_front_info(front_members)
    for chunk in split_long_message(text):
        await message.answer(chunk)
    await message.answer("Кнопки обновлены.", reply_markup=main_keyboard(is_admin_message(message)))
