import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

from app.database import init_db


@dataclass(frozen=True)
class ImportResult:
    members_imported: int
    groups_imported: int
    member_group_links_imported: int
    custom_fields_imported: int
    warnings: list[str]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _member_id(member: dict[str, Any]) -> str | None:
    return member.get("_id") or member.get("id") or member.get("uid")


def _group_id(group: dict[str, Any]) -> str | None:
    return group.get("_id") or group.get("id")


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


async def import_simply_plural_export(export_path: Path, db_path: Path) -> ImportResult:
    if not export_path.exists():
        raise FileNotFoundError(f"Simply Plural export not found: {export_path}")

    with export_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    await init_db(db_path)

    members = _as_list(data.get("members"))
    groups = _as_list(data.get("groups"))
    custom_fields = _as_list(data.get("customFields"))

    warnings: list[str] = []
    member_ids: set[str] = set()
    group_ids: set[str] = set()

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Перезаливаем справочник Simply Plural, но не трогаем пользователей/текущий фронт/ивенты.
        await db.execute("DELETE FROM member_groups")
        await db.execute("DELETE FROM groups")
        await db.execute("DELETE FROM custom_fields")
        await db.execute("DELETE FROM members")

        members_imported = 0
        for index, member in enumerate(members, start=1):
            if not isinstance(member, dict):
                warnings.append(f"Skipped member #{index}: entry is not an object")
                continue

            mid = _member_id(member)
            name = str(member.get("name") or "").strip()
            if not mid or not name:
                warnings.append(f"Skipped member #{index}: missing id or name")
                continue

            member_ids.add(mid)
            await db.execute(
                """
                INSERT INTO members(
                    id, name, pronouns, description, color, avatar_url, avatar_uuid,
                    pk_id, is_private, is_archived, archived_reason, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    name,
                    member.get("pronouns") or "",
                    member.get("desc") or member.get("description") or "",
                    member.get("color") or "",
                    member.get("avatarUrl") or member.get("avatar_url") or "",
                    member.get("avatarUuid") or member.get("avatar_uuid") or "",
                    member.get("pkId") or "",
                    1 if member.get("private") else 0,
                    1 if member.get("archived") else 0,
                    member.get("archivedReason") or "",
                    _json(member),
                ),
            )
            members_imported += 1

        groups_imported = 0
        for index, group in enumerate(groups, start=1):
            if not isinstance(group, dict):
                warnings.append(f"Skipped group #{index}: entry is not an object")
                continue

            gid = _group_id(group)
            name = str(group.get("name") or "").strip()
            if not gid or not name:
                warnings.append(f"Skipped group #{index}: missing id or name")
                continue

            group_ids.add(gid)
            await db.execute(
                """
                INSERT INTO groups(
                    id, parent_id, name, emoji, description, is_private, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gid,
                    group.get("parent") or group.get("parentId") or "root",
                    name,
                    group.get("emoji") or "",
                    group.get("desc") or group.get("description") or "",
                    1 if group.get("private") else 0,
                    _json(group),
                ),
            )
            groups_imported += 1

        custom_fields_imported = 0
        for field in custom_fields:
            if not isinstance(field, dict):
                continue
            fid = field.get("_id") or field.get("id")
            name = str(field.get("name") or "").strip()
            if not fid or not name:
                continue
            await db.execute(
                """
                INSERT INTO custom_fields(id, oid, name, type, support_markdown, raw_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    field.get("oid") or "",
                    name,
                    field.get("type"),
                    1 if field.get("supportMarkdown") else 0,
                    _json(field),
                ),
            )
            custom_fields_imported += 1

        links = set()
        for index, group in enumerate(groups, start=1):
            if not isinstance(group, dict):
                continue
            gid = _group_id(group)
            if not gid or gid not in group_ids:
                continue
            for mid in _as_list(group.get("members")):
                if mid not in member_ids:
                    warnings.append(f"Group #{index} references an unknown member id")
                    continue
                links.add((mid, gid))

        for mid, gid in sorted(links):
            await db.execute(
                "INSERT OR IGNORE INTO member_groups(member_id, group_id) VALUES (?, ?)",
                (mid, gid),
            )

        await db.commit()

    return ImportResult(
        members_imported=members_imported,
        groups_imported=groups_imported,
        member_group_links_imported=len(links),
        custom_fields_imported=custom_fields_imported,
        warnings=warnings,
    )


async def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import Simply Plural JSON export")
    parser.add_argument("export", type=Path)
    parser.add_argument("--db", type=Path, default=Path("data/bot.sqlite3"))
    args = parser.parse_args()

    result = await import_simply_plural_export(args.export, args.db)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
