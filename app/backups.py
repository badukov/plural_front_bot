import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import settings


def _safe_reason(reason: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in reason).strip("_")


def _backup_database_sync(db_path: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


async def create_database_backup(reason: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_reason = _safe_reason(reason) or "backup"
    backup_dir = settings.database_path.parent / "backups"
    backup_path = backup_dir / f"{settings.database_path.stem}_{timestamp}_{safe_reason}{settings.database_path.suffix}"
    await asyncio.to_thread(_backup_database_sync, settings.database_path, backup_path)
    return backup_path
