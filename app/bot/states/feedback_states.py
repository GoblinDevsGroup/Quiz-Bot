from aiogram.fsm.state import State, StatesGroup


class FeedbackStates(StatesGroup):
    awaiting_text = State()
