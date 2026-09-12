from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import ConfirmCB, LanguageCB, MenuCB
from app.i18n import Translator

OPTION_LETTERS = ["A", "B", "C", "D", "E", "F"]


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇺🇿 Oʻzbekcha", callback_data=LanguageCB(code="uz").pack())],
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data=LanguageCB(code="ru").pack())],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data=LanguageCB(code="en").pack())],
        ]
    )


def cancel_keyboard(locale: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("cancel"), callback_data=MenuCB(action="main").pack())]]
    )


def back_cancel_keyboard(locale: str, back_action: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("back"), callback_data=MenuCB(action=back_action).pack()),
                InlineKeyboardButton(text=_("cancel"), callback_data=MenuCB(action="main").pack()),
            ]
        ]
    )


def confirm_keyboard(locale: str, action: str, value: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_("confirm_yes"), callback_data=ConfirmCB(action=action, value=value).pack()
                ),
                InlineKeyboardButton(
                    text=_("confirm_no"), callback_data=MenuCB(action="main").pack()
                ),
            ]
        ]
    )
