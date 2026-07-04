from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.access import is_admin_message
from app.keyboards import main_keyboard
from app.repository import repo


router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    if message.from_user is None:
        return

    is_admin = is_admin_message(message)
    await repo.upsert_user(
        telegram_user_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=is_admin,
    )

    members_count = await repo.count_members()

    if is_admin:
        text = (
            "Вы админ. Доступно управление фронтом.\n"
            f"В базе личностей: {members_count}."
        )
    else:
        text = (
            "Вам доступна кнопка «Инфо о фронте».\n"
            f"В базе личностей: {members_count}."
        )

    await message.answer(text, reply_markup=main_keyboard(is_admin))
