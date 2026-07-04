from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import settings
from app.formatters import format_member_brief, split_long_message
from app.keyboards import (
    BTN_ADD_MEMBER,
    BTN_BLUR,
    BTN_DIRECTORY,
    BTN_FRONT,
    BTN_INFO,
    BTN_NOTIFICATIONS,
    BTN_REMOVE_FRONT,
    main_keyboard,
    search_results_keyboard,
)
from app.access import is_admin_message
from app.repository import repo


router = Router()

BUTTON_TEXTS = {
    BTN_ADD_MEMBER,
    BTN_BLUR,
    BTN_DIRECTORY,
    BTN_FRONT,
    BTN_INFO,
    BTN_NOTIFICATIONS,
    BTN_REMOVE_FRONT,
}


@router.message(lambda message: bool(message.text))
async def search_by_any_text(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state:
        return

    query = (message.text or "").strip()
    if not query or query.startswith("/") or query in BUTTON_TEXTS:
        return

    matches = await repo.search_members(query, limit=settings.search_limit)
    if not matches:
        await message.answer(
            "Ничего не найдено. Попробуйте другой кусок имени.",
            reply_markup=main_keyboard(is_admin_message(message)),
        )
        return

    blocks = [f"Найдено вариантов: {len(matches)}"]
    for member in matches:
        blocks.append(await format_member_brief(member))
    text = "\n\n—————\n\n".join(blocks)

    chunks = split_long_message(text)
    for chunk in chunks[:-1]:
        await message.answer(chunk)
    await message.answer(chunks[-1], reply_markup=search_results_keyboard(matches))
