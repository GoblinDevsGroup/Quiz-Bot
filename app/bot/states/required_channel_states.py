from aiogram.fsm.state import State, StatesGroup


class RequiredChannelStates(StatesGroup):
    awaiting_channel = State()
