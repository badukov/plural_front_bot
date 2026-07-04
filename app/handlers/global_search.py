from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import settings
from app.formatters import format_member_brief, split_long_message
from app.access import is_admin_message
from app.i18n import all_button_texts, lang_from_message, t
from app.keyboards import main_keyboard, search_results_keyboard
from app.repository import repo


router = Router()

@router.message(lambda message: bool(message.text))
async def search_by_any_text(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    current_state = await state.get_state()
    if current_state:
        return

    query = (message.text or "").strip()
    if not query or query.startswith("/") or query in all_button_texts():
        return

    matches = await repo.search_members(query, limit=settings.search_limit)
    if not matches:
        await message.answer(
            t("nothing_found", lang),
            reply_markup=main_keyboard(is_admin_message(message), lang),
        )
        return

    blocks = [t("found_count", lang, count=len(matches))]
    for member in matches:
        blocks.append(await format_member_brief(member, lang))
    text = "\n\n—————\n\n".join(blocks)

    chunks = split_long_message(text)
    for chunk in chunks[:-1]:
        await message.answer(chunk)
    await message.answer(chunks[-1], reply_markup=search_results_keyboard(matches, lang))
