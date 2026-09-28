from aiogram.fsm.state import State, StatesGroup


class GenerationReviewStates(StatesGroup):
    """After an AI-generated quiz (from PDF or a text prompt) is previewed
    and the creator taps "Saqlash", these two settings are asked the same
    way the manual-creation flow asks them, before the quiz is finalized."""

    choosing_time_limit = State()
    choosing_shuffle = State()
