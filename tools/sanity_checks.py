import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.database import init_db
from app.formatters import (
    current_status_text,
    format_front_history,
    format_front_info,
    format_front_statistics,
    format_member_brief,
    split_long_message,
)
from app.i18n import all_button_texts, button_text, is_button_text, normalize_lang
from app.keyboards import (
    add_category_keyboard,
    add_choice_keyboard,
    add_member_menu_keyboard,
    directory_categories_keyboard,
    directory_category_keyboard,
    directory_home_keyboard,
    directory_member_keyboard,
    directory_members_keyboard,
    member_button_items,
    members_choice_keyboard,
)
from app.repository import RU_TO_EN_KEYBOARD, Repository, _cyrillic_to_latin, member_reference, repo


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


def _member_with_group_root(root_name: str) -> str | None:
    con = sqlite3.connect(settings.database_path)
    cur = con.cursor()
    cur.execute(
        """
        WITH RECURSIVE tree(id) AS (
            SELECT id FROM groups WHERE lower(name)=lower(?)
            UNION ALL
            SELECT g.id FROM groups g JOIN tree t ON g.parent_id = t.id
        )
        SELECT mg.member_id
        FROM member_groups mg
        JOIN tree t ON t.id = mg.group_id
        LIMIT 1
        """,
        (root_name,),
    )
    row = cur.fetchone()
    con.close()
    return str(row[0]) if row else None


