from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.access import is_admin_message
from app.broadcast import broadcast_by_language
from app.formatters import format_front_notification
from app.i18n import is_button_text, lang_from_message, t
from app.keyboards import (
    directory_home_keyboard,
    front_members_keyboard,
    main_keyboard,
    member_button_items,
    members_choice_keyboard,
)
from app.repository import repo
from app.states import FrontSearchState


router = Router()


@router.message(lambda message: is_button_text(message.text, "front"))
async def start_front_search(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await message.answer(
            t("admin_only", lang),
            reply_markup=main_keyboard(False, lang),
        )
        return

    await state.set_state(FrontSearchState.waiting_for_query)
    await message.answer(t("enter_name", lang))


@router.message(FrontSearchState.waiting_for_query)
async def process_front_search(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await state.clear()
        await message.answer(
            t("admin_only", lang),
            reply_markup=main_keyboard(False, lang),
        )
        return

    query = (message.text or "").strip()
    if is_button_text(query, "directory"):
        await state.clear()
        await message.answer(
            t("directory_home", lang),
            reply_markup=directory_home_keyboard(lang),
        )
        return

    if not query:
        await message.answer(t("enter_some_name", lang))
        return

    matches = await repo.search_members(query)
    if not matches:
        await message.answer(t("nothing_found", lang))
        return

    await state.clear()
    await message.answer(
        t("choose_front", lang),
        reply_markup=members_choice_keyboard("setfront", member_button_items(matches, lang), lang),
    )


@router.message(lambda message: is_button_text(message.text, "remove_front"))
async def remove_front_start(message: Message) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await message.answer(
            t("admin_only", lang),
            reply_markup=main_keyboard(False, lang),
        )
        return

    front_members = await repo.get_current_front_members()
    if not front_members:
        await message.answer(t("no_front", lang))
        return

    await message.answer(
        t("who_remove", lang),
        reply_markup=front_members_keyboard(member_button_items(front_members, lang), lang),
    )


@router.message(lambda message: is_button_text(message.text, "blur"))
async def set_blur(message: Message) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await message.answer(
            t("admin_only", lang),
            reply_markup=main_keyboard(False, lang),
        )
        return

    await repo.clear_front(created_by=message.from_user.id if message.from_user else None)
    await broadcast_by_language(
        message.bot,
        lambda user_lang: format_front_notification(t("front_cleared_event", user_lang), [], user_lang),
    )
    await message.answer(t("front_cleared_status", lang), reply_markup=main_keyboard(True, lang))
