from aiogram.fsm.state import State, StatesGroup


class BrowseStates(StatesGroup):
    searching = State()
    awaiting_page_number = State()


class QuizTakingStates(StatesGroup):
    in_progress = State()


class ReportStates(StatesGroup):
    choosing_reason = State()
    entering_comment = State()
