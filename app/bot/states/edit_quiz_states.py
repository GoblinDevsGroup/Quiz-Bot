from aiogram.fsm.state import State, StatesGroup


class EditQuizStates(StatesGroup):
    awaiting_title = State()
    awaiting_description = State()
    awaiting_time_limit = State()
    awaiting_shuffle = State()
    awaiting_new_question_poll = State()
    awaiting_new_question_image = State()
