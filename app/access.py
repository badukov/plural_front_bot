from aiogram.types import Message, CallbackQuery

from app.config import settings


def is_admin_user_id(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_ids


def is_admin_message(message: Message) -> bool:
    return message.from_user is not None and is_admin_user_id(message.from_user.id)


def is_admin_callback(callback: CallbackQuery) -> bool:
    return callback.from_user is not None and is_admin_user_id(callback.from_user.id)
