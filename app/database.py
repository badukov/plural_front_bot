from pathlib import Path

import aiosqlite


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    pronouns TEXT,
    description TEXT,
    color TEXT,
    avatar_url TEXT,
    avatar_uuid TEXT,
    pk_id TEXT,
    is_private INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    archived_reason TEXT,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    name TEXT NOT NULL,
    emoji TEXT,
    description TEXT,
    is_private INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS member_groups (
    member_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    PRIMARY KEY (member_id, group_id)
);

CREATE TABLE IF NOT EXISTS custom_fields (
    id TEXT PRIMARY KEY,
    oid TEXT,
    name TEXT NOT NULL,
    type INTEGER,
    support_markdown INTEGER,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    telegram_user_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    username TEXT,
    first_name TEXT,
    language_code TEXT,
    language_override TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    subscribed INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS front_state (
    member_id TEXT PRIMARY KEY,
    fronted_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    member_id TEXT,
    created_by INTEGER,
    created_at INTEGER NOT NULL,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS external_ids (
    provider TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    local_id TEXT NOT NULL,
    remote_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (provider, entity_type, local_id)
);

CREATE TABLE IF NOT EXISTS front_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    created_by INTEGER,
    created_at INTEGER NOT NULL,
    snapshot_json_z TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS florality_front_sessions (
    session_id TEXT PRIMARY KEY,
    remote_member_id TEXT NOT NULL,
    local_member_id TEXT,
    member_name TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    edited_at INTEGER,
    edited_manually INTEGER NOT NULL DEFAULT 0,
    synced_at INTEGER NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS florality_front_sessions_archive (
    session_id TEXT PRIMARY KEY,
    remote_member_id TEXT NOT NULL,
    local_member_id TEXT,
    member_name TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    edited_at INTEGER,
    edited_manually INTEGER NOT NULL DEFAULT 0,
    synced_at INTEGER NOT NULL,
    archived_at INTEGER NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_members_name ON members(name);
CREATE INDEX IF NOT EXISTS idx_member_groups_member ON member_groups(member_id);
CREATE INDEX IF NOT EXISTS idx_member_groups_group ON member_groups(group_id);
CREATE INDEX IF NOT EXISTS idx_front_state_fronted_at ON front_state(fronted_at);
CREATE INDEX IF NOT EXISTS idx_external_ids_remote ON external_ids(provider, entity_type, remote_id);
CREATE INDEX IF NOT EXISTS idx_front_history_created_at ON front_history(created_at);
CREATE INDEX IF NOT EXISTS idx_florality_sessions_started ON florality_front_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_florality_sessions_ended ON florality_front_sessions(ended_at);
CREATE INDEX IF NOT EXISTS idx_florality_sessions_archive_started ON florality_front_sessions_archive(started_at);
"""


async def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "language_code" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN language_code TEXT")
        if "language_override" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN language_override TEXT")
        await db.commit()
