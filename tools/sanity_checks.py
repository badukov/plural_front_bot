import asyncio
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.formatters import current_status_text, format_front_info, split_long_message
from app.keyboards import (
    directory_categories_keyboard,
    directory_category_keyboard,
    directory_home_keyboard,
    directory_members_keyboard,
    member_button_items,
    members_choice_keyboard,
)
from app.repository import RU_TO_EN_KEYBOARD, _cyrillic_to_latin, repo


MAX_CALLBACK_DATA_BYTES = 64


def _check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)


def _counts() -> dict[str, int]:
    con = sqlite3.connect(settings.database_path)
    cur = con.cursor()
    result: dict[str, int] = {}
    for table in ["members", "groups", "member_groups", "custom_fields", "front_state"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        result[table] = int(cur.fetchone()[0])
    con.close()
    return result


def _duplicate_name_rows() -> list[dict[str, object]]:
    con = sqlite3.connect(settings.database_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, name, pronouns, is_archived
        FROM members
        WHERE name COLLATE NOCASE IN (
            SELECT name
            FROM members
            GROUP BY name COLLATE NOCASE
            HAVING COUNT(*) > 1
        )
        ORDER BY name COLLATE NOCASE, id
        LIMIT 24
        """
    )
    rows = [dict(row) for row in cur.fetchall()]
    con.close()
    return rows


def _first_cyrillic_member() -> dict[str, object] | None:
    con = sqlite3.connect(settings.database_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, name
        FROM members
        WHERE name GLOB '*[А-Яа-яЁё]*'
        ORDER BY name COLLATE NOCASE, id
        LIMIT 1
        """
    )
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None


def _assert_callback_data_is_safe(buttons: list[tuple[str, str]]) -> None:
    markup = members_choice_keyboard("setfront", buttons)
    _assert_markup_callback_data_is_safe(markup)


def _assert_markup_callback_data_is_safe(markup) -> None:
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data:
                size = len(button.callback_data.encode("utf-8"))
                _check("callback_data must fit Telegram 64-byte limit", size <= MAX_CALLBACK_DATA_BYTES)


async def main() -> None:
    counts = _counts()
    _check("members table should not be empty", counts["members"] > 0)
    _check("groups table should not be empty", counts["groups"] > 0)
    _check("member_groups table should not be empty", counts["member_groups"] > 0)
    _check("custom_fields table should not be empty", counts["custom_fields"] > 0)

    front_members = await repo.get_current_front_members()
    status = current_status_text(front_members)
    _check("empty front must be blur", bool(front_members) or status == "блюр")
    _check("non-empty front must start with status prefix", not front_members or status.startswith("фронт - "))

    front_info = await format_front_info(front_members)
    _check("front info chunks must fit Telegram limit", all(len(chunk) <= 3900 for chunk in split_long_message(front_info)))

    long_chunks = split_long_message("\n\n".join(["x" * 1000 for _ in range(10)]))
    _check("long message splitter must split oversized text", len(long_chunks) > 1)
    _check("long message chunks must fit Telegram limit", all(len(chunk) <= 3900 for chunk in long_chunks))

    matches = await repo.search_members("", limit=12)
    buttons = member_button_items(matches)
    _assert_callback_data_is_safe(buttons)
    _assert_markup_callback_data_is_safe(directory_home_keyboard())

    root_groups = await repo.list_child_groups(parent_id=None, limit=8)
    root_total = await repo.count_child_groups(parent_id=None)
    _assert_markup_callback_data_is_safe(
        directory_categories_keyboard(
            groups=root_groups,
            page=0,
            has_prev=False,
            has_next=root_total > 8,
        )
    )

    all_members = await repo.get_all_members_page(limit=8)
    all_total = await repo.count_all_members()
    _assert_markup_callback_data_is_safe(
        directory_members_keyboard(
            members=all_members,
            page=0,
            has_prev=False,
            has_next=all_total > 8,
            page_callback_prefix="dir:all",
            back_callback_data="dir:home",
        )
    )

    if root_groups:
        group = root_groups[0]
        group_id = str(group["id"])
        child_groups = await repo.list_child_groups(parent_id=group_id, limit=8)
        child_total = await repo.count_child_groups(parent_id=group_id)
        members_count = await repo.count_members_for_group_tree(group_id)
        _assert_markup_callback_data_is_safe(
            directory_category_keyboard(
                group_id=group_id,
                child_groups=child_groups,
                page=0,
                has_prev=False,
                has_next=child_total > 8,
                members_count=members_count,
                parent_id=group.get("parent_id"),
            )
        )

    if matches:
        member = await repo.get_member_by_id(str(matches[0]["id"]))
        _check("member lookup by id must return a row", member is not None)
        categories = await repo.get_categories_for_member(str(matches[0]["id"]))
        _check("categories lookup must return a list", isinstance(categories, list))
        mention = await repo.replace_member_mentions(f"<###@{matches[0]['id']}###>")
        _check("known Simply Plural mention must be replaced", not mention.startswith("<###@"))

    cyrillic_member = _first_cyrillic_member()
    if cyrillic_member:
        member_id = str(cyrillic_member["id"])
        name = str(cyrillic_member["name"])
        translit = _cyrillic_to_latin(name.casefold())
        if translit and translit != name.casefold():
            translit_matches = await repo.search_members(translit, limit=12)
            _check(
                "transliterated search should find the source member",
                any(str(row["id"]) == member_id for row in translit_matches),
            )

        keyboard_query = name.casefold().translate(RU_TO_EN_KEYBOARD)
        if keyboard_query and keyboard_query != name.casefold():
            keyboard_matches = await repo.search_members(keyboard_query, limit=12)
            _check(
                "wrong keyboard layout search should find the source member",
                any(str(row["id"]) == member_id for row in keyboard_matches),
            )

    duplicate_rows = _duplicate_name_rows()
    if duplicate_rows:
        duplicate_buttons = member_button_items(duplicate_rows)
        labels = [label for _, label in duplicate_buttons]
        _check("duplicate member names must get distinguishable button labels", len(labels) == len(set(labels)))
        _assert_callback_data_is_safe(duplicate_buttons)

    print("Sanity checks passed.")
    print(
        "Checked counts: "
        f"members={counts['members']}, "
        f"groups={counts['groups']}, "
        f"member_groups={counts['member_groups']}, "
        f"custom_fields={counts['custom_fields']}, "
        f"front_state={counts['front_state']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
