import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from app.formatters import split_long_message
from app.repository import repo


log = logging.getLogger(__name__)


async def broadcast(bot: Bot, text: str) -> None:
    users = await repo.get_subscribed_users()
    for user in users:
        chat_id = user["chat_id"]
        telegram_user_id = user["telegram_user_id"]
        try:
            for chunk in split_long_message(text):
                await bot.send_message(chat_id=chat_id, text=chunk)
        except TelegramForbiddenError:
            log.info("User %s blocked bot. Marking unsubscribed.", telegram_user_id)
            await repo.set_user_subscribed(telegram_user_id, False)
        except TelegramBadRequest as exc:
            log.warning("Telegram bad request for user %s: %s", telegram_user_id, exc)
        except Exception:
            log.exception("Failed to broadcast to user %s", telegram_user_id)
