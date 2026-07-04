from aiogram import Router
from aiogram.types import Message

from app.access import is_admin_message
from app.keyboards import BTN_NOTIFICATIONS, main_keyboard
from app.repository import repo


router = Router()


@router.message(lambda message: message.text == BTN_NOTIFICATIONS)
async def toggle_notifications(message: Message) -> None:
    if message.from_user is None:
        return

    user = await repo.get_user(message.from_user.id)
    if user is None:
        await repo.upsert_user(
            telegram_user_id=message.from_user.id,
            chat_id=message.chat.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            is_admin=is_admin_message(message),
        )

    subscribed = await repo.toggle_user_subscribed(message.from_user.id)
    text = (
        "Оповещения о смене фронта включены."
        if subscribed
        else "Оповещения о смене фронта выключены."
    )
    await message.answer(text, reply_markup=main_keyboard(is_admin_message(message)))
