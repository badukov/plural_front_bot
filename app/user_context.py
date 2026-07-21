from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.repository import repo
from app.i18n import reset_current_language, set_current_language


async def remember_message_user_language(message: Message) -> None:
    if message.from_user is None:
        return
    await repo.update_user_language(message.from_user.id, message.from_user.language_code)


async def remember_callback_user_language(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    await repo.update_user_language(callback.from_user.id, callback.from_user.language_code)


class UserLanguageMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id: int | None = None
        telegram_language: str | None = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            telegram_language = event.from_user.language_code if event.from_user else None
            await remember_message_user_language(event)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            telegram_language = event.from_user.language_code if event.from_user else None
            await remember_callback_user_language(event)

        stored_user = await repo.get_user(user_id) if user_id is not None else None
        override = str(stored_user.get("language_override") or "") if stored_user else ""
        token = set_current_language(override or telegram_language)
        try:
            return await handler(event, data)
        finally:
            reset_current_language(token)
