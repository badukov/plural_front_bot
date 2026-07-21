import logging
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile


logger = logging.getLogger(__name__)


def member_photo(member: dict[str, Any]) -> str | FSInputFile | None:
    value = str(member.get("avatar_url") or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    path = Path(value)
    return FSInputFile(path) if path.is_file() else None


async def send_member_avatar(bot: Bot, chat_id: int, member: dict[str, Any]) -> bool:
    photo = member_photo(member)
    if photo is None:
        return False
    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=str(member.get("name") or "") or None,
        )
        return True
    except (TelegramBadRequest, OSError) as error:
        logger.warning("Member avatar could not be sent for %s: %s", member.get("id"), error)
        return False
