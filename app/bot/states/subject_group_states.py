from aiogram.fsm.state import State, StatesGroup


class SubjectGroupStates(StatesGroup):
    awaiting_group_link = State()
