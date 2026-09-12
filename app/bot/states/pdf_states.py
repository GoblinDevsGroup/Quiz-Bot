from aiogram.fsm.state import State, StatesGroup


class PdfQuizStates(StatesGroup):
    waiting_for_pdf = State()
    choosing_question_count = State()
    choosing_difficulty = State()
    choosing_question_type = State()
    choosing_language = State()
    generating = State()
    previewing = State()
