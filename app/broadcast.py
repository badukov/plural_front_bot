import logging
import inspect
from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from app.formatters import split_long_message
from app.i18n import normalize_lang
from app.media import send_member_avatar
from app.repository import repo


log = logging.getLogger(__name__)


async def broadcast(bot: Bot, text: str) -> None:
    await broadcast_by_language(bot, lambda _lang: text)


async def broadcast_by_language(
    bot: Bot,
    text_builder: Callable[[str], str | Awaitable[str]],
    photo_members: list[dict] | None = None,
) -> None:
    users = await repo.get_subscribed_users()
    for user in users:
        chat_id = user["chat_id"]
        telegram_user_id = user["telegram_user_id"]
        lang = normalize_lang(user.get("language_override") or user.get("language_code"))
        maybe_text = text_builder(lang)
        text = await maybe_text if inspect.isawaitable(maybe_text) else maybe_text
        try:
            sent_member_ids: set[str] = set()
            for member in photo_members or []:
                member_id = str(member.get("id") or member.get("name") or "")
                if not member_id or member_id in sent_member_ids:
                    continue
                sent_member_ids.add(member_id)
                await send_member_avatar(bot, chat_id, member)
            for chunk in split_long_message(text):
                await bot.send_message(chat_id=chat_id, text=chunk)
        except TelegramForbiddenError:
            log.info("User %s blocked bot. Marking unsubscribed.", telegram_user_id)
            await repo.set_user_subscribed(telegram_user_id, False)
        except TelegramBadRequest as exc:
            log.warning("Telegram bad request for user %s: %s", telegram_user_id, exc)
        except Exception:
            log.exception("Failed to broadcast to user %s", telegram_user_id)
