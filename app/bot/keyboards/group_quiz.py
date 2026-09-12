from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import GroupReadyCB, GroupStopCB
from app.i18n import Translator


def group_ready_keyboard(locale: str, session_id: str, ready_count: int) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    label = _("group_ready_button")
    if ready_count:
        label = f"{label} ({ready_count})"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=GroupReadyCB(session_id=session_id).pack())]]
    )


def group_stop_keyboard(locale: str, session_id: str) -> InlineKeyboardMarkup:
    """Attached to each question's poll message while a group quiz is
    running — pressing it is restricted to chat admins/creator (checked in
    the handler, since Telegram polls carry no per-user button visibility)."""
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("group_stop_button"), callback_data=GroupStopCB(session_id=session_id).pack())]]
    )