def _insert_group(cur, group_id: str, parent_id: str, name: str, emoji: str = "") -> None:
    raw = {
        "_id": group_id,
        "id": group_id,
        "parent": parent_id,
        "name": name,
        "emoji": emoji,
        "members": [],
    }
    cur.execute(
        """
        INSERT INTO groups(id, parent_id, name, emoji, description, is_private, raw_json)
        VALUES (?, ?, ?, ?, '', 0, ?)
        """,
        (group_id, parent_id, name, emoji, json.dumps(raw, ensure_ascii=False, sort_keys=True)),
    )


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
    _check("english language code should normalize", normalize_lang("en-US") == "en")
    _check("italian language code should normalize", normalize_lang("it") == "it")
    _check("unknown language should fall back to russian", normalize_lang("de") == "ru")
    _check("localized front button should match", is_button_text(button_text("front", "en"), "front"))
    _check("button registry should include italian notifications", button_text("notifications", "it") in all_button_texts())

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
    admin_directory_markup = directory_home_keyboard(is_admin=True)
    user_directory_markup = directory_home_keyboard(is_admin=False)
    _assert_markup_callback_data_is_safe(admin_directory_markup)
    admin_directory_callbacks = [
        button.callback_data
        for row in admin_directory_markup.inline_keyboard
        for button in row
    ]
    user_directory_callbacks = [
        button.callback_data
        for row in user_directory_markup.inline_keyboard
        for button in row
    ]
    _check("admin directory should expose member management", "add:menu" in admin_directory_callbacks)
    _check("user directory should hide member management", "add:menu" not in user_directory_callbacks)
    admin_member_markup = directory_member_keyboard("member-id", is_admin=True)
    user_member_markup = directory_member_keyboard("member-id", is_admin=False)
    _assert_markup_callback_data_is_safe(admin_member_markup)
    _assert_markup_callback_data_is_safe(user_member_markup)
    admin_callbacks = [
        button.callback_data
        for row in admin_member_markup.inline_keyboard
        for button in row
    ]
    user_callbacks = [
        button.callback_data
        for row in user_member_markup.inline_keyboard
        for button in row
    ]
    _check("admin directory card should expose front actions", "dir:addfront:member-id" in admin_callbacks)
    _check("user directory card should not expose add-front action", "dir:addfront:member-id" not in user_callbacks)
    _check("user directory card should not expose replace-front action", "dir:replacefront:member-id" not in user_callbacks)
    long_member_id = "florality_" + "x" * 80
    long_member_markup = directory_member_keyboard(long_member_id, is_admin=True)
    _assert_markup_callback_data_is_safe(long_member_markup)
    _check("long member ids should use a short callback reference", member_reference(long_member_id).startswith("~"))

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
        _assert_markup_callback_data_is_safe(add_member_menu_keyboard())
        _assert_markup_callback_data_is_safe(add_choice_keyboard("add:role", root_groups[:3], "Пропустить"))
        _assert_markup_callback_data_is_safe(
            add_category_keyboard(root_groups[:3], selected_count=1, parent_id=None)
        )

    if matches:
        member = await repo.get_member_by_id(str(matches[0]["id"]))
        _check("member lookup by id must return a row", member is not None)
        categories = await repo.get_categories_for_member(str(matches[0]["id"]))
        _check("categories lookup must return a list", isinstance(categories, list))
        mention = await repo.replace_member_mentions(f"<###@{matches[0]['id']}###>")
        _check("known Simply Plural mention must be replaced", not mention.startswith("<###@"))

    year_member_id = _member_with_group_root("Years of birth")
    if year_member_id:
        member = await repo.get_member_by_id(year_member_id)
        brief = await format_member_brief(member)
        _check("brief card should include year from category tree", "Год рождения: не указан" not in brief)

    role_member_id = _member_with_group_root("Roles")
    if role_member_id:
        member = await repo.get_member_by_id(role_member_id)
        brief = await format_member_brief(member)
        _check("brief card should include role from category tree", "Роль: не указана" not in brief)

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

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "bot.sqlite3"
        await init_db(db_path)
        temp_repo = Repository(db_path)

        con = sqlite3.connect(db_path)
        cur = con.cursor()
        _insert_group(cur, "years", "root", "Years of birth", "🕰️")
        _insert_group(cur, "year2026", "years", "2026")
        _insert_group(cur, "roles", "root", "Roles", "💼")
        _insert_group(cur, "role1", "roles", "Test role", "💼")
        con.commit()
        con.close()

        created_years = await temp_repo.ensure_future_year_groups()
        _check("future year groups should be created on temp database", bool(created_years))

        member = await temp_repo.create_member(
            name="Temporary Test Member",
            pronouns="they/them",
            description="",
            group_ids=["year2026", "role1"],
            created_by=1,
        )
        found = await temp_repo.search_members("Temporary Test", limit=5)
        _check(
            "created member should be searchable",
            any(row["id"] == member["id"] for row in found),
        )

        avatar_path = str(Path(tmp) / "avatar.jpg")
        avatar_updated = await temp_repo.update_member_avatar_url(member["id"], avatar_path)
        member_with_avatar = await temp_repo.get_member_by_id(member["id"])
        avatar_raw = json.loads(member_with_avatar["raw_json"] or "{}")
        _check("member avatar update should succeed", avatar_updated)
        _check("member avatar update should persist database path", member_with_avatar["avatar_url"] == avatar_path)
        _check("member avatar update should persist export metadata", avatar_raw.get("avatarUrl") == avatar_path)

        await temp_repo.upsert_user(
            telegram_user_id=1,
            chat_id=1,
            username=None,
            first_name=None,
            is_admin=True,
            language_code="en",
        )
        user = await temp_repo.get_user(1)
        _check("user language should be stored", user["language_code"] == "en")
        await temp_repo.update_user_language(1, "it")
        user = await temp_repo.get_user(1)
        _check("user language should update", user["language_code"] == "it")
        subscribed = await temp_repo.toggle_user_subscribed(1)
        _check("toggle should disable initially subscribed user", subscribed is False)
        subscribed = await temp_repo.toggle_user_subscribed(1)
        _check("toggle should enable disabled user", subscribed is True)

        export = await temp_repo.export_simply_plural_data()
        _check("export should contain created member", len(export["members"]) == 1)
        exported_group = next(group for group in export["groups"] if group.get("_id") == "role1")
        _check("export should restore group members links", member["id"] in exported_group.get("members", []))

        await temp_repo.set_external_id("florality", "member", member["id"], "remote-member-id")
        remote_id = await temp_repo.get_external_id("florality", "member", member["id"])
        _check("external id mapping should be stored", remote_id == "remote-member-id")
        local_id = await temp_repo.get_local_id_for_external_id("florality", "member", "remote-member-id")
        _check("external id reverse mapping should be stored", local_id == member["id"])

        unique_by_name = await temp_repo.find_unique_member_by_names(["Temporary Test Member"])
        _check("unique exact member name should resolve", unique_by_name and unique_by_name["id"] == member["id"])

        front_changed = await temp_repo.replace_front_members(
            [member["id"]],
            created_by=None,
            event_type="test_front_replace",
            details={"source": "sanity"},
        )
        _check("front replacement should report changed front", front_changed)
        front_members = await temp_repo.get_current_front_members()
        _check("front replacement should set current front", [row["id"] for row in front_members] == [member["id"]])
        front_unchanged = await temp_repo.replace_front_members(
            [member["id"]],
            created_by=None,
            event_type="test_front_replace",
            details={"source": "sanity"},
        )
        _check("same front replacement should be a no-op", front_unchanged is False)
        await temp_repo.record_current_front_history("test_front_replace", created_by=None)
        history_rows = await temp_repo.get_front_history(limit=5)
        _check("front history should store compressed snapshots", len(history_rows) == 1)
        _check("front history should restore snapshot members", history_rows[0]["members"][0]["id"] == member["id"])
        history_text = format_front_history(history_rows)
        _check("front history should use formatted Telegram time", '<tg-time unix="' in history_text and 'format="dt"' in history_text)
        _check("front history text should fit Telegram limit", all(len(chunk) <= 3900 for chunk in split_long_message(history_text)))
        stats = await temp_repo.get_front_statistics(days=30)
        _check("front statistics should count history rows", stats["changes"] == 1)
        _check("front statistics should include percentage distribution", stats["front_percentages"][0]["percent"] == 100.0)
        stats_text = format_front_statistics(stats)
        _check("front statistics should use formatted Telegram time", '<tg-time unix="' in stats_text and 'format="dt"' in stats_text)
        _check("front statistics text should include percentage", "100.0%" in stats_text)
        _check("front statistics text should fit Telegram limit", all(len(chunk) <= 3900 for chunk in split_long_message(stats_text)))

        imported_member, import_action = await temp_repo.upsert_florality_member(
            {
                "_id": "remote-imported-member",
                "name": "Florality Imported Member",
                "pronouns": "she/her",
                "about": "Imported test description",
                "avatar": "",
            },
            "remote-imported-member",
        )
        _check("Florality member import should create local member", import_action == "created")
        _check("Florality imported member should use local id prefix", imported_member["id"].startswith("florality_"))
        imported_reference = member_reference(imported_member["id"])
        resolved_imported_member = await temp_repo.get_member_by_reference(imported_reference)
        _check(
            "short callback reference should resolve a Florality member",
            resolved_imported_member is not None and resolved_imported_member["id"] == imported_member["id"],
        )

        imported_member, import_action = await temp_repo.upsert_florality_member(
            {
                "_id": "remote-imported-member",
                "name": "Florality Imported Member",
                "pronouns": "she/her",
                "about": "Imported test description",
                "avatar": "",
            },
            "remote-imported-member",
        )
        _check("unchanged Florality member import should be a no-op", import_action == "unchanged")

        imported_member, import_action = await temp_repo.upsert_florality_member(
            {
                "_id": "remote-imported-member",
                "name": "Florality Imported Member Updated",
                "pronouns": "they/them",
                "about": "Imported test description",
                "avatar": "",
            },
            "remote-imported-member",
        )
        _check("changed Florality member import should update local member", import_action == "updated")
        _check("Florality member update should change pronouns", imported_member["pronouns"] == "they/them")
        compared_member, compare_action = await temp_repo.compare_florality_member(
            {
                "_id": "remote-imported-member",
                "name": "Florality Imported Member Updated",
                "pronouns": "they/them",
                "about": "Imported test description",
                "avatar": "",
            },
            "remote-imported-member",
        )
        _check("Florality dry-run compare should detect unchanged member", compared_member["id"] == imported_member["id"] and compare_action == "unchanged")
        compared_member, compare_action = await temp_repo.compare_florality_member(
            {
                "_id": "remote-imported-member",
                "name": "Florality Imported Member Updated",
                "pronouns": "she/her",
                "about": "Imported test description",
                "avatar": "",
            },
            "remote-imported-member",
        )
        _check("Florality dry-run compare should detect changed member", compared_member["id"] == imported_member["id"] and compare_action == "changed")

        deleted = await temp_repo.logical_delete_member(member["id"], created_by=1)
        _check("logical delete should succeed", deleted)
        deleted_group = await temp_repo.find_deleted_group()
        _check("logical delete should create or find deleted group", deleted_group is not None)
        after_delete = await temp_repo.search_members("Temporary Test", limit=5)
        _check(
            "logically deleted member should be hidden from default search",
            all(row["id"] != member["id"] for row in after_delete),
        )
        restored_member, restore_action = await temp_repo.upsert_florality_member(
            {
                "_id": "remote-member-id",
                "name": "Temporary Test Member",
                "pronouns": "they/them",
                "about": "",
                "avatar": "",
            },
            "remote-member-id",
        )
        _check("active Florality import should update a locally deleted mapped member", restore_action == "updated")
        restored_search = await temp_repo.search_members("Temporary Test", limit=5)
        _check(
            "active Florality import should restore member from deleted group",
            any(row["id"] == restored_member["id"] for row in restored_search),
        )

        compared_member, compare_action = await temp_repo.compare_florality_member(
            {
                "_id": "remote-imported-member",
                "name": "Florality Imported Member Updated",
                "pronouns": "they/them ",
                "about": "Imported test description ",
            },
            "remote-imported-member",
        )
        _check(
            "Florality comparison should ignore surrounding whitespace",
            compared_member is not None and compare_action == "unchanged",
        )

        await temp_repo.create_member("Ambiguous Florality Name", "", "", [], created_by=1)
        await temp_repo.create_member("Ambiguous Florality Name", "", "", [], created_by=1)
        ambiguous_member, ambiguous_action = await temp_repo.compare_florality_member(
            {"_id": "ambiguous-remote", "name": "Ambiguous Florality Name"},
            "ambiguous-remote",
        )
        _check(
            "duplicate local names should be reported as an ambiguous Florality match",
            ambiguous_member is None and ambiguous_action == "ambiguous",
        )
        try:
            await temp_repo.upsert_florality_member(
                {"_id": "ambiguous-remote", "name": "Ambiguous Florality Name"},
                "ambiguous-remote",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("ambiguous Florality import must not create another local member")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "old_users.sqlite3"
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE users (
                telegram_user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0,
                subscribed INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        con.commit()
        con.close()
        await init_db(db_path)
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cur.fetchall()}
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='external_ids'")
        external_ids_exists = cur.fetchone() is not None
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='front_history'")
        front_history_exists = cur.fetchone() is not None
        con.close()
        _check("users migration should add language_code", "language_code" in user_columns)
        _check("init should create external id mappings table", external_ids_exists)
        _check("init should create front history table", front_history_exists)

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
