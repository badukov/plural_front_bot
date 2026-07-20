from collections import Counter, defaultdict
from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.i18n import button_text, t
from app.repository import member_reference


BTN_FRONT = "Фронт"
BTN_REMOVE_FRONT = "Снять с фронта"
BTN_BLUR = "Блюр"
BTN_INFO = "Инфо о фронте"
BTN_DIRECTORY = "Справочник"
BTN_NOTIFICATIONS = "Оповещения"
BTN_HISTORY = "История"
BTN_STATISTICS = "Статистика"
BTN_ADD_MEMBER = "Добавить личность"


def main_keyboard(is_admin: bool, lang: str = "ru") -> ReplyKeyboardMarkup:
    if is_admin:
        keyboard = [
            [KeyboardButton(text=button_text("front", lang)), KeyboardButton(text=button_text("remove_front", lang))],
            [KeyboardButton(text=button_text("blur", lang)), KeyboardButton(text=button_text("info", lang))],
            [KeyboardButton(text=button_text("history", lang))],
            [KeyboardButton(text=button_text("directory", lang)), KeyboardButton(text=button_text("notifications", lang))],
            [KeyboardButton(text=button_text("add_member", lang))],
        ]
    else:
        keyboard = [
            [KeyboardButton(text=button_text("info", lang)), KeyboardButton(text=button_text("notifications", lang))],
            [KeyboardButton(text=button_text("history", lang)), KeyboardButton(text=button_text("directory", lang))],
        ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder=t("input_placeholder", lang),
    )


def history_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text("statistics", lang), callback_data="hist:stats")],
        ]
    )


def statistics_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text("history", lang), callback_data="hist:history")],
        ]
    )


