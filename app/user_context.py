from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.repository import repo


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
        if isinstance(event, Message):
            await remember_message_user_language(event)
        elif isinstance(event, CallbackQuery):
            await remember_callback_user_language(event)
        return await handler(event, data)
