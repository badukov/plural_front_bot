from aiogram import Router
from aiogram.types import CallbackQuery

from app.access import is_admin_callback
from app.broadcast import broadcast_by_language
from app.florality import sync_florality_front
from app.formatters import current_status_text, format_front_notification, split_long_message
from app.i18n import lang_from_callback, t
from app.repository import repo


router = Router()


async def _show_callback_result(callback: CallbackQuery, text: str) -> None:
    if not callback.message:
        return

    chunks = split_long_message(text)
    await callback.message.edit_text(chunks[0])
    for chunk in chunks[1:]:
        await callback.message.answer(chunk)


@router.callback_query(lambda callback: callback.data == "cancel")
async def cancel(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    await callback.answer(t("cancelled_answer", lang))
    if callback.message:
        await callback.message.edit_text(t("cancelled", lang))


@router.callback_query(lambda callback: callback.data and callback.data.startswith("setfront:"))
async def set_front_callback(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    member_id = callback.data.split(":", 1)[1]
    member = await repo.get_member_by_id(member_id)
    if not member:
        await callback.answer(t("member_not_found", lang), show_alert=True)
        return

    added = await repo.add_to_front(
        member_id=member_id,
        created_by=callback.from_user.id if callback.from_user else None,
    )

    front_members = await repo.get_current_front_members()
    status = current_status_text(front_members, lang)

    if added:
        await repo.record_current_front_history("front_added", callback.from_user.id if callback.from_user else None)
        await sync_florality_front(front_members)
        await broadcast_by_language(
            callback.bot,
            lambda user_lang: format_front_notification(
                t("front_added_event", user_lang, name=member["name"]),
                front_members,
                user_lang,
            ),
        )
        answer_text = t("front_added", lang, name=member["name"], status=status)
    else:
        answer_text = t("already_front", lang, name=member["name"], status=status)

    await callback.answer(t("ready", lang))
    await _show_callback_result(callback, answer_text)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("rmfront:"))
async def remove_front_callback(callback: CallbackQuery) -> None:
    lang = lang_from_callback(callback)
    if not is_admin_callback(callback):
        await callback.answer(t("not_enough_rights", lang), show_alert=True)
        return

    member_id = callback.data.split(":", 1)[1]
    member = await repo.get_member_by_id(member_id)
    if not member:
        await callback.answer(t("member_not_found", lang), show_alert=True)
        return

    removed = await repo.remove_from_front(
        member_id=member_id,
        created_by=callback.from_user.id if callback.from_user else None,
    )

    front_members = await repo.get_current_front_members()
    status = current_status_text(front_members, lang)

    if removed:
        text = t("front_removed", lang, name=member["name"], status=status)
        await repo.record_current_front_history("front_removed", callback.from_user.id if callback.from_user else None)
        await sync_florality_front(front_members)
        await broadcast_by_language(
            callback.bot,
            lambda user_lang: format_front_notification(
                t("front_removed_event", user_lang, name=member["name"]),
                front_members,
                user_lang,
            ),
        )
    else:
        text = t("not_in_front", lang, name=member["name"], status=status)

    await callback.answer(t("ready", lang))
    await _show_callback_result(callback, text)
