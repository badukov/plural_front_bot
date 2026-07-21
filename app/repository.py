import hashlib
import base64
import gzip
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite
from rapidfuzz import fuzz

from app.config import settings


MENTION_RE = re.compile(r"<###@([^#<>]+)###>")
SEARCH_SPLIT_RE = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)
DELETED_GROUP_NAMES = {"deleted", "trash", "удаленные", "удалённые", "удалено"}
EXTERNAL_ID_CLEANUP_RE = re.compile(r"[^0-9A-Za-z_-]+")
MEMBER_REFERENCE_PREFIX = "~"

EN_TO_RU_KEYBOARD_MAP = {
    "q": "й",
    "w": "ц",
    "e": "у",
    "r": "к",
    "t": "е",
    "y": "н",
    "u": "г",
    "i": "ш",
    "o": "щ",
    "p": "з",
    "[": "х",
    "]": "ъ",
    "a": "ф",
    "s": "ы",
    "d": "в",
    "f": "а",
    "g": "п",
    "h": "р",
    "j": "о",
    "k": "л",
    "l": "д",
    ";": "ж",
    "'": "э",
    "z": "я",
    "x": "ч",
    "c": "с",
    "v": "м",
    "b": "и",
    "n": "т",
    "m": "ь",
    ",": "б",
    ".": "ю",
    "`": "ё",
}
EN_TO_RU_KEYBOARD = str.maketrans(EN_TO_RU_KEYBOARD_MAP)
RU_TO_EN_KEYBOARD = str.maketrans({v: k for k, v in EN_TO_RU_KEYBOARD_MAP.items()})

CYR_TO_LAT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

