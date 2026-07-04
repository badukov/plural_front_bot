from aiogram import Router
from aiogram.types import CallbackQuery

from app.access import is_admin_callback
from app.broadcast import broadcast
from app.formatters import current_status_text, split_long_message
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
    await callback.answer("Отменено")
    if callback.message:
        await callback.message.edit_text("Отменено.")


@router.callback_query(lambda callback: callback.data and callback.data.startswith("setfront:"))
async def set_front_callback(callback: CallbackQuery) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    member_id = callback.data.split(":", 1)[1]
    member = await repo.get_member_by_id(member_id)
    if not member:
        await callback.answer("Личность не найдена", show_alert=True)
        return

    added = await repo.add_to_front(
        member_id=member_id,
        created_by=callback.from_user.id if callback.from_user else None,
    )

    front_members = await repo.get_current_front_members()
    status = current_status_text(front_members)

    if added:
        await broadcast(callback.bot, status)
        answer_text = f"Поставлено на фронт: {member['name']}\n{status}"
    else:
        answer_text = f"{member['name']} уже на фронте.\n{status}"

    await callback.answer("Готово")
    await _show_callback_result(callback, answer_text)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("rmfront:"))
async def remove_front_callback(callback: CallbackQuery) -> None:
    if not is_admin_callback(callback):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    member_id = callback.data.split(":", 1)[1]
    member = await repo.get_member_by_id(member_id)
    if not member:
        await callback.answer("Личность не найдена", show_alert=True)
        return

    removed = await repo.remove_from_front(
        member_id=member_id,
        created_by=callback.from_user.id if callback.from_user else None,
    )

    front_members = await repo.get_current_front_members()
    status = current_status_text(front_members)

    if removed:
        text = f"{member['name']} снят с фронта\n{status}"
        await broadcast(callback.bot, text)
    else:
        text = f"{member['name']} сейчас не на фронте.\n{status}"

    await callback.answer("Готово")
    await _show_callback_result(callback, text)
