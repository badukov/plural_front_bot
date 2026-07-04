from aiogram.fsm.state import State, StatesGroup


class FrontSearchState(StatesGroup):
    waiting_for_query = State()


class DirectorySearchState(StatesGroup):
    waiting_for_query = State()


class AddMemberState(StatesGroup):
    waiting_for_name = State()
    waiting_for_pronouns = State()
    waiting_for_description = State()
    choosing_year = State()
    choosing_role = State()
    choosing_categories = State()
