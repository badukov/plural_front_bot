import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database import init_db
from app.florality import run_florality_front_pull, run_florality_history_pull
from app.import_sp import import_simply_plural_export
from app.repository import repo
from app.reminders import run_admin_front_reminders
from app.user_context import UserLanguageMiddleware
from app.handlers import (
    start,
    info,
    notifications,
    history,
    admin_front,
    admin_add,
    directory,
    callbacks,
    language,
    global_search,
)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    if not settings.admin_ids:
        logging.warning("ADMIN_IDS is empty: member management and front controls will be unavailable")

    await init_db(settings.database_path)
    await repo.sync_admin_flags(settings.admin_ids)
    await repo.archive_front_history()

    if settings.auto_import_on_start:
        if settings.sp_export_path.exists():
            result = await import_simply_plural_export(
                export_path=settings.sp_export_path,
                db_path=settings.database_path,
            )
            logging.info(
                "Simply Plural import: members=%s groups=%s links=%s",
                result.members_imported,
                result.groups_imported,
                result.member_group_links_imported,
            )
        else:
            logging.warning("AUTO_IMPORT_ON_START=true, but export file does not exist: %s", settings.sp_export_path)

    if await repo.count_front_history() == 0:
        await repo.record_current_front_history("initial", created_by=None)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    language_middleware = UserLanguageMiddleware()
    dp.message.middleware(language_middleware)
    dp.callback_query.middleware(language_middleware)

    dp.include_router(start.router)
    dp.include_router(language.router)
    dp.include_router(info.router)
    dp.include_router(notifications.router)
    dp.include_router(history.router)
    dp.include_router(admin_front.router)
    dp.include_router(admin_add.router)
    dp.include_router(directory.router)
    dp.include_router(callbacks.router)
    dp.include_router(global_search.router)

    logging.info("Bot started")
    florality_pull_task = asyncio.create_task(run_florality_front_pull(bot))
    florality_history_task = asyncio.create_task(run_florality_history_pull())
    admin_reminder_task = asyncio.create_task(run_admin_front_reminders(bot))
    try:
        await dp.start_polling(bot)
    finally:
        for task in (florality_pull_task, florality_history_task, admin_reminder_task):
            task.cancel()
        for task in (florality_pull_task, florality_history_task, admin_reminder_task):
            with suppress(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    asyncio.run(main())
