from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.access import is_admin_message
from app.i18n import lang_from_message, t
from app.keyboards import main_keyboard
from app.repository import repo


router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    if message.from_user is None:
        return

    is_admin = is_admin_message(message)
    lang = lang_from_message(message)
    await repo.upsert_user(
        telegram_user_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=is_admin,
        language_code=message.from_user.language_code,
    )

    members_count = await repo.count_members()

    if is_admin:
        text = t("admin_start", lang, count=members_count)
    else:
        text = t("user_start", lang, count=members_count)

    await message.answer(text, reply_markup=main_keyboard(is_admin, lang))
