import json
import tempfile
from pathlib import Path

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.access import is_admin_callback, is_admin_message
from app.formatters import format_member_brief
from app.keyboards import (
    BTN_ADD_MEMBER,
    add_category_keyboard,
    add_category_selected_keyboard,
    add_choice_keyboard,
    add_member_menu_keyboard,
    main_keyboard,
)
from app.repository import repo
from app.states import AddMemberState


router = Router()


def _is_skip(text: str) -> bool:
    return text.strip().casefold() in {"-", "skip", "пропустить", "нет"}


async def _send_year_choice(message_or_callback: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddMemberState.choosing_year)
    await repo.ensure_future_year_groups()
    root = await repo.get_group_by_name("Years of birth")
    groups = await repo.list_child_groups(root["id"], limit=1000) if root else []

    def year_key(group: dict) -> tuple[int, str]:
        try:
            return (int(str(group.get("name") or "")), str(group.get("name") or ""))
        except ValueError:
            return (99999, str(group.get("name") or ""))

    groups = sorted(groups, key=year_key)
    markup = add_choice_keyboard("add:year", groups, "Пропустить год")
    text = "Выберите год рождения:"
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer()
        if message_or_callback.message:
            await message_or_callback.message.edit_text(text, reply_markup=markup)
    else:
        await message_or_callback.answer(text, reply_markup=markup)


async def _send_role_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddMemberState.choosing_role)
    root = await repo.get_group_by_name("Roles")
    groups = []
    if root:
        for group_id in (await repo.get_descendant_group_ids(root["id"]))[1:]:
            group = await repo.get_group_by_id(group_id)
            if not group:
                continue
            path = await repo.get_group_path(group_id)
            label = path.split(" / ", 1)[1] if " / " in path else str(group.get("name") or "")
            group = dict(group)
            group["name"] = label
            groups.append(group)
    groups = sorted(groups, key=lambda group: str(group.get("name") or "").casefold())
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Выберите роль:",
            reply_markup=add_choice_keyboard("add:role", groups, "Пропустить роль"),
        )


async def _send_category_browser(
    callback: CallbackQuery,
    state: FSMContext,
    parent_id: str | None = None,
) -> None:
    await state.set_state(AddMemberState.choosing_categories)
    data = await state.get_data()
    selected = list(data.get("category_ids") or [])
    groups = await repo.list_child_groups(parent_id=parent_id, limit=1000)
    await state.update_data(category_parent_id=parent_id)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Выберите дополнительные категории или нажмите «Готово».",
            reply_markup=add_category_keyboard(
                groups=groups,
                selected_count=len(selected),
                parent_id=parent_id,
            ),
        )


async def _finish_member(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    name = str(data.get("name") or "").strip()
    if not name:
        await state.clear()
        await callback.answer("Имя потерялось, начните заново", show_alert=True)
        return

    group_ids = []
    for key in ["year_group_id", "role_group_id"]:
        value = data.get(key)
        if value:
            group_ids.append(str(value))
    group_ids.extend(str(value) for value in data.get("category_ids") or [])

    member = await repo.create_member(
        name=name,
        pronouns=str(data.get("pronouns") or ""),
        description=str(data.get("description") or ""),
        group_ids=group_ids,
        created_by=callback.from_user.id if callback.from_user else None,
    )
    await state.clear()
    await callback.answer("Личность добавлена")
    if callback.message:
        brief = await format_member_brief(member)
        await callback.message.edit_text(f"Личность добавлена:\n\n{brief}")


@router.message(lambda message: message.text == BTN_ADD_MEMBER)
async def add_member_menu(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        await message.answer(
            "Управление фронтом доступно только админам.",
            reply_markup=main_keyboard(False),
        )
        return

    await state.clear()
    await message.answer("Меню добавления:", reply_markup=add_member_menu_keyboard())


@router.callback_query(lambda callback: callback.data == "add:cancel")
async def add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message:
        await callback.message.edit_text("Отменено.")


@router.callback_query(lambda callback: callback.data == "add:new")
async def add_new_member(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.clear()
    await state.set_state(AddMemberState.waiting_for_name)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Введите имя новой личности:")


@router.message(AddMemberState.waiting_for_name)
async def add_member_name(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        await state.clear()
        return

    name = (message.text or "").strip()
    if not name or _is_skip(name):
        await message.answer("Имя обязательно. Введите имя новой личности:")
        return

    await state.update_data(name=name)
    await state.set_state(AddMemberState.waiting_for_pronouns)
    await message.answer("Введите местоимения или «-», чтобы пропустить:")


@router.message(AddMemberState.waiting_for_pronouns)
async def add_member_pronouns(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        await state.clear()
        return

    text = (message.text or "").strip()
    await state.update_data(pronouns="" if _is_skip(text) else text)
    await state.set_state(AddMemberState.waiting_for_description)
    await message.answer("Введите описание или «-», чтобы пропустить:")


@router.message(AddMemberState.waiting_for_description)
async def add_member_description(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        await state.clear()
        return

    text = (message.text or "").strip()
    await state.update_data(description="" if _is_skip(text) else text)
    await _send_year_choice(message, state)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:year:"))
async def add_member_year(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    value = (callback.data or "").split(":", 2)[2]
    await state.update_data(year_group_id="" if value == "skip" else value)
    await _send_role_choice(callback, state)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:role:"))
async def add_member_role(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    value = (callback.data or "").split(":", 2)[2]
    await state.update_data(role_group_id="" if value == "skip" else value, category_ids=[])
    await _send_category_browser(callback, state)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:cat:"))
async def add_member_category_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    group_id = (callback.data or "").split(":", 2)[2]
    group = await repo.get_group_by_id(group_id)
    if not group:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    data = await state.get_data()
    selected = set(data.get("category_ids") or [])
    path = await repo.get_group_path(group_id)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"Категория:\n{path}",
            reply_markup=add_category_selected_keyboard(group_id, group_id in selected),
        )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:cattoggle:"))
async def add_member_category_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    group_id = (callback.data or "").split(":", 2)[2]
    data = await state.get_data()
    selected = set(data.get("category_ids") or [])
    if group_id in selected:
        selected.remove(group_id)
    else:
        selected.add(group_id)
    await state.update_data(category_ids=sorted(selected))
    await callback.answer("Обновлено")
    await _send_category_browser(callback, state, data.get("category_parent_id"))


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:catopen:"))
async def add_member_category_open(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    group_id = (callback.data or "").split(":", 2)[2]
    await _send_category_browser(callback, state, group_id)


@router.callback_query(lambda callback: callback.data == "add:catup")
async def add_member_category_up(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    parent_id = data.get("category_parent_id")
    parent = await repo.get_group_by_id(parent_id) if parent_id else None
    next_parent = parent.get("parent_id") if parent else None
    if next_parent == "root":
        next_parent = None
    await _send_category_browser(callback, state, next_parent)


@router.callback_query(lambda callback: callback.data in {"add:catdone", "add:catskip"})
async def add_member_categories_done(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    if callback.data == "add:catskip":
        await state.update_data(category_ids=[])
    await _finish_member(callback, state)


@router.callback_query(lambda callback: callback.data == "add:export")
async def export_json(callback: CallbackQuery) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await repo.export_simply_plural_data()
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".json",
            prefix="plural_front_export_",
            delete=False,
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name

        await callback.answer("Экспорт готов")
        if callback.message:
            await callback.message.answer_document(
                FSInputFile(tmp_path, filename="plural_front_export.json"),
                caption="Экспорт текущей базы.",
            )
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
