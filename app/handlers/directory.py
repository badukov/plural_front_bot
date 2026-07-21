import logging
from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

from app.access import is_admin_callback, is_admin_message
from app.broadcast import broadcast_by_language
from app.config import settings
from app.florality import sync_florality_front
from app.formatters import current_status_text, format_front_notification, format_member_info, split_long_message
from app.i18n import is_button_text, lang_from_callback, lang_from_message, t
from app.keyboards import (
    directory_categories_keyboard,
    directory_category_keyboard,
    directory_home_keyboard,
    directory_member_keyboard,
    directory_members_keyboard,
)
from app.repository import repo
from app.states import DirectorySearchState


router = Router()
logger = logging.getLogger(__name__)

CATEGORY_PAGE_SIZE = 8
MEMBER_PAGE_SIZE = 8


def _safe_page(value: str | None) -> int:
    try:
        page = int(value or "0")
    except ValueError:
        return 0
    return max(page, 0)


async def _edit_or_answer(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if callback.message:
        await callback.message.edit_text(text, reply_markup=reply_markup)


async def _show_chunks(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    chunks = split_long_message(text)
    if not callback.message:
        return

    if len(chunks) == 1:
        await callback.message.edit_text(chunks[0], reply_markup=reply_markup)
        return

    await callback.message.edit_text(chunks[0])
    for index, chunk in enumerate(chunks[1:], start=1):
        await callback.message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


@router.message(lambda message: is_button_text(message.text, "directory"))
async def open_directory(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    await state.clear()
    await message.answer(
        t("directory_home", lang),
        reply_markup=directory_home_keyboard(lang, is_admin_message(message)),
    )


@router.callback_query(lambda callback: callback.data == "dir:home")
async def directory_home(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    await state.clear()
    await callback.answer()
    await _edit_or_answer(
        callback,
        t("directory_home", lang),
        reply_markup=directory_home_keyboard(lang, is_admin_callback(callback)),
    )


@router.callback_query(lambda callback: callback.data == "dir:search")
async def directory_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    await state.set_state(DirectorySearchState.waiting_for_query)
    await callback.answer()
    await _edit_or_answer(callback, t("enter_name", lang))


@router.message(DirectorySearchState.waiting_for_query)
async def directory_search(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    query = (message.text or "").strip()
    if is_button_text(query, "directory"):
        await open_directory(message, state)
        return
    if not query:
        await message.answer(t("enter_some_name", lang))
        return

    matches = await repo.search_members(query, limit=settings.search_limit)
    if not matches:
        await message.answer(t("nothing_found", lang))
        return

    await state.clear()
    await message.answer(
        t("found_count", lang, count=len(matches)),
        reply_markup=directory_members_keyboard(
            members=matches,
            page=0,
            has_prev=False,
            has_next=False,
            page_callback_prefix="dir:search",
            back_callback_data="dir:home",
            lang=lang,
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:cats:"))
async def directory_categories(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    page = _safe_page(callback.data.rsplit(":", 1)[-1] if callback.data else "0")
    total = await repo.count_child_groups(parent_id=None)
    offset = page * CATEGORY_PAGE_SIZE
    groups = await repo.list_child_groups(
        parent_id=None,
        limit=CATEGORY_PAGE_SIZE,
        offset=offset,
    )

    if not groups and page > 0:
        page = 0
        offset = 0
        groups = await repo.list_child_groups(
            parent_id=None,
            limit=CATEGORY_PAGE_SIZE,
            offset=offset,
        )

    await callback.answer()
    text = (
        f"{t('categories', lang)}\n"
        f"{t('shown_range', lang, start=min(offset + 1, total), end=min(offset + len(groups), total), total=total)}"
    )
    await _edit_or_answer(
        callback,
        text,
        reply_markup=directory_categories_keyboard(
            groups=groups,
            page=page,
            has_prev=page > 0,
            has_next=offset + CATEGORY_PAGE_SIZE < total,
            lang=lang,
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:cat:"))
async def directory_category(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer(t("category_not_found", lang), show_alert=True)
        return

    group_id = parts[2]
    page = _safe_page(parts[3])
    group = await repo.get_group_by_id(group_id)
    if not group:
        await callback.answer(t("category_not_found", lang), show_alert=True)
        return

    total_children = await repo.count_child_groups(parent_id=group_id)
    offset = page * CATEGORY_PAGE_SIZE
    child_groups = await repo.list_child_groups(
        parent_id=group_id,
        limit=CATEGORY_PAGE_SIZE,
        offset=offset,
    )
    if not child_groups and page > 0:
        page = 0
        offset = 0
        child_groups = await repo.list_child_groups(
            parent_id=group_id,
            limit=CATEGORY_PAGE_SIZE,
            offset=offset,
        )

    path = await repo.get_group_path(group_id)
    members_count = await repo.count_members_for_group_tree(group_id)
    text = (
        f"{t('category_title', lang)}:\n{path}\n\n"
        f"{t('child_categories', lang, count=total_children)}\n"
        f"{t('members_here', lang, count=members_count)}"
    )

    await callback.answer()
    await _edit_or_answer(
        callback,
        text,
        reply_markup=directory_category_keyboard(
            group_id=group_id,
            child_groups=child_groups,
            page=page,
            has_prev=page > 0,
            has_next=offset + CATEGORY_PAGE_SIZE < total_children,
            members_count=members_count,
            parent_id=group.get("parent_id"),
            lang=lang,
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:all:"))
async def directory_all_members(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    page = _safe_page(callback.data.rsplit(":", 1)[-1] if callback.data else "0")
    total = await repo.count_all_members()
    offset = page * MEMBER_PAGE_SIZE
    members = await repo.get_all_members_page(limit=MEMBER_PAGE_SIZE, offset=offset)

    if not members and page > 0:
        page = 0
        offset = 0
        members = await repo.get_all_members_page(limit=MEMBER_PAGE_SIZE, offset=offset)

    await callback.answer()
    text = (
        f"{t('all_members', lang)}\n"
        f"{t('shown_range', lang, start=min(offset + 1, total), end=min(offset + len(members), total), total=total)}"
    )
    await _edit_or_answer(
        callback,
        text,
        reply_markup=directory_members_keyboard(
            members=members,
            page=page,
            has_prev=page > 0,
            has_next=offset + MEMBER_PAGE_SIZE < total,
            page_callback_prefix="dir:all",
            back_callback_data="dir:home",
            lang=lang,
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:list:"))
async def directory_group_members(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer(t("category_not_found", lang), show_alert=True)
        return

    group_id = parts[2]
    page = _safe_page(parts[3])
    group = await repo.get_group_by_id(group_id)
    if not group:
        await callback.answer(t("category_not_found", lang), show_alert=True)
        return

    total = await repo.count_members_for_group_tree(group_id)
    offset = page * MEMBER_PAGE_SIZE
    members = await repo.get_members_for_group_tree(
        group_id=group_id,
        limit=MEMBER_PAGE_SIZE,
        offset=offset,
    )
    if not members and page > 0:
        page = 0
        offset = 0
        members = await repo.get_members_for_group_tree(
            group_id=group_id,
            limit=MEMBER_PAGE_SIZE,
            offset=offset,
        )

    path = await repo.get_group_path(group_id)
    text = f"{path}\n{t('shown_range', lang, start=min(offset + 1, total), end=min(offset + len(members), total), total=total)}"

    await callback.answer()
    await _edit_or_answer(
        callback,
        text,
        reply_markup=directory_members_keyboard(
            members=members,
            page=page,
            has_prev=page > 0,
            has_next=offset + MEMBER_PAGE_SIZE < total,
            page_callback_prefix=f"dir:list:{group_id}",
            back_callback_data=f"dir:cat:{group_id}:0",
            lang=lang,
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:m:"))
async def directory_member_info(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    reference = (callback.data or "")[len("dir:m:") :]
    member = await repo.get_member_by_reference(reference)
    if not member:
        await callback.answer(t("member_not_found", lang), show_alert=True)
        return
    member_id = str(member["id"])

    await callback.answer()
    avatar_value = str(member.get("avatar_url") or "").strip()
    if callback.message and avatar_value:
        photo: str | FSInputFile | None = None
        if avatar_value.startswith(("http://", "https://")):
            photo = avatar_value
        else:
            avatar_path = Path(avatar_value)
            if avatar_path.is_file():
                photo = FSInputFile(avatar_path)
        if photo:
            try:
                await callback.message.answer_photo(photo=photo, caption=str(member.get("name") or ""))
            except (TelegramAPIError, OSError) as error:
                logger.warning("Member avatar could not be sent for %s: %s", member_id, error)
    text = await format_member_info(member, lang)
    await _show_chunks(
        callback,
        text,
        reply_markup=directory_member_keyboard(member_id, is_admin_callback(callback), lang),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:addfront:"))
async def directory_add_to_front(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    reference = (callback.data or "")[len("dir:addfront:") :]
    member = await repo.get_member_by_reference(reference)
    if not member:
        await callback.answer(t("member_not_found", lang), show_alert=True)
        return
    member_id = str(member["id"])

    added = await repo.add_to_front(member_id, callback.from_user.id if callback.from_user else None)
    front_members = await repo.get_current_front_members()
    status = current_status_text(front_members, lang)
    if added:
        await repo.record_current_front_history("front_added", callback.from_user.id if callback.from_user else None)
        await sync_florality_front(front_members)
        await broadcast_by_language(
            callback.bot,
            lambda user_lang: format_front_notification(
                t("front_added_event", user_lang, name=member["name"]),
                front_members,
                user_lang,
            ),
            photo_members=[member],
        )
        text = t("front_added", lang, name=member["name"], status=status)
    else:
        text = t("already_front", lang, name=member["name"], status=status)

    await callback.answer(t("ready", lang))
    if callback.message:
        await callback.message.answer(text)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:replacefront:"))
async def directory_replace_front(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    reference = (callback.data or "")[len("dir:replacefront:") :]
    member = await repo.get_member_by_reference(reference)
    if not member:
        await callback.answer(t("member_not_found", lang), show_alert=True)
        return
    member_id = str(member["id"])

    changed = await repo.replace_front_members(
        [member_id],
        created_by=callback.from_user.id if callback.from_user else None,
        event_type="front_replaced",
        details={"source": "directory"},
    )
    front_members = await repo.get_current_front_members()
    status = current_status_text(front_members, lang)
    if changed:
        await repo.record_current_front_history("front_replaced", callback.from_user.id if callback.from_user else None)
        await sync_florality_front(front_members)
        await broadcast_by_language(
            callback.bot,
            lambda user_lang: format_front_notification(
                t("front_replaced_event", user_lang, name=member["name"]),
                front_members,
                user_lang,
            ),
            photo_members=[member],
        )

    await callback.answer(t("ready", lang))
    if callback.message:
        text = (
            t("front_replaced", lang, name=member["name"], status=status)
            if changed
            else t("already_front", lang, name=member["name"], status=status)
        )
        await callback.message.answer(text)
