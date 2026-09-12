from aiogram.fsm.state import State, StatesGroup


class ManualQuizStates(StatesGroup):
    entering_title = State()
    entering_description = State()
    collecting_questions = State()
    awaiting_question_image = State()
    choosing_time_limit = State()
    choosing_shuffle = State()
