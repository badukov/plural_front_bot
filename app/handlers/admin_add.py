import json
import tempfile
from pathlib import Path

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.access import is_admin_callback, is_admin_message
from app.config import settings
from app.florality import import_florality_members, sync_florality_member
from app.formatters import format_member_brief, split_long_message
from app.i18n import is_button_text, lang_from_callback, lang_from_message, t
from app.keyboards import (
    add_category_keyboard,
    add_category_selected_keyboard,
    add_choice_keyboard,
    add_member_menu_keyboard,
    main_keyboard,
)
from app.repository import repo
from app.states import AddMemberState, DeleteMemberState


router = Router()


def _names_block(names: tuple[str, ...]) -> str:
    if not names:
        return "-"
    return "\n".join(f"- {name}" for name in names)


def _is_skip(text: str) -> bool:
    return text.strip().casefold() in {"-", "skip", "пропустить", "нет", "salta", "no"}


async def _send_year_choice(message_or_callback: Message | CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(message_or_callback) if isinstance(message_or_callback, CallbackQuery) else lang_from_message(message_or_callback)
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
    markup = add_choice_keyboard("add:year", groups, t("skip_year", lang), lang)
    text = t("choose_year", lang)
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer()
        if message_or_callback.message:
            await message_or_callback.message.edit_text(text, reply_markup=markup)
    else:
        await message_or_callback.answer(text, reply_markup=markup)


async def _send_role_choice(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
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
            t("choose_role", lang),
            reply_markup=add_choice_keyboard("add:role", groups, t("skip_role", lang), lang),
        )


async def _send_category_browser(
    callback: CallbackQuery,
    state: FSMContext,
    parent_id: str | None = None,
) -> None:
    lang = lang_from_callback(callback)
    await state.set_state(AddMemberState.choosing_categories)
    data = await state.get_data()
    selected = list(data.get("category_ids") or [])
    groups = await repo.list_child_groups(parent_id=parent_id, limit=1000)
    await state.update_data(category_parent_id=parent_id)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            t("choose_categories", lang),
            reply_markup=add_category_keyboard(
                groups=groups,
                selected_count=len(selected),
                parent_id=parent_id,
                lang=lang,
            ),
        )


