from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot.keyboards.callback_data import MenuCB
from app.i18n import Translator


def main_menu_keyboard(locale: str) -> ReplyKeyboardMarkup:
    """Persistent reply keyboard shown after /start — replaces the on-screen
    keyboard rather than attaching inline buttons to a single message."""
    _ = Translator(locale)
    rows = [
        [KeyboardButton(text=_("menu_quiz_bank"))],
        [KeyboardButton(text=_("menu_create_quiz")), KeyboardButton(text=_("menu_my_quizzes"))],
        [KeyboardButton(text=_("menu_profile")), KeyboardButton(text=_("menu_help"))],
        [KeyboardButton(text=_("menu_language"))],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def back_to_main_keyboard(locale: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())]]
    )
