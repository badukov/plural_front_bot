from collections import Counter, defaultdict
from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


BTN_FRONT = "Фронт"
BTN_REMOVE_FRONT = "Снять с фронта"
BTN_BLUR = "Блюр"
BTN_INFO = "Инфо о фронте"
BTN_DIRECTORY = "Справочник"
BTN_NOTIFICATIONS = "Оповещения"
BTN_ADD_MEMBER = "Добавить личность"


def main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    if is_admin:
        keyboard = [
            [KeyboardButton(text=BTN_FRONT), KeyboardButton(text=BTN_REMOVE_FRONT)],
            [KeyboardButton(text=BTN_BLUR), KeyboardButton(text=BTN_INFO)],
            [KeyboardButton(text=BTN_DIRECTORY), KeyboardButton(text=BTN_NOTIFICATIONS)],
            [KeyboardButton(text=BTN_ADD_MEMBER)],
        ]
    else:
        keyboard = [
            [KeyboardButton(text=BTN_INFO), KeyboardButton(text=BTN_DIRECTORY)],
            [KeyboardButton(text=BTN_NOTIFICATIONS)],
        ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def short_button_text(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def member_button_items(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    name_keys = [str(row.get("name") or "").strip().casefold() for row in rows]
    counts = Counter(name_keys)
    seen: defaultdict[str, int] = defaultdict(int)
    buttons: list[tuple[str, str]] = []

    for row, key in zip(rows, name_keys, strict=False):
        name = str(row.get("name") or "Без имени").strip()
        label = name

        if counts[key] > 1:
            seen[key] += 1
            suffixes: list[str] = []
            pronouns = str(row.get("pronouns") or "").strip()
            if pronouns:
                suffixes.append(pronouns)
            if row.get("is_archived"):
                suffixes.append("архив")
            suffixes.append(f"#{seen[key]}")
            label = f"{name} ({', '.join(suffixes)})"
        elif row.get("is_archived"):
            label = f"{name} (архив)"

        buttons.append((str(row["id"]), short_button_text(label)))

    return buttons


def members_choice_keyboard(action: str, members: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    # action: setfront | rmfront
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"{action}:{member_id}")]
        for member_id, name in members
    ]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_keyboard(members: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"Подробнее: {name}", callback_data=f"dir:m:{member_id}")]
        for member_id, name in member_button_items(members)
    ]
    rows.append([InlineKeyboardButton(text="В справочник", callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_member_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Новая личность", callback_data="add:new")],
            [InlineKeyboardButton(text="Экспорт JSON", callback_data="add:export")],
            [InlineKeyboardButton(text="Отмена", callback_data="add:cancel")],
        ]
    )


def add_choice_keyboard(prefix: str, groups: list[dict[str, Any]], skip_text: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=short_button_text(str(group.get("name") or "Без названия")),
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
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=short_button_text(str(group.get("name") or "Без названия")),
                callback_data=f"add:cat:{group['id']}",
            )
        ]
        for group in groups
    ]
    if parent_id:
        rows.append([InlineKeyboardButton(text="Выше", callback_data="add:catup")])
    rows.append([InlineKeyboardButton(text=f"Готово ({selected_count})", callback_data="add:catdone")])
    rows.append([InlineKeyboardButton(text="Пропустить категории", callback_data="add:catskip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_category_selected_keyboard(group_id: str, selected: bool) -> InlineKeyboardMarkup:
    text = "Убрать из выбранных" if selected else "Добавить категорию"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=f"add:cattoggle:{group_id}")],
            [InlineKeyboardButton(text="Открыть вложенные", callback_data=f"add:catopen:{group_id}")],
            [InlineKeyboardButton(text="Готово", callback_data="add:catdone")],
        ]
    )


def directory_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Поиск по имени", callback_data="dir:search")],
            [InlineKeyboardButton(text="Категории", callback_data="dir:cats:0")],
            [InlineKeyboardButton(text="Все личности", callback_data="dir:all:0")],
        ]
    )


def directory_categories_keyboard(
    groups: list[dict[str, Any]],
    page: int,
    has_prev: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=short_button_text(str(group.get("name") or "Без названия")),
                callback_data=f"dir:cat:{group['id']}:0",
            )
        ]
        for group in groups
    ]
    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton(text="Назад", callback_data=f"dir:cats:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="Дальше", callback_data=f"dir:cats:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="В справочник", callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def directory_category_keyboard(
    group_id: str,
    child_groups: list[dict[str, Any]],
    page: int,
    has_prev: bool,
    has_next: bool,
    members_count: int,
    parent_id: str | None,
) -> InlineKeyboardMarkup:
    rows = []
    if members_count:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Личности здесь и ниже: {members_count}",
                    callback_data=f"dir:list:{group_id}:0",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=short_button_text(str(group.get("name") or "Без названия")),
                    callback_data=f"dir:cat:{group['id']}:0",
                )
            ]
            for group in child_groups
        ]
    )
    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton(text="Назад", callback_data=f"dir:cat:{group_id}:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="Дальше", callback_data=f"dir:cat:{group_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    back_data = f"dir:cat:{parent_id}:0" if parent_id and parent_id != "root" else "dir:cats:0"
    rows.append([InlineKeyboardButton(text="Выше", callback_data=back_data)])
    rows.append([InlineKeyboardButton(text="В справочник", callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def directory_members_keyboard(
    members: list[dict[str, Any]],
    page: int,
    has_prev: bool,
    has_next: bool,
    page_callback_prefix: str,
    back_callback_data: str,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"dir:m:{member_id}")]
        for member_id, name in member_button_items(members)
    ]

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton(text="Назад", callback_data=f"{page_callback_prefix}:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="Дальше", callback_data=f"{page_callback_prefix}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="Назад к выбору", callback_data=back_callback_data)])
    rows.append([InlineKeyboardButton(text="В справочник", callback_data="dir:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def front_members_keyboard(members: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"rmfront:{member_id}")]
        for member_id, name in members
    ]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
