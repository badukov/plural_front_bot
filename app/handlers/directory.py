from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.config import settings
from app.formatters import format_member_info, split_long_message
from app.keyboards import (
    BTN_DIRECTORY,
    directory_categories_keyboard,
    directory_category_keyboard,
    directory_home_keyboard,
    directory_members_keyboard,
)
from app.repository import repo
from app.states import DirectorySearchState


router = Router()

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


@router.message(lambda message: message.text == BTN_DIRECTORY)
async def open_directory(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Справочник: выберите способ просмотра.",
        reply_markup=directory_home_keyboard(),
    )


@router.callback_query(lambda callback: callback.data == "dir:home")
async def directory_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _edit_or_answer(
        callback,
        "Справочник: выберите способ просмотра.",
        reply_markup=directory_home_keyboard(),
    )


@router.callback_query(lambda callback: callback.data == "dir:search")
async def directory_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DirectorySearchState.waiting_for_query)
    await callback.answer()
    await _edit_or_answer(callback, "Введите имя или часть имени личности.")


@router.message(DirectorySearchState.waiting_for_query)
async def directory_search(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if query == BTN_DIRECTORY:
        await open_directory(message, state)
        return
    if not query:
        await message.answer("Введите хотя бы часть имени.")
        return

    matches = await repo.search_members(query, limit=settings.search_limit)
    if not matches:
        await message.answer("Ничего не найдено. Попробуйте другой кусок имени.")
        return

    await state.clear()
    await message.answer(
        f"Найдено вариантов: {len(matches)}",
        reply_markup=directory_members_keyboard(
            members=matches,
            page=0,
            has_prev=False,
            has_next=False,
            page_callback_prefix="dir:search",
            back_callback_data="dir:home",
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:cats:"))
async def directory_categories(callback: CallbackQuery) -> None:
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
    text = f"Категории\nПоказано {min(offset + 1, total)}-{min(offset + len(groups), total)} из {total}"
    await _edit_or_answer(
        callback,
        text,
        reply_markup=directory_categories_keyboard(
            groups=groups,
            page=page,
            has_prev=page > 0,
            has_next=offset + CATEGORY_PAGE_SIZE < total,
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:cat:"))
async def directory_category(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    group_id = parts[2]
    page = _safe_page(parts[3])
    group = await repo.get_group_by_id(group_id)
    if not group:
        await callback.answer("Категория не найдена", show_alert=True)
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
        f"Категория:\n{path}\n\n"
        f"Вложенных категорий: {total_children}\n"
        f"Личностей здесь и ниже: {members_count}"
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
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:all:"))
async def directory_all_members(callback: CallbackQuery) -> None:
    page = _safe_page(callback.data.rsplit(":", 1)[-1] if callback.data else "0")
    total = await repo.count_all_members()
    offset = page * MEMBER_PAGE_SIZE
    members = await repo.get_all_members_page(limit=MEMBER_PAGE_SIZE, offset=offset)

    if not members and page > 0:
        page = 0
        offset = 0
        members = await repo.get_all_members_page(limit=MEMBER_PAGE_SIZE, offset=offset)

    await callback.answer()
    text = f"Все личности\nПоказано {min(offset + 1, total)}-{min(offset + len(members), total)} из {total}"
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
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:list:"))
async def directory_group_members(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    group_id = parts[2]
    page = _safe_page(parts[3])
    group = await repo.get_group_by_id(group_id)
    if not group:
        await callback.answer("Категория не найдена", show_alert=True)
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
    text = f"{path}\nПоказано {min(offset + 1, total)}-{min(offset + len(members), total)} из {total}"

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
        ),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("dir:m:"))
async def directory_member_info(callback: CallbackQuery) -> None:
    member_id = (callback.data or "")[len("dir:m:") :]
    member = await repo.get_member_by_id(member_id)
    if not member:
        await callback.answer("Личность не найдена", show_alert=True)
        return

    await callback.answer()
    text = await format_member_info(member)
    await _show_chunks(callback, text, reply_markup=directory_home_keyboard())
