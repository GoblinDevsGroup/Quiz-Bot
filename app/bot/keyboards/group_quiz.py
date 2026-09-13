from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import GroupReadyCB
from app.i18n import Translator


def group_ready_keyboard(locale: str, session_id: str, ready_count: int) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    label = _("group_ready_button")
    if ready_count:
        label = f"{label} ({ready_count})"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=GroupReadyCB(session_id=session_id).pack())]]
    )
