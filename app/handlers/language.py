from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.access import is_admin_message
from app.i18n import SUPPORTED_LANGS, normalize_lang, t
from app.keyboards import main_keyboard
from app.repository import repo


router = Router()


@router.message(Command("language", "lang"))
async def change_language(message: Message) -> None:
    if message.from_user is None:
        return

    parts = (message.text or "").split(maxsplit=1)
    argument = parts[1].strip().casefold() if len(parts) > 1 else ""
    if not argument:
        user = await repo.get_user(message.from_user.id)
        active = str((user or {}).get("language_override") or "auto")
        lang = normalize_lang(active if active != "auto" else message.from_user.language_code)
        await message.answer(t("language_command_usage", lang, current=active))
        return

    if argument not in SUPPORTED_LANGS | {"auto"}:
        user = await repo.get_user(message.from_user.id)
        current = str((user or {}).get("language_override") or "auto")
        lang = normalize_lang(current if current != "auto" else message.from_user.language_code)
        await message.answer(t("language_command_usage", lang, current=current))
        return

    await repo.upsert_user(
        telegram_user_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=is_admin_message(message),
        language_code=message.from_user.language_code,
    )
    override = None if argument == "auto" else argument
    await repo.update_user_language_override(message.from_user.id, override)
    active_lang = normalize_lang(message.from_user.language_code if override is None else override)
    await message.answer(
        t("language_changed", active_lang, language=argument),
        reply_markup=main_keyboard(is_admin_message(message), active_lang),
    )
