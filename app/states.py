from aiogram.fsm.state import State, StatesGroup


class FrontSearchState(StatesGroup):
    waiting_for_query = State()


class DirectorySearchState(StatesGroup):
    waiting_for_query = State()
