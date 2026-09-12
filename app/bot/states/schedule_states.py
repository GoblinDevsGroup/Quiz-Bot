from aiogram.fsm.state import State, StatesGroup


class ScheduleStates(StatesGroup):
    awaiting_datetime = State()