async def _finish_member(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    data = await state.get_data()
    name = str(data.get("name") or "").strip()
    if not name:
        await state.clear()
        await callback.answer(t("name_lost", lang), show_alert=True)
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
    if settings.florality_create_missing_members_enabled:
        await sync_florality_member(member)
    await state.clear()
    await callback.answer(t("member_added_answer", lang))
    if callback.message:
        brief = await format_member_brief(member, lang)
        await callback.message.edit_text(t("member_added", lang, brief=brief))


@router.message(lambda message: is_button_text(message.text, "add_member"))
async def add_member_menu(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await message.answer(
            t("admin_only", lang),
            reply_markup=main_keyboard(False, lang),
        )
        return

    await state.clear()
    await message.answer(t("add_menu", lang), reply_markup=add_member_menu_keyboard(lang))


@router.callback_query(lambda callback: callback.data == "add:cancel")
async def add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    await state.clear()
    await callback.answer(t("cancelled_answer", lang))
    if callback.message:
        await callback.message.edit_text(t("cancelled", lang))


@router.callback_query(lambda callback: callback.data == "add:new")
async def add_new_member(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    await state.clear()
    await callback.answer(t("manual_add_disabled", lang), show_alert=True)
    if callback.message:
        await callback.message.edit_text(t("manual_add_disabled", lang), reply_markup=add_member_menu_keyboard(lang))


@router.callback_query(lambda callback: callback.data == "add:import_florality")
async def import_from_florality(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    if not settings.florality_api_token:
        await callback.answer(t("florality_not_configured", lang), show_alert=True)
        return

    await callback.answer()
    if callback.message:
        await callback.message.edit_text(t("florality_import_started", lang))

    result = await import_florality_members()
    text = t(
        "florality_import_done",
        lang,
        imported_front=_names_block(result.imported_front_names),
        changed=_names_block(result.changed_names),
        missing_local=_names_block(result.missing_local_names),
        missing_remote=_names_block(result.missing_remote_names),
        unchanged=result.unchanged,
        skipped=result.skipped,
        backup=Path(result.backup_path).name if result.backup_path else "-",
    )
    if callback.message:
        chunks = split_long_message(text)
        await callback.message.edit_text(
            chunks[0],
            reply_markup=add_member_menu_keyboard(lang) if len(chunks) == 1 else None,
        )
        for index, chunk in enumerate(chunks[1:], start=1):
            await callback.message.answer(
                chunk,
                reply_markup=add_member_menu_keyboard(lang) if index == len(chunks) - 1 else None,
            )


@router.callback_query(lambda callback: callback.data == "add:delete")
async def delete_member_start(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    await state.clear()
    await callback.answer(t("manual_delete_disabled", lang), show_alert=True)
    if callback.message:
        await callback.message.edit_text(t("manual_delete_disabled", lang), reply_markup=add_member_menu_keyboard(lang))


@router.message(DeleteMemberState.waiting_for_query)
async def delete_member_search(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await state.clear()
        return

    await state.clear()
    await message.answer(t("manual_delete_disabled", lang), reply_markup=add_member_menu_keyboard(lang))


@router.callback_query(lambda callback: callback.data and callback.data.startswith("del:ask:"))
async def delete_member_ask(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    await callback.answer(t("manual_delete_disabled", lang), show_alert=True)
    if callback.message:
        await callback.message.edit_text(t("manual_delete_disabled", lang), reply_markup=add_member_menu_keyboard(lang))


@router.callback_query(lambda callback: callback.data and callback.data.startswith("del:confirm:"))
async def delete_member_confirm(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    await callback.answer(t("manual_delete_disabled", lang), show_alert=True)
    if callback.message:
        await callback.message.edit_text(t("manual_delete_disabled", lang), reply_markup=add_member_menu_keyboard(lang))


@router.message(AddMemberState.waiting_for_name)
async def add_member_name(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await state.clear()
        return

    name = (message.text or "").strip()
    if not name or _is_skip(name):
        await message.answer(t("name_required", lang))
        return

    await state.update_data(name=name)
    await state.set_state(AddMemberState.waiting_for_pronouns)
    await message.answer(t("enter_pronouns", lang))


@router.message(AddMemberState.waiting_for_pronouns)
async def add_member_pronouns(message: Message, state: FSMContext) -> None:
    lang = lang_from_message(message)
    if not is_admin_message(message):
        await state.clear()
        return

    text = (message.text or "").strip()
    await state.update_data(pronouns="" if _is_skip(text) else text)
    await state.set_state(AddMemberState.waiting_for_description)
    await message.answer(t("enter_description", lang))


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
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    value = (callback.data or "").split(":", 2)[2]
    await state.update_data(year_group_id="" if value == "skip" else value)
    await _send_role_choice(callback, state)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:role:"))
async def add_member_role(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    value = (callback.data or "").split(":", 2)[2]
    await state.update_data(role_group_id="" if value == "skip" else value, category_ids=[])
    await _send_category_browser(callback, state)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:cat:"))
async def add_member_category_pick(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    group_id = (callback.data or "").split(":", 2)[2]
    group = await repo.get_group_by_id(group_id)
    if not group:
        await callback.answer(t("category_not_found", lang), show_alert=True)
        return

    data = await state.get_data()
    selected = set(data.get("category_ids") or [])
    path = await repo.get_group_path(group_id)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"{t('category_title', lang)}:\n{path}",
            reply_markup=add_category_selected_keyboard(group_id, group_id in selected, lang),
        )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:cattoggle:"))
async def add_member_category_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    group_id = (callback.data or "").split(":", 2)[2]
    data = await state.get_data()
    selected = set(data.get("category_ids") or [])
    if group_id in selected:
        selected.remove(group_id)
    else:
        selected.add(group_id)
    await state.update_data(category_ids=sorted(selected))
    await callback.answer(t("updated", lang))
    await _send_category_browser(callback, state, data.get("category_parent_id"))


@router.callback_query(lambda callback: callback.data and callback.data.startswith("add:catopen:"))
async def add_member_category_open(callback: CallbackQuery, state: FSMContext) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
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
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    if callback.data == "add:catskip":
        await state.update_data(category_ids=[])
    await _finish_member(callback, state)


@router.callback_query(lambda callback: callback.data == "add:export")
async def export_json(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
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

        await callback.answer(t("export_ready", lang))
        if callback.message:
            await callback.message.answer_document(
                FSInputFile(tmp_path, filename="plural_front_export.json"),
                caption=t("export_caption", lang),
            )
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
