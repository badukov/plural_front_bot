from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.access import is_admin_message
from app.broadcast import broadcast
from app.formatters import format_front_notification
from app.keyboards import (
    BTN_BLUR,
    BTN_DIRECTORY,
    BTN_FRONT,
    BTN_REMOVE_FRONT,
    directory_home_keyboard,
    front_members_keyboard,
    main_keyboard,
    member_button_items,
    members_choice_keyboard,
)
from app.repository import repo
from app.states import FrontSearchState


router = Router()


@router.message(lambda message: message.text == BTN_FRONT)
async def start_front_search(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        await message.answer(
            "Управление фронтом доступно только админам.",
            reply_markup=main_keyboard(False),
        )
        return

    await state.set_state(FrontSearchState.waiting_for_query)
    await message.answer("Введите имя или часть имени личности:")


@router.message(FrontSearchState.waiting_for_query)
async def process_front_search(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        await state.clear()
        await message.answer(
            "Управление фронтом доступно только админам.",
            reply_markup=main_keyboard(False),
        )
        return

    query = (message.text or "").strip()
    if query == BTN_DIRECTORY:
        await state.clear()
        await message.answer(
            "Справочник: выберите способ просмотра.",
            reply_markup=directory_home_keyboard(),
        )
        return

    if not query:
        await message.answer("Введите хотя бы часть имени.")
        return

    matches = await repo.search_members(query)
    if not matches:
        await message.answer("Ничего не найдено. Попробуйте другой кусок имени.")
        return

    await state.clear()
    await message.answer(
        "Выберите личность для постановки на фронт:",
        reply_markup=members_choice_keyboard("setfront", member_button_items(matches)),
    )


@router.message(lambda message: message.text == BTN_REMOVE_FRONT)
async def remove_front_start(message: Message) -> None:
    if not is_admin_message(message):
        await message.answer(
            "Управление фронтом доступно только админам.",
            reply_markup=main_keyboard(False),
        )
        return

    front_members = await repo.get_current_front_members()
    if not front_members:
        await message.answer("Сейчас: блюр. На фронте никого нет.")
        return

    await message.answer(
        "Кого снять с фронта?",
        reply_markup=front_members_keyboard(member_button_items(front_members)),
    )


@router.message(lambda message: message.text == BTN_BLUR)
async def set_blur(message: Message) -> None:
    if not is_admin_message(message):
        await message.answer(
            "Управление фронтом доступно только админам.",
            reply_markup=main_keyboard(False),
        )
        return

    await repo.clear_front(created_by=message.from_user.id if message.from_user else None)
    await broadcast(message.bot, await format_front_notification("Фронт очищен", []))
    await message.answer("Фронт очищен. Статус: блюр.", reply_markup=main_keyboard(True))