LAT_TO_CYR = [
    ("shch", "щ"),
    ("sch", "щ"),
    ("yo", "ё"),
    ("yu", "ю"),
    ("ya", "я"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("ts", "ц"),
    ("a", "а"),
    ("b", "б"),
    ("v", "в"),
    ("g", "г"),
    ("d", "д"),
    ("e", "е"),
    ("z", "з"),
    ("i", "и"),
    ("j", "й"),
    ("y", "й"),
    ("k", "к"),
    ("l", "л"),
    ("m", "м"),
    ("n", "н"),
    ("o", "о"),
    ("p", "п"),
    ("r", "р"),
    ("s", "с"),
    ("t", "т"),
    ("u", "у"),
    ("f", "ф"),
    ("h", "х"),
    ("c", "к"),
]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _normalize_search_text(text: str) -> str:
    normalized = text.casefold().replace("ё", "е")
    normalized = SEARCH_SPLIT_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def _compact_search_text(text: str) -> str:
    return text.replace(" ", "")


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def member_reference(member_id: str) -> str:
    value = str(member_id)
    if len(value.encode("utf-8")) <= 40:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{MEMBER_REFERENCE_PREFIX}{digest}"


def _pack_json(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def _unpack_json(value: str) -> Any:
    raw = gzip.decompress(base64.b64decode(value.encode("ascii")))
    return json.loads(raw.decode("utf-8"))


def _cyrillic_to_latin(text: str) -> str:
    return "".join(CYR_TO_LAT.get(char, char) for char in text)


def _latin_to_cyrillic(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        for latin, cyrillic in LAT_TO_CYR:
            if text.startswith(latin, index):
                result.append(cyrillic)
                index += len(latin)
                break
        else:
            result.append(text[index])
            index += 1
    return "".join(result)


def _search_variants(text: str) -> set[str]:
    raw = text.casefold().strip()
    base_values = {
        raw,
        raw.translate(EN_TO_RU_KEYBOARD),
        raw.translate(RU_TO_EN_KEYBOARD),
        _cyrillic_to_latin(raw),
        _latin_to_cyrillic(raw),
    }

    variants: set[str] = set()
    for value in base_values:
        normalized = _normalize_search_text(value)
        if not normalized:
            continue
        variants.add(normalized)
        compact = _compact_search_text(normalized)
        if compact:
            variants.add(compact)
        transliterated = _normalize_search_text(_cyrillic_to_latin(normalized))
        if transliterated:
            variants.add(transliterated)
            variants.add(_compact_search_text(transliterated))

    return {variant for variant in variants if variant}


def _best_search_score(query_variants: set[str], name_variants: set[str]) -> float:
    best = 0.0
    for query in query_variants:
        for name in name_variants:
            if not query or not name:
                continue
            if query == name:
                best = max(best, 100.0)
            elif query in name:
                coverage = min(1.0, len(query) / max(len(name), 1))
                best = max(best, 78.0 + coverage * 18.0)
            elif name in query:
                coverage = min(1.0, len(name) / max(len(query), 1))
                best = max(best, 68.0 + coverage * 12.0)

            best = max(
                best,
                float(fuzz.WRatio(query, name)),
                float(fuzz.partial_ratio(query, name)) * 0.95,
            )
    return best


class Repository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.database_path

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            yield db

    async def upsert_user(
        self,
        telegram_user_id: int,
        chat_id: int,
        username: str | None,
        first_name: str | None,
        is_admin: bool,
        language_code: str | None = None,
    ) -> None:
        now = _now_ms()
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO users (
                    telegram_user_id, chat_id, username, first_name, language_code, is_admin,
                    subscribed, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    chat_id=excluded.chat_id,
                    username=excluded.username,
                    first_name=excluded.first_name,
                    language_code=excluded.language_code,
                    is_admin=excluded.is_admin,
                    subscribed=1,
                    updated_at=excluded.updated_at
                """,
                (
                    telegram_user_id,
                    chat_id,
                    username,
                    first_name,
                    language_code,
                    1 if is_admin else 0,
                    now,
                    now,
                ),
            )
            await db.commit()

    async def update_user_language(self, telegram_user_id: int, language_code: str | None) -> None:
        async with self._connect() as db:
            await db.execute(
                "UPDATE users SET language_code=?, updated_at=? WHERE telegram_user_id=?",
                (language_code, _now_ms(), telegram_user_id),
            )
            await db.commit()

    async def update_user_language_override(self, telegram_user_id: int, language: str | None) -> bool:
        async with self._connect() as db:
            cursor = await db.execute(
                "UPDATE users SET language_override=?, updated_at=? WHERE telegram_user_id=?",
                (language, _now_ms(), telegram_user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def set_user_subscribed(self, telegram_user_id: int, subscribed: bool) -> None:
        async with self._connect() as db:
            await db.execute(
                "UPDATE users SET subscribed=?, updated_at=? WHERE telegram_user_id=?",
                (1 if subscribed else 0, _now_ms(), telegram_user_id),
            )
            await db.commit()

    async def get_user(self, telegram_user_id: int) -> dict[str, Any] | None:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE telegram_user_id=?",
                (telegram_user_id,),
            )
            return _row_to_dict(await cursor.fetchone())

    async def toggle_user_subscribed(self, telegram_user_id: int) -> bool:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT subscribed FROM users WHERE telegram_user_id=?",
                (telegram_user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return False

            subscribed = not bool(row["subscribed"])
            await db.execute(
                "UPDATE users SET subscribed=?, updated_at=? WHERE telegram_user_id=?",
                (1 if subscribed else 0, _now_ms(), telegram_user_id),
            )
            await db.commit()
            return subscribed

    async def get_subscribed_users(self) -> list[dict[str, Any]]:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE subscribed=1 ORDER BY created_at"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def sync_admin_flags(self, admin_ids: set[int]) -> None:
        async with self._connect() as db:
            await db.execute("UPDATE users SET is_admin=0")
            if admin_ids:
                placeholders = ",".join("?" for _ in admin_ids)
                await db.execute(
                    f"UPDATE users SET is_admin=1 WHERE telegram_user_id IN ({placeholders})",
                    tuple(sorted(admin_ids)),
                )
            await db.commit()

    async def get_subscribed_admin_users(
        self,
        admin_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        active_admin_ids = settings.admin_ids if admin_ids is None else admin_ids
        if not active_admin_ids:
            return []
        placeholders = ",".join("?" for _ in active_admin_ids)
        async with self._connect() as db:
            cursor = await db.execute(
                f"""
                SELECT *
                FROM users
                WHERE subscribed=1 AND telegram_user_id IN ({placeholders})
                ORDER BY created_at
                """,
                tuple(sorted(active_admin_ids)),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def count_members(self) -> int:
        async with self._connect() as db:
            cursor = await db.execute("SELECT COUNT(*) AS c FROM members")
            row = await cursor.fetchone()
            return int(row["c"])

    async def get_member_name_map(self) -> dict[str, str]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT id, name FROM members")
            rows = await cursor.fetchall()
            return {row["id"]: row["name"] for row in rows}

    async def search_members(self, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        limit = limit or settings.search_limit
        query_norm = query.strip()

        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT id, name, pronouns, is_private, is_archived
                FROM members
                ORDER BY name COLLATE NOCASE
                """
            )
            rows = [dict(row) for row in await cursor.fetchall()]

        deleted_ids = await self.get_deleted_member_ids()
        rows = [row for row in rows if row["id"] not in deleted_ids]

        if not query_norm:
            return rows[:limit]

        query_variants = _search_variants(query_norm)
        if not query_variants:
            return rows[:limit]

        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for row in rows:
            score = _best_search_score(query_variants, _search_variants(row["name"] or ""))
            if score > 0:
                ranked.append((score, row["name"] or "", row))

        ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
        confident = [row for score, _, row in ranked if score >= 35]
        if confident:
            return confident[:limit]
        return [row for _, _, row in ranked[:limit]]

    async def add_to_front(self, member_id: str, created_by: int | None) -> bool:
        now = _now_ms()
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT member_id FROM front_state WHERE member_id=?",
                (member_id,),
            )
            existing = await cursor.fetchone()
            if existing:
                return False

            await db.execute(
                "INSERT INTO front_state(member_id, fronted_at) VALUES (?, ?)",
                (member_id, now),
            )
            await db.execute(
                """
                INSERT INTO events(event_type, member_id, created_by, created_at, details_json)
                VALUES ('front_added', ?, ?, ?, NULL)
                """,
                (member_id, created_by, now),
            )
            await db.commit()
            return True

    async def remove_from_front(self, member_id: str, created_by: int | None) -> bool:
        now = _now_ms()
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT member_id FROM front_state WHERE member_id=?",
                (member_id,),
            )
            existing = await cursor.fetchone()
            if not existing:
                return False

            await db.execute("DELETE FROM front_state WHERE member_id=?", (member_id,))
            await db.execute(
                """
                INSERT INTO events(event_type, member_id, created_by, created_at, details_json)
                VALUES ('front_removed', ?, ?, ?, NULL)
                """,
                (member_id, created_by, now),
            )
            await db.commit()
            return True

    async def clear_front(self, created_by: int | None) -> None:
        now = _now_ms()
        async with self._connect() as db:
            await db.execute("DELETE FROM front_state")
            await db.execute(
                """
                INSERT INTO events(event_type, member_id, created_by, created_at, details_json)
                VALUES ('blur', NULL, ?, ?, NULL)
                """,
                (created_by, now),
            )
            await db.commit()

    async def get_current_front_members(self) -> list[dict[str, Any]]:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT m.*, fs.fronted_at
                FROM front_state fs
                JOIN members m ON m.id = fs.member_id
                ORDER BY fs.fronted_at ASC, m.name COLLATE NOCASE
                """
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def record_current_front_history(self, event_type: str, created_by: int | None) -> None:
        front_members = await self.get_current_front_members()
        snapshot = {
            "members": [
                {
                    "id": str(member.get("id") or ""),
                    "name": str(member.get("name") or ""),
                }
                for member in front_members
            ],
        }
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO front_history(event_type, created_by, created_at, snapshot_json_z)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, created_by, _now_ms(), _pack_json(snapshot)),
            )
            await db.commit()
        await self.archive_front_history()

    async def archive_front_history(self, older_than_ms: int | None = None) -> int:
        if older_than_ms is None:
            older_than_ms = _now_ms() - settings.front_history_active_days * 24 * 60 * 60 * 1000
        archived_at = _now_ms()
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) AS c FROM front_history WHERE created_at < ?",
                (older_than_ms,),
            )
            count = int((await cursor.fetchone())["c"])
            if not count:
                return 0
            await db.execute(
                """
                INSERT INTO front_history_archive(
                    id, event_type, created_by, created_at, snapshot_json_z, archived_at
                )
                SELECT id, event_type, created_by, created_at, snapshot_json_z, ?
                FROM front_history
                WHERE created_at < ?
                ON CONFLICT(id) DO UPDATE SET
                    event_type=excluded.event_type,
                    created_by=excluded.created_by,
                    created_at=excluded.created_at,
                    snapshot_json_z=excluded.snapshot_json_z,
                    archived_at=excluded.archived_at
                """,
                (archived_at, older_than_ms),
            )
            await db.execute("DELETE FROM front_history WHERE created_at < ?", (older_than_ms,))
            await db.commit()
            return count

    async def count_front_history(self) -> int:
        async with self._connect() as db:
            cursor = await db.execute("SELECT COUNT(*) AS c FROM front_history")
            row = await cursor.fetchone()
            return int(row["c"])

    async def get_front_history(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT id, event_type, created_by, created_at, snapshot_json_z
                FROM front_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = [dict(row) for row in await cursor.fetchall()]

        result = []
        for row in rows:
            try:
                snapshot = _unpack_json(row["snapshot_json_z"])
            except Exception:
                snapshot = {"members": []}
            result.append(
                {
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                    "members": snapshot.get("members") if isinstance(snapshot, dict) else [],
                }
            )
        return result

    async def get_sync_state(self, key: str) -> str | None:
        async with self._connect() as db:
            cursor = await db.execute("SELECT value FROM sync_state WHERE key=?", (key,))
            row = await cursor.fetchone()
            return str(row["value"]) if row else None

    async def set_sync_state(self, key: str, value: str) -> None:
        now = _now_ms()
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO sync_state(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, now),
            )
            await db.commit()

    async def upsert_florality_front_sessions(self, sessions: list[dict[str, Any]]) -> tuple[int, int]:
        inserted = 0
        changed = 0
        synced_at = _now_ms()
        async with self._connect() as db:
            for item in sessions:
                session_id = str(item.get("session_id") or "")
                if not session_id:
                    continue
                values = (
                    str(item.get("remote_member_id") or ""),
                    str(item.get("local_member_id") or "") or None,
                    str(item.get("member_name") or item.get("remote_member_id") or ""),
                    int(item.get("started_at") or 0),
                    int(item["ended_at"]) if item.get("ended_at") is not None else None,
                    int(item["edited_at"]) if item.get("edited_at") is not None else None,
                    1 if item.get("edited_manually") else 0,
                    synced_at,
                    _json(item.get("raw") or {}),
                )
                cursor = await db.execute(
                    """
                    SELECT remote_member_id, local_member_id, member_name, started_at,
                           ended_at, edited_at, edited_manually
                    FROM florality_front_sessions WHERE session_id=?
                    UNION ALL
                    SELECT remote_member_id, local_member_id, member_name, started_at,
                           ended_at, edited_at, edited_manually
                    FROM florality_front_sessions_archive WHERE session_id=?
                    LIMIT 1
                    """,
                    (session_id, session_id),
                )
                existing = await cursor.fetchone()
                if existing is None:
                    inserted += 1
                else:
                    comparable = tuple(existing[key] for key in (
                        "remote_member_id", "local_member_id", "member_name", "started_at",
                        "ended_at", "edited_at", "edited_manually",
                    ))
                    if comparable != values[:7]:
                        changed += 1
                await db.execute(
                    "DELETE FROM florality_front_sessions_archive WHERE session_id=?",
                    (session_id,),
                )
                await db.execute(
                    """
                    INSERT INTO florality_front_sessions(
                        session_id, remote_member_id, local_member_id, member_name,
                        started_at, ended_at, edited_at, edited_manually, synced_at, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        remote_member_id=excluded.remote_member_id,
                        local_member_id=excluded.local_member_id,
                        member_name=excluded.member_name,
                        started_at=excluded.started_at,
                        ended_at=excluded.ended_at,
                        edited_at=excluded.edited_at,
                        edited_manually=excluded.edited_manually,
                        synced_at=excluded.synced_at,
                        raw_json=excluded.raw_json
                    """,
                    (session_id, *values),
                )
            await db.commit()
        return inserted, changed

    async def archive_florality_front_sessions(self, older_than_ms: int) -> int:
        archived_at = _now_ms()
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) AS c FROM florality_front_sessions WHERE ended_at IS NOT NULL AND ended_at < ?",
                (older_than_ms,),
            )
            count = int((await cursor.fetchone())["c"])
            if not count:
                return 0
            await db.execute(
                """
                INSERT INTO florality_front_sessions_archive(
                    session_id, remote_member_id, local_member_id, member_name,
                    started_at, ended_at, edited_at, edited_manually,
                    synced_at, archived_at, raw_json
                )
                SELECT session_id, remote_member_id, local_member_id, member_name,
                       started_at, ended_at, edited_at, edited_manually,
                       synced_at, ?, raw_json
                FROM florality_front_sessions
                WHERE ended_at IS NOT NULL AND ended_at < ?
                ON CONFLICT(session_id) DO UPDATE SET
                    remote_member_id=excluded.remote_member_id,
                    local_member_id=excluded.local_member_id,
                    member_name=excluded.member_name,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    edited_at=excluded.edited_at,
                    edited_manually=excluded.edited_manually,
                    synced_at=excluded.synced_at,
                    archived_at=excluded.archived_at,
                    raw_json=excluded.raw_json
                """,
                (archived_at, older_than_ms),
            )
            await db.execute(
                "DELETE FROM florality_front_sessions WHERE ended_at IS NOT NULL AND ended_at < ?",
                (older_than_ms,),
            )
            await db.commit()
            return count

    async def count_florality_front_sessions(self) -> int:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM florality_front_sessions) +
                    (SELECT COUNT(*) FROM florality_front_sessions_archive) AS c
                """
            )
            return int((await cursor.fetchone())["c"])

    async def get_florality_front_statistics(self, days: int | None = 30) -> dict[str, Any]:
        now = _now_ms()
        since = now - days * 24 * 60 * 60 * 1000 if days is not None else 0
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT session_id, remote_member_id, member_name, started_at, ended_at, edited_at
                FROM florality_front_sessions
                WHERE started_at <= ? AND (ended_at IS NULL OR ended_at >= ?)
                UNION ALL
                SELECT session_id, remote_member_id, member_name, started_at, ended_at, edited_at
                FROM florality_front_sessions_archive
                WHERE started_at <= ? AND (ended_at IS NULL OR ended_at >= ?)
                ORDER BY started_at ASC
                """,
                (now, since, now, since),
            )
            rows = [dict(row) for row in await cursor.fetchall()]

        durations: dict[str, int] = {}
        session_counts: dict[str, int] = {}
        member_names: dict[str, str] = {}
        day_counts: dict[str, int] = {}
        last_change_at = 0
        for row in rows:
            name = str(row.get("member_name") or "").strip()
            if not name:
                continue
            member_key = str(row.get("remote_member_id") or name)
            member_names[member_key] = name
            started_at = max(since, int(row["started_at"]))
            ended_at = min(now, int(row["ended_at"]) if row.get("ended_at") is not None else now)
            duration = max(0, ended_at - started_at)
            durations[member_key] = durations.get(member_key, 0) + duration
            session_counts[member_key] = session_counts.get(member_key, 0) + 1
            day = time.strftime("%Y-%m-%d", time.gmtime(int(row["started_at"]) / 1000))
            day_counts[day] = day_counts.get(day, 0) + 1
            last_change_at = max(
                last_change_at,
                int(row.get("edited_at") or row.get("ended_at") or row["started_at"]),
            )

        sorted_members = sorted(
            durations.items(),
            key=lambda item: (-item[1], member_names[item[0]].casefold(), item[0]),
        )
        total_duration = sum(durations.values())
        return {
            "days": days if days is not None else "all",
            "duration_based": True,
            "changes": len(rows),
            "blur_count": 0,
            "unique_count": len(durations),
            "top_members": [(member_names[key], duration) for key, duration in sorted_members[:5]],
            "front_percentages": [
                {
                    "name": member_names[key],
                    "count": session_counts.get(key, 0),
                    "duration_ms": duration,
                    "percent": (duration / total_duration * 100) if total_duration else 0.0,
                }
                for key, duration in sorted_members
            ],
            "total_front_appearances": sum(session_counts.values()),
            "total_duration_ms": total_duration,
            "busiest_day": max(day_counts.items(), key=lambda item: item[1]) if day_counts else None,
            "last_change_at": last_change_at,
        }

    async def get_front_statistics(self, days: int | None = 30) -> dict[str, Any]:
        if await self.count_florality_front_sessions():
            return await self.get_florality_front_statistics(days)
        now = _now_ms()
        since = now - days * 24 * 60 * 60 * 1000 if days is not None else 0
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT id, event_type, created_at, snapshot_json_z
                FROM (
                    SELECT id, event_type, created_at, snapshot_json_z FROM front_history
                    UNION ALL
                    SELECT id, event_type, created_at, snapshot_json_z FROM front_history_archive
                )
                WHERE created_at >= ? AND created_at <= ?
                ORDER BY created_at ASC, id ASC
                """,
                (since, now),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
            if since:
                cursor = await db.execute(
                    """
                    SELECT id, event_type, created_at, snapshot_json_z
                    FROM (
                        SELECT id, event_type, created_at, snapshot_json_z FROM front_history
                        UNION ALL
                        SELECT id, event_type, created_at, snapshot_json_z FROM front_history_archive
                    )
                    WHERE created_at < ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (since,),
                )
                baseline = await cursor.fetchone()
                if baseline:
                    rows.insert(0, dict(baseline))

        durations: dict[str, int] = {}
        session_counts: dict[str, int] = {}
        member_names: dict[str, str] = {}
        day_counts: dict[str, int] = {}
        blur_count = 0
        last_change_at = 0
        previous_member_ids: set[str] = set()
        changes = 0
        for index, row in enumerate(rows):
            created_at = int(row["created_at"])
            next_created_at = int(rows[index + 1]["created_at"]) if index + 1 < len(rows) else now
            interval_start = max(since, created_at)
            interval_end = min(now, next_created_at)
            try:
                snapshot = _unpack_json(row["snapshot_json_z"])
            except Exception:
                snapshot = {"members": []}
            members = snapshot.get("members") if isinstance(snapshot, dict) else []
            current_member_ids: set[str] = set()
            if not members:
                blur_count += 1
            for member in members:
                if not isinstance(member, dict):
                    continue
                name = str(member.get("name") or "").strip()
                if not name:
                    continue
                member_key = str(member.get("id") or name)
                current_member_ids.add(member_key)
                member_names[member_key] = name
                duration = max(0, interval_end - interval_start)
                durations[member_key] = durations.get(member_key, 0) + duration
            for member_key in current_member_ids - previous_member_ids:
                session_counts[member_key] = session_counts.get(member_key, 0) + 1
            previous_member_ids = current_member_ids
            if created_at >= since:
                changes += 1
                last_change_at = max(last_change_at, created_at)
                day = time.strftime("%Y-%m-%d", time.gmtime(created_at / 1000))
                day_counts[day] = day_counts.get(day, 0) + 1

        sorted_members = sorted(
            durations.items(),
            key=lambda item: (-item[1], member_names[item[0]].casefold(), item[0]),
        )
        total_duration = sum(durations.values())
        return {
            "days": days if days is not None else "all",
            "duration_based": True,
            "changes": changes,
            "blur_count": blur_count,
            "unique_count": len(durations),
            "top_members": [(member_names[key], duration) for key, duration in sorted_members[:5]],
            "front_percentages": [
                {
                    "name": member_names[key],
                    "count": session_counts.get(key, 0),
                    "duration_ms": duration,
                    "percent": (duration / total_duration * 100) if total_duration else 0.0,
                }
                for key, duration in sorted_members
            ],
            "total_front_appearances": sum(session_counts.values()),
            "total_duration_ms": total_duration,
            "busiest_day": max(day_counts.items(), key=lambda item: item[1]) if day_counts else None,
            "last_change_at": last_change_at,
        }

    async def get_member_by_id(self, member_id: str) -> dict[str, Any] | None:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM members WHERE id=?", (member_id,))
            return _row_to_dict(await cursor.fetchone())

    async def get_member_by_reference(self, reference: str | None) -> dict[str, Any] | None:
        if not reference:
            return None
        exact = await self.get_member_by_id(reference)
        if exact or not reference.startswith(MEMBER_REFERENCE_PREFIX):
            return exact
        async with self._connect() as db:
            cursor = await db.execute("SELECT id FROM members ORDER BY id")
            matching_ids = [
                str(row["id"])
                for row in await cursor.fetchall()
                if member_reference(str(row["id"])) == reference
            ]
        if len(matching_ids) != 1:
            return None
        return await self.get_member_by_id(matching_ids[0])

    async def get_external_id(self, provider: str, entity_type: str, local_id: str) -> str | None:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT remote_id
                FROM external_ids
                WHERE provider=? AND entity_type=? AND local_id=?
                """,
                (provider, entity_type, local_id),
            )
            row = await cursor.fetchone()
            return str(row["remote_id"]) if row else None

    async def set_external_id(
        self,
        provider: str,
        entity_type: str,
        local_id: str,
        remote_id: str,
    ) -> None:
        now = _now_ms()
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO external_ids(provider, entity_type, local_id, remote_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, entity_type, local_id) DO UPDATE SET
                    remote_id=excluded.remote_id,
                    updated_at=excluded.updated_at
                """,
                (provider, entity_type, local_id, remote_id, now, now),
            )
            await db.commit()

    async def get_local_id_for_external_id(self, provider: str, entity_type: str, remote_id: str) -> str | None:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT local_id
                FROM external_ids
                WHERE provider=? AND entity_type=? AND remote_id=?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (provider, entity_type, remote_id),
            )
            row = await cursor.fetchone()
            return str(row["local_id"]) if row else None

    async def get_external_id_mappings(self, provider: str, entity_type: str) -> list[dict[str, Any]]:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT local_id, remote_id
                FROM external_ids
                WHERE provider=? AND entity_type=?
                ORDER BY updated_at DESC
                """,
                (provider, entity_type),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def find_members_by_names(self, names: list[str]) -> list[dict[str, Any]]:
        normalized_names = {_normalize_search_text(name) for name in names if name and _normalize_search_text(name)}
        if not normalized_names:
            return []

        deleted_ids = await self.get_deleted_member_ids()
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM members
                ORDER BY name COLLATE NOCASE, id
                """
            )
            rows = [dict(row) for row in await cursor.fetchall()]

        return [
            row
            for row in rows
            if row["id"] not in deleted_ids and _normalize_search_text(row.get("name") or "") in normalized_names
        ]

    async def find_unique_member_by_names(self, names: list[str]) -> dict[str, Any] | None:
        matches = await self.find_members_by_names(names)
        unique_ids = {row["id"] for row in matches}
        if len(unique_ids) == 1:
            return matches[0]
        return None

    async def compare_florality_member(
        self,
        remote_member: dict[str, Any],
        remote_id: str,
    ) -> tuple[dict[str, Any] | None, str]:
        mapped_local_id = await self.get_local_id_for_external_id("florality", "member", remote_id)
        existing = await self.get_member_by_id(mapped_local_id) if mapped_local_id else None

        if not existing:
            matches = await self.find_members_by_names(
                [
                    str(remote_member.get("name") or "").strip(),
                    str(remote_member.get("displayName") or "").strip(),
                ]
            )
            if len({member["id"] for member in matches}) > 1:
                return None, "ambiguous"
            existing = matches[0] if matches else None

        if not existing:
            return None, "missing"

        deleted_ids = await self.get_deleted_member_ids()
        if existing["id"] in deleted_ids and not remote_member.get("deletedAt"):
            return existing, "missing"

        comparisons: list[tuple[str, str | int]] = []
        name = str(remote_member.get("name") or remote_member.get("displayName") or "").strip()
        if name:
            comparisons.append(("name", name))
        if "pronouns" in remote_member:
            comparisons.append(("pronouns", str(remote_member.get("pronouns") or "").strip()))
        if "about" in remote_member:
            comparisons.append(("description", str(remote_member.get("about") or "").strip()))
        if "deletedAt" in remote_member:
            comparisons.append(("is_archived", 1 if remote_member.get("deletedAt") else 0))
            if remote_member.get("deletedAt"):
                comparisons.append(("archived_reason", "Deleted in Florality"))

        comparable = {
            "name": existing.get("name") or "",
            "pronouns": str(existing.get("pronouns") or "").strip(),
            "description": str(existing.get("description") or "").strip(),
            "is_archived": 1 if existing.get("is_archived") else 0,
            "archived_reason": existing.get("archived_reason") or "",
        }
        return existing, "unchanged" if all(comparable[key] == value for key, value in comparisons) else "changed"

    async def upsert_florality_member(self, remote_member: dict[str, Any], remote_id: str) -> tuple[dict[str, Any], str]:
        name = str(remote_member.get("name") or remote_member.get("displayName") or "").strip()
        if not name:
            raise ValueError("Florality member has no name")

        mapped_local_id = await self.get_local_id_for_external_id("florality", "member", remote_id)
        existing = await self.get_member_by_id(mapped_local_id) if mapped_local_id else None

        if not existing:
            matches = await self.find_members_by_names(
                [
                    str(remote_member.get("name") or "").strip(),
                    str(remote_member.get("displayName") or "").strip(),
                ]
            )
            if len({member["id"] for member in matches}) > 1:
                raise ValueError("Florality member name matches multiple local members")
            existing = matches[0] if matches else None

        cleaned_remote_id = EXTERNAL_ID_CLEANUP_RE.sub("_", remote_id).strip("_") or "member"
        remote_digest = hashlib.sha1(remote_id.encode("utf-8")).hexdigest()[:10]
        local_id = str(existing["id"]) if existing else f"florality_{cleaned_remote_id[:30]}_{remote_digest}"
        was_deleted = False
        if existing:
            was_deleted = local_id in await self.get_deleted_member_ids()
        if existing:
            try:
                raw = json.loads(existing.get("raw_json") or "{}")
            except json.JSONDecodeError:
                raw = {}
        else:
            raw = {
                "_id": local_id,
                "uid": local_id,
                "color": "",
                "avatarUuid": "",
                "pkId": "",
                "private": False,
                "buckets": [],
                "info": {},
            }
        raw.update(
            {
                "_id": raw.get("_id") or local_id,
                "uid": raw.get("uid") or local_id,
                "name": name,
                "pronouns": remote_member.get("pronouns") or "",
                "desc": remote_member.get("about") or raw.get("desc") or "",
                "avatarUrl": (
                    remote_member.get("_local_avatar_path")
                    or raw.get("avatarUrl")
                    or ""
                ),
                "archived": bool(remote_member.get("deletedAt")) or bool(raw.get("archived")),
                "archivedReason": (
                    "Deleted in Florality"
                    if remote_member.get("deletedAt")
                    else raw.get("archivedReason") or ""
                ),
                "florality": {
                    "_id": remote_id,
                    "displayName": remote_member.get("displayName") or "",
                    "avatar": remote_member.get("avatar") or "",
                    "avatarUrl": remote_member.get("avatarUrl") or "",
                    "createdAt": remote_member.get("createdAt") or "",
                    "updatedAt": remote_member.get("updatedAt") or "",
                    "deletedAt": remote_member.get("deletedAt") or "",
                },
            }
        )
        values = {
            "name": name,
            "pronouns": str(remote_member.get("pronouns") or ""),
            "description": str(remote_member.get("about") or ""),
            "avatar_url": str(
                remote_member.get("_local_avatar_path")
                or (existing.get("avatar_url") if existing else "")
                or ""
            ),
            "is_archived": 1 if (remote_member.get("deletedAt") or (existing and existing.get("is_archived"))) else 0,
            "archived_reason": (
                "Deleted in Florality"
                if remote_member.get("deletedAt")
                else str(existing.get("archived_reason") or "") if existing else ""
            ),
            "raw_json": _json(raw),
        }

        action = "created"
        if existing:
            comparable = {
                "name": existing.get("name") or "",
                "pronouns": existing.get("pronouns") or "",
                "description": existing.get("description") or "",
                "avatar_url": existing.get("avatar_url") or "",
                "is_archived": 1 if existing.get("is_archived") else 0,
                "archived_reason": existing.get("archived_reason") or "",
            }
            action = "unchanged" if all(comparable[key] == values[key] for key in comparable) else "updated"
            if was_deleted and not remote_member.get("deletedAt"):
                action = "updated"

        async with self._connect() as db:
            if existing:
                await db.execute(
                    """
                    UPDATE members
                    SET name=?,
                        pronouns=?,
                        description=?,
                        avatar_url=?,
                        is_archived=?,
                        archived_reason=?,
                        raw_json=?
                    WHERE id=?
                    """,
                    (
                        values["name"],
                        values["pronouns"],
                        values["description"],
                        values["avatar_url"],
                        values["is_archived"],
                        values["archived_reason"],
                        values["raw_json"],
                        local_id,
                    ),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO members(
                        id, name, pronouns, description, color, avatar_url, avatar_uuid,
                        pk_id, is_private, is_archived, archived_reason, raw_json
                    )
                    VALUES (?, ?, ?, ?, '', ?, '', '', 0, ?, ?, ?)
                    """,
                    (
                        local_id,
                        values["name"],
                        values["pronouns"],
                        values["description"],
                        values["avatar_url"],
                        values["is_archived"],
                        values["archived_reason"],
                        values["raw_json"],
                    ),
                )
            await db.commit()

        await self.set_external_id("florality", "member", local_id, remote_id)
        if not remote_member.get("deletedAt"):
            await self.restore_member_from_deleted(local_id)
        member = await self.get_member_by_id(local_id)
        if member is None:
            raise RuntimeError("Imported Florality member was not found")
        return member, action

    async def update_member_avatar_url(self, member_id: str, avatar_url: str) -> bool:
        member = await self.get_member_by_id(member_id)
        if not member:
            return False
        try:
            raw = json.loads(member.get("raw_json") or "{}")
        except json.JSONDecodeError:
            raw = {}
        raw["avatarUrl"] = avatar_url
        async with self._connect() as db:
            await db.execute(
                "UPDATE members SET avatar_url=?, raw_json=? WHERE id=?",
                (avatar_url, _json(raw), member_id),
            )
            await db.commit()
        return True

    async def replace_front_members(
        self,
        member_ids: list[str],
        created_by: int | None,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> bool:
        ordered_ids = list(dict.fromkeys(member_ids))
        now = _now_ms()
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT member_id FROM front_state ORDER BY fronted_at ASC, member_id"
            )
            current_ids = [row["member_id"] for row in await cursor.fetchall()]
            if current_ids == ordered_ids:
                return False

            await db.execute("DELETE FROM front_state")
            for index, member_id in enumerate(ordered_ids):
                await db.execute(
                    "INSERT INTO front_state(member_id, fronted_at) VALUES (?, ?)",
                    (member_id, now + index),
                )
            await db.execute(
                """
                INSERT INTO events(event_type, member_id, created_by, created_at, details_json)
                VALUES (?, NULL, ?, ?, ?)
                """,
                (
                    event_type,
                    created_by,
                    now,
                    json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
            await db.commit()
            return True

    async def get_group_by_name(self, name: str, parent_id: str | None = None) -> dict[str, Any] | None:
        async with self._connect() as db:
            if parent_id is None:
                cursor = await db.execute(
                    """
                    SELECT *
                    FROM groups
                    WHERE name=? AND (parent_id IS NULL OR parent_id='' OR parent_id='root')
                    ORDER BY id
                    LIMIT 1
                    """,
                    (name,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT *
                    FROM groups
                    WHERE name=? AND parent_id=?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (name, parent_id),
                )
            return _row_to_dict(await cursor.fetchone())

    async def find_deleted_group(self) -> dict[str, Any] | None:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT * FROM groups ORDER BY parent_id IS NOT NULL, name COLLATE NOCASE"
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        for row in rows:
            if (row.get("name") or "").strip().casefold() in DELETED_GROUP_NAMES:
                return row
        return None

    async def count_all_members(self) -> int:
        deleted_ids = await self.get_deleted_member_ids()
        async with self._connect() as db:
            cursor = await db.execute("SELECT COUNT(*) AS c FROM members")
            row = await cursor.fetchone()
            return max(0, int(row["c"]) - len(deleted_ids))

    async def get_all_members_page(self, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        deleted_ids = await self.get_deleted_member_ids()
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT id, name, pronouns, is_private, is_archived
                FROM members
                ORDER BY name COLLATE NOCASE, id
                """,
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        rows = [row for row in rows if row["id"] not in deleted_ids]
        return rows[offset:offset + limit]

    async def get_group_by_id(self, group_id: str) -> dict[str, Any] | None:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM groups WHERE id=?", (group_id,))
            return _row_to_dict(await cursor.fetchone())

    async def get_all_groups(self) -> list[dict[str, Any]]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM groups ORDER BY id")
            return [dict(row) for row in await cursor.fetchall()]

    async def add_member_group_links(self, links: list[tuple[str, str]]) -> tuple[int, set[str]]:
        """Add category links without removing or replacing existing local data."""
        added_member_ids: set[str] = set()
        unique_links = list(dict.fromkeys(links))
        if not unique_links:
            return 0, added_member_ids

        added_count = 0
        async with self._connect() as db:
            for member_id, group_id in unique_links:
                cursor = await db.execute(
                    "INSERT OR IGNORE INTO member_groups(member_id, group_id) VALUES (?, ?)",
                    (member_id, group_id),
                )
                if cursor.rowcount > 0:
                    added_count += 1
                    added_member_ids.add(member_id)
            await db.commit()
        return added_count, added_member_ids

    async def get_missing_member_group_links(self, links: list[tuple[str, str]]) -> list[tuple[str, str]]:
        missing: list[tuple[str, str]] = []
        unique_links = list(dict.fromkeys(links))
        if not unique_links:
            return missing
        async with self._connect() as db:
            for member_id, group_id in unique_links:
                cursor = await db.execute(
                    "SELECT 1 FROM member_groups WHERE member_id=? AND group_id=? LIMIT 1",
                    (member_id, group_id),
                )
                if not await cursor.fetchone():
                    missing.append((member_id, group_id))
        return missing

    async def ensure_child_group(
        self,
        parent_id: str,
        name: str,
        emoji: str = "",
    ) -> dict[str, Any]:
        existing = await self.get_group_by_name(name, parent_id=parent_id)
        if existing:
            return existing

        group_id = f"local_group_{uuid.uuid4().hex}"
        raw = {
            "_id": group_id,
            "id": group_id,
            "name": name,
            "emoji": emoji,
            "parent": parent_id,
            "members": [],
            "private": False,
            "desc": "",
        }
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO groups(id, parent_id, name, emoji, description, is_private, raw_json)
                VALUES (?, ?, ?, ?, '', 0, ?)
                """,
                (group_id, parent_id, name, emoji, json.dumps(raw, ensure_ascii=False, sort_keys=True)),
            )
            await db.commit()

        group = await self.get_group_by_id(group_id)
        if group is None:
            raise RuntimeError("Created group was not found")
        return group

    async def ensure_deleted_group(self) -> dict[str, Any]:
        existing = await self.find_deleted_group()
        if existing:
            return existing

        group_id = f"local_group_{uuid.uuid4().hex}"
        raw = {
            "_id": group_id,
            "id": group_id,
            "name": "Deleted",
            "emoji": "🗑️",
            "parent": "root",
            "members": [],
            "private": False,
            "desc": "",
        }
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO groups(id, parent_id, name, emoji, description, is_private, raw_json)
                VALUES (?, 'root', 'Deleted', '🗑️', '', 0, ?)
                """,
                (group_id, json.dumps(raw, ensure_ascii=False, sort_keys=True)),
            )
            await db.commit()

        group = await self.get_group_by_id(group_id)
        if group is None:
            raise RuntimeError("Created deleted group was not found")
        return group

    async def get_deleted_member_ids(self) -> set[str]:
        deleted_group = await self.find_deleted_group()
        if not deleted_group:
            return set()
        group_ids = await self.get_descendant_group_ids(deleted_group["id"])
        if not group_ids:
            return set()
        placeholders = ",".join("?" for _ in group_ids)
        async with self._connect() as db:
            cursor = await db.execute(
                f"SELECT DISTINCT member_id FROM member_groups WHERE group_id IN ({placeholders})",
                group_ids,
            )
            return {row["member_id"] for row in await cursor.fetchall()}

    async def logical_delete_member(self, member_id: str, created_by: int | None) -> bool:
        member = await self.get_member_by_id(member_id)
        if not member:
            return False
        deleted_group = await self.ensure_deleted_group()
        now = _now_ms()
        async with self._connect() as db:
            await db.execute(
                "INSERT OR IGNORE INTO member_groups(member_id, group_id) VALUES (?, ?)",
                (member_id, deleted_group["id"]),
            )
            await db.execute("DELETE FROM front_state WHERE member_id=?", (member_id,))
            await db.execute(
                """
                INSERT INTO events(event_type, member_id, created_by, created_at, details_json)
                VALUES ('member_deleted', ?, ?, ?, NULL)
                """,
                (member_id, created_by, now),
            )
            await db.commit()
        return True

    async def restore_member_from_deleted(self, member_id: str, created_by: int | None = None) -> bool:
        deleted_group = await self.find_deleted_group()
        if not deleted_group:
            return False
        group_ids = await self.get_descendant_group_ids(deleted_group["id"])
        if not group_ids:
            return False

        placeholders = ",".join("?" for _ in group_ids)
        now = _now_ms()
        async with self._connect() as db:
            cursor = await db.execute(
                f"SELECT 1 FROM member_groups WHERE member_id=? AND group_id IN ({placeholders}) LIMIT 1",
                (member_id, *group_ids),
            )
            if not await cursor.fetchone():
                return False

            await db.execute(
                f"DELETE FROM member_groups WHERE member_id=? AND group_id IN ({placeholders})",
                (member_id, *group_ids),
            )
            await db.execute(
                """
                INSERT INTO events(event_type, member_id, created_by, created_at, details_json)
                VALUES ('member_restored', ?, ?, ?, NULL)
                """,
                (member_id, created_by, now),
            )
            await db.commit()
            return True

    async def ensure_future_year_groups(self, years_ahead: int = 10) -> list[dict[str, Any]]:
        root = await self.get_group_by_name("Years of birth")
        if not root:
            return []

        existing = await self.list_child_groups(root["id"], limit=1000)
        numeric_years: list[int] = []
        for group in existing:
            try:
                numeric_years.append(int(str(group.get("name") or "").strip()))
            except ValueError:
                continue

        current_year = time.localtime().tm_year
        existing_max = max(numeric_years) if numeric_years else current_year - 1
        target_max = current_year + years_ahead
        created: list[dict[str, Any]] = []
        for year in range(existing_max + 1, target_max + 1):
            created.append(await self.ensure_child_group(root["id"], str(year)))
        return created

    async def list_child_groups(
        self,
        parent_id: str | None,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        async with self._connect() as db:
            if parent_id:
                cursor = await db.execute(
                    """
                    SELECT *
                    FROM groups
                    WHERE parent_id=?
                    ORDER BY name COLLATE NOCASE, id
                    LIMIT ? OFFSET ?
                    """,
                    (parent_id, limit, offset),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT *
                    FROM groups
                    WHERE parent_id IS NULL OR parent_id='' OR parent_id='root'
                    ORDER BY name COLLATE NOCASE, id
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            return [dict(row) for row in await cursor.fetchall()]

    async def count_child_groups(self, parent_id: str | None) -> int:
        async with self._connect() as db:
            if parent_id:
                cursor = await db.execute(
                    "SELECT COUNT(*) AS c FROM groups WHERE parent_id=?",
                    (parent_id,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM groups
                    WHERE parent_id IS NULL OR parent_id='' OR parent_id='root'
                    """
                )
            row = await cursor.fetchone()
            return int(row["c"])

    async def _get_all_groups_map(self) -> dict[str, dict[str, Any]]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM groups")
            return {row["id"]: dict(row) for row in await cursor.fetchall()}

    def _group_display_name(self, group: dict[str, Any]) -> str:
        emoji = (group.get("emoji") or "").strip()
        name = group.get("name") or ""
        return f"{emoji} {name}".strip() if emoji else name

    async def get_group_path(self, group_id: str) -> str:
        all_groups = await self._get_all_groups_map()
        group = all_groups.get(group_id)
        if not group:
            return ""

        parts = [self._group_display_name(group)]
        parent_id = group.get("parent_id")
        guard = 0
        while parent_id and parent_id != "root" and parent_id in all_groups and guard < 50:
            parent = all_groups[parent_id]
            parts.append(self._group_display_name(parent))
            parent_id = parent.get("parent_id")
            guard += 1

        return " / ".join(reversed([part for part in parts if part]))

    async def get_descendant_group_ids(self, group_id: str) -> list[str]:
        all_groups = await self._get_all_groups_map()
        children: dict[str, list[str]] = {}
        for gid, group in all_groups.items():
            parent_id = group.get("parent_id")
            if parent_id:
                children.setdefault(parent_id, []).append(gid)

        result: list[str] = []
        stack = [group_id]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            result.append(current)
            stack.extend(children.get(current, []))
        return result

    async def count_members_for_group_tree(self, group_id: str) -> int:
        group_ids = await self.get_descendant_group_ids(group_id)
        if not group_ids:
            return 0
        placeholders = ",".join("?" for _ in group_ids)
        async with self._connect() as db:
            cursor = await db.execute(
                f"""
                SELECT COUNT(DISTINCT m.id) AS c
                FROM members m
                JOIN member_groups mg ON mg.member_id = m.id
                WHERE mg.group_id IN ({placeholders})
                """,
                group_ids,
            )
            row = await cursor.fetchone()
            return int(row["c"])

    async def get_members_for_group_tree(
        self,
        group_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        group_ids = await self.get_descendant_group_ids(group_id)
        if not group_ids:
            return []
        placeholders = ",".join("?" for _ in group_ids)
        async with self._connect() as db:
            cursor = await db.execute(
                f"""
                SELECT DISTINCT m.id, m.name, m.pronouns, m.is_private, m.is_archived
                FROM members m
                JOIN member_groups mg ON mg.member_id = m.id
                WHERE mg.group_id IN ({placeholders})
                ORDER BY m.name COLLATE NOCASE, m.id
                LIMIT ? OFFSET ?
                """,
                (*group_ids, limit, offset),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def get_categories_for_member(self, member_id: str) -> list[str]:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT g.*
                FROM member_groups mg
                JOIN groups g ON g.id = mg.group_id
                WHERE mg.member_id=?
                ORDER BY g.name COLLATE NOCASE
                """,
                (member_id,),
            )
            member_groups = [dict(row) for row in await cursor.fetchall()]

            cursor = await db.execute("SELECT * FROM groups")
            all_groups = {row["id"]: dict(row) for row in await cursor.fetchall()}

        def path_for(group: dict[str, Any]) -> str:
            parts = [self._group_display_name(group)]
            parent_id = group.get("parent_id")
            guard = 0
            while parent_id and parent_id != "root" and parent_id in all_groups and guard < 50:
                parent = all_groups[parent_id]
                parts.append(self._group_display_name(parent))
                parent_id = parent.get("parent_id")
                guard += 1
            return " / ".join(reversed([p for p in parts if p]))

        paths = sorted({path_for(group) for group in member_groups if group.get("name")})
        return paths

    async def get_category_values_for_member(self, member_id: str, root_name: str) -> list[str]:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT g.*
                FROM member_groups mg
                JOIN groups g ON g.id = mg.group_id
                WHERE mg.member_id=?
                """,
                (member_id,),
            )
            member_groups = [dict(row) for row in await cursor.fetchall()]

            cursor = await db.execute("SELECT * FROM groups")
            all_groups = {row["id"]: dict(row) for row in await cursor.fetchall()}

        values: set[str] = set()
        for group in member_groups:
            parts = [self._group_display_name(group)]
            parent_id = group.get("parent_id")
            root_found = False
            guard = 0
            while parent_id and parent_id != "root" and parent_id in all_groups and guard < 50:
                parent = all_groups[parent_id]
                if (parent.get("name") or "").casefold() == root_name.casefold():
                    root_found = True
                    break
                parts.append(self._group_display_name(parent))
                parent_id = parent.get("parent_id")
                guard += 1

            if root_found:
                values.add(" / ".join(reversed([part for part in parts if part])))

        return sorted(values)

    async def create_member(
        self,
        name: str,
        pronouns: str = "",
        description: str = "",
        group_ids: list[str] | None = None,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        member_id = f"local_{uuid.uuid4().hex}"
        now = _now_ms()
        group_ids = list(dict.fromkeys(group_ids or []))
        raw = {
            "_id": member_id,
            "uid": member_id,
            "name": name,
            "pronouns": pronouns,
            "desc": description,
            "color": "",
            "avatarUrl": "",
            "avatarUuid": "",
            "pkId": "",
            "private": False,
            "archived": False,
            "buckets": [],
            "info": {},
            "lastOperationTime": now,
        }

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO members(
                    id, name, pronouns, description, color, avatar_url, avatar_uuid,
                    pk_id, is_private, is_archived, archived_reason, raw_json
                )
                VALUES (?, ?, ?, ?, '', '', '', '', 0, 0, '', ?)
                """,
                (member_id, name, pronouns, description, json.dumps(raw, ensure_ascii=False, sort_keys=True)),
            )
            for group_id in group_ids:
                await db.execute(
                    "INSERT OR IGNORE INTO member_groups(member_id, group_id) VALUES (?, ?)",
                    (member_id, group_id),
                )
            await db.execute(
                """
                INSERT INTO events(event_type, member_id, created_by, created_at, details_json)
                VALUES ('member_created', ?, ?, ?, NULL)
                """,
                (member_id, created_by, now),
            )
            await db.commit()

        member = await self.get_member_by_id(member_id)
        if member is None:
            raise RuntimeError("Created member was not found")
        return member

    async def export_simply_plural_data(self) -> dict[str, Any]:
        async with self._connect() as db:
            members_cursor = await db.execute("SELECT raw_json FROM members ORDER BY name COLLATE NOCASE, id")
            member_rows = await members_cursor.fetchall()
            groups_cursor = await db.execute("SELECT id, raw_json FROM groups ORDER BY name COLLATE NOCASE, id")
            group_rows = await groups_cursor.fetchall()
            fields_cursor = await db.execute("SELECT raw_json FROM custom_fields ORDER BY name COLLATE NOCASE, id")
            field_rows = await fields_cursor.fetchall()
            links_cursor = await db.execute(
                "SELECT member_id, group_id FROM member_groups ORDER BY group_id, member_id"
            )
            links = await links_cursor.fetchall()

        members = [json.loads(row["raw_json"] or "{}") for row in member_rows]
        groups = []
        members_by_group: dict[str, list[str]] = {}
        for link in links:
            members_by_group.setdefault(link["group_id"], []).append(link["member_id"])

        for row in group_rows:
            group = json.loads(row["raw_json"] or "{}")
            group["members"] = members_by_group.get(row["id"], [])
            groups.append(group)

        return {
            "members": members,
            "groups": groups,
            "customFields": [json.loads(row["raw_json"] or "{}") for row in field_rows],
        }

    async def get_custom_fields_map(self) -> dict[str, str]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT id, name FROM custom_fields")
            rows = await cursor.fetchall()
            return {row["id"]: row["name"] for row in rows}

    async def replace_member_mentions(self, text: str) -> str:
        if not text:
            return text

        name_map = await self.get_member_name_map()

        def repl(match: re.Match[str]) -> str:
            member_id = match.group(1).strip()
            return name_map.get(member_id, member_id)

        return MENTION_RE.sub(repl, text)


repo = Repository()
