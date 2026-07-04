import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{30,}$")


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            raise ValueError(f"ADMIN_IDS contains non-numeric id: {part!r}") from None
    return ids


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    database_path: Path
    sp_export_path: Path
    auto_import_on_start: bool
    public_show_private: bool
    public_show_archived: bool
    search_limit: int


settings = Settings(
    bot_token=os.getenv("BOT_TOKEN", "").strip(),
    admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
    database_path=Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3")),
    sp_export_path=Path(os.getenv("SP_EXPORT_PATH", "data/simply_plural_export.json")),
    auto_import_on_start=_bool("AUTO_IMPORT_ON_START", False),
    public_show_private=_bool("PUBLIC_SHOW_PRIVATE", True),
    public_show_archived=_bool("PUBLIC_SHOW_ARCHIVED", True),
    search_limit=int(os.getenv("SEARCH_LIMIT", "12")),
)

if not settings.bot_token:
    raise RuntimeError(
        "BOT_TOKEN is empty. Copy .env.example to .env and paste token from @BotFather."
    )

if not BOT_TOKEN_RE.match(settings.bot_token):
    raise RuntimeError(
        "BOT_TOKEN has invalid format. Paste a Telegram bot token from @BotFather into .env."
    )