def short_button_text(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def member_button_items(rows: list[dict[str, Any]], lang: str = "ru") -> list[tuple[str, str]]:
    name_keys = [str(row.get("name") or "").strip().casefold() for row in rows]
    counts = Counter(name_keys)
    seen: defaultdict[str, int] = defaultdict(int)
    buttons: list[tuple[str, str]] = []

    for row, key in zip(rows, name_keys, strict=False):
        name = str(row.get("name") or t("no_name", lang)).strip()
        label = name

        if counts[key] > 1:
            seen[key] += 1
            suffixes: list[str] = []
            pronouns = str(row.get("pronouns") or "").strip()
            if pronouns:
                suffixes.append(pronouns)
            if row.get("is_archived"):
                suffixes.append(t("archived_short", lang))
            suffixes.append(f"#{seen[key]}")
            label = f"{name} ({', '.join(suffixes)})"
        elif row.get("is_archived"):
            label = f"{name} ({t('archived_short', lang)})"

        buttons.append((str(row["id"]), short_button_text(label)))

    return buttons


def members_choice_keyboard(action: str, members: list[tuple[str, str]], lang: str = "ru") -> InlineKeyboardMarkup:
    # action: setfront | rmfront
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"{action}:{member_id}")]
        for member_id, name in members
    ]
    rows.append([InlineKeyboardButton(text=t("cancel", lang), callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_keyboard(members: list[dict[str, Any]], lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{t('details_prefix', lang)}: {name}", callback_data=f"dir:m:{member_reference(member_id)}")]
        for member_id, name in member_button_items(members, lang)
    ]
    rows.append([InlineKeyboardButton(text=t("to_directory", lang), callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_member_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("import_florality", lang), callback_data="add:import_florality")],
            [InlineKeyboardButton(text=t("download_florality_avatars", lang), callback_data="add:avatars_florality")],
            [InlineKeyboardButton(text=t("export_json", lang), callback_data="add:export")],
            [InlineKeyboardButton(text=t("cancel", lang), callback_data="add:cancel")],
        ]
    )


def add_choice_keyboard(prefix: str, groups: list[dict[str, Any]], skip_text: str, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=short_button_text(str(group.get("name") or t("unnamed_category", lang))),
                callback_data=f"{prefix}:{group['id']}",
            )
        ]
        for group in groups
    ]
    rows.append([InlineKeyboardButton(text=skip_text, callback_data=f"{prefix}:skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_category_keyboard(
    groups: list[dict[str, Any]],
    selected_count: int,
    parent_id: str | None = None,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=short_button_text(str(group.get("name") or t("unnamed_category", lang))),
                callback_data=f"add:cat:{group['id']}",
            )
        ]
        for group in groups
    ]
    if parent_id:
        rows.append([InlineKeyboardButton(text=t("up", lang), callback_data="add:catup")])
    rows.append([InlineKeyboardButton(text=t("done_count", lang, count=selected_count), callback_data="add:catdone")])
    rows.append([InlineKeyboardButton(text=t("skip_categories", lang), callback_data="add:catskip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_category_selected_keyboard(group_id: str, selected: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    text = t("remove_category", lang) if selected else t("add_category", lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=f"add:cattoggle:{group_id}")],
            [InlineKeyboardButton(text=t("open_children", lang), callback_data=f"add:catopen:{group_id}")],
            [InlineKeyboardButton(text=t("done", lang), callback_data="add:catdone")],
        ]
    )


def directory_home_keyboard(lang: str = "ru", is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t("search_by_name", lang), callback_data="dir:search")],
        [InlineKeyboardButton(text=t("categories", lang), callback_data="dir:cats:0")],
        [InlineKeyboardButton(text=t("all_members", lang), callback_data="dir:all:0")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text=button_text("add_member", lang), callback_data="add:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def directory_categories_keyboard(
    groups: list[dict[str, Any]],
    page: int,
    has_prev: bool,
    has_next: bool,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=short_button_text(str(group.get("name") or t("unnamed_category", lang))),
                callback_data=f"dir:cat:{group['id']}:0",
            )
        ]
        for group in groups
    ]
    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton(text=t("back", lang), callback_data=f"dir:cats:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text=t("next", lang), callback_data=f"dir:cats:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=t("to_directory", lang), callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def directory_category_keyboard(
    group_id: str,
    child_groups: list[dict[str, Any]],
    page: int,
    has_prev: bool,
    has_next: bool,
    members_count: int,
    parent_id: str | None,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    rows = []
    if members_count:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("members_here", lang, count=members_count),
                    callback_data=f"dir:list:{group_id}:0",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=short_button_text(str(group.get("name") or t("unnamed_category", lang))),
                    callback_data=f"dir:cat:{group['id']}:0",
                )
            ]
            for group in child_groups
        ]
    )
    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton(text=t("back", lang), callback_data=f"dir:cat:{group_id}:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text=t("next", lang), callback_data=f"dir:cat:{group_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    back_data = f"dir:cat:{parent_id}:0" if parent_id and parent_id != "root" else "dir:cats:0"
    rows.append([InlineKeyboardButton(text=t("up", lang), callback_data=back_data)])
    rows.append([InlineKeyboardButton(text=t("to_directory", lang), callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def directory_members_keyboard(
    members: list[dict[str, Any]],
    page: int,
    has_prev: bool,
    has_next: bool,
    page_callback_prefix: str,
    back_callback_data: str,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"dir:m:{member_reference(member_id)}")]
        for member_id, name in member_button_items(members, lang)
    ]

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton(text=t("back", lang), callback_data=f"{page_callback_prefix}:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text=t("next", lang), callback_data=f"{page_callback_prefix}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text=t("back_to_choice", lang), callback_data=back_callback_data)])
    rows.append([InlineKeyboardButton(text=t("to_directory", lang), callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def directory_member_keyboard(member_id: str, is_admin: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    reference = member_reference(member_id)
    if is_admin:
        rows.extend(
            [
                [InlineKeyboardButton(text=t("add_to_front", lang), callback_data=f"dir:addfront:{reference}")],
                [InlineKeyboardButton(text=t("replace_front", lang), callback_data=f"dir:replacefront:{reference}")],
            ]
        )
    rows.append([InlineKeyboardButton(text=t("to_directory", lang), callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def front_members_keyboard(members: list[tuple[str, str]], lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"rmfront:{member_id}")]
        for member_id, name in members
    ]
    rows.append([InlineKeyboardButton(text=t("cancel", lang), callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_results_keyboard(members: list[dict[str, Any]], lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"del:ask:{member_id}")]
        for member_id, name in member_button_items(members, lang)
    ]
    rows.append([InlineKeyboardButton(text=t("cancel", lang), callback_data="add:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(member_id: str, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("delete_confirm_button", lang), callback_data=f"del:confirm:{member_id}")],
            [InlineKeyboardButton(text=t("cancel", lang), callback_data="add:cancel")],
        ]
    )
