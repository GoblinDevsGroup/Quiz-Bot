from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    awaiting_ban_id = State()
    awaiting_unban_id = State()
    awaiting_finduser_query = State()
    awaiting_broadcast_text = State()
    awaiting_delete_quiz_id = State()


class ModerationStates(StatesGroup):
    awaiting_reject_reason = State()
