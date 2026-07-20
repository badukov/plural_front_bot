import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from app.formatters import current_status_text
from app.i18n import normalize_lang, t
from app.repository import repo


logger = logging.getLogger(__name__)

MOSCOW_TIMEZONE = timezone(timedelta(hours=3), name="Europe/Moscow")
REMINDER_HOURS = tuple(range(6, 23, 2))
REMINDER_MINUTE = 30


def next_admin_front_reminder_at(now: datetime) -> datetime:
    """Return the next 06:30, 08:30, ..., 22:30 Moscow reminder."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=MOSCOW_TIMEZONE)
    local_now = now.astimezone(MOSCOW_TIMEZONE)
    for day_offset in (0, 1):
        reminder_date: date = local_now.date() + timedelta(days=day_offset)
        for hour in REMINDER_HOURS:
            candidate = datetime.combine(
                reminder_date,
                time(hour=hour, minute=REMINDER_MINUTE),
                tzinfo=MOSCOW_TIMEZONE,
            )
            if candidate > local_now:
                return candidate
    raise RuntimeError("Could not calculate the next admin front reminder")


async def send_admin_front_reminder(bot: Bot) -> None:
    admins = await repo.get_subscribed_admin_users()
    if not admins:
        logger.info("Admin front reminder skipped: no subscribed admins")
        return

    front_members = await repo.get_current_front_members()
    for admin in admins:
        telegram_user_id = int(admin["telegram_user_id"])
        lang = normalize_lang(admin.get("language_code"))
        text = t(
            "admin_front_check_reminder",
            lang,
            status=current_status_text(front_members, lang),
        )
        try:
            await bot.send_message(chat_id=admin["chat_id"], text=text)
        except TelegramForbiddenError:
            logger.info("Admin %s blocked bot. Marking unsubscribed.", telegram_user_id)
            await repo.set_user_subscribed(telegram_user_id, False)
        except TelegramAPIError as error:
            logger.warning("Could not send front reminder to admin %s: %s", telegram_user_id, error)
        except Exception:
            logger.exception("Unexpected front reminder error for admin %s", telegram_user_id)


async def run_admin_front_reminders(bot: Bot) -> None:
    logger.info("Admin front reminders started for 06:30-22:30 Europe/Moscow every two hours")
    while True:
        now = datetime.now(MOSCOW_TIMEZONE)
        next_reminder = next_admin_front_reminder_at(now)
        delay = max(1.0, (next_reminder - now).total_seconds())
        await asyncio.sleep(delay)
        await send_admin_front_reminder(bot)

