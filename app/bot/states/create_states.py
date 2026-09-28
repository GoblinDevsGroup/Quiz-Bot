from aiogram.fsm.state import State, StatesGroup


class CreateQuizStates(StatesGroup):
    """Shared first step for every quiz-creation method (PDF, manual, AI
    prompt): subject and grade are picked once here, then the method-specific
    flow picks up from state data instead of asking again."""

    choosing_subject = State()
    choosing_grade = State()
