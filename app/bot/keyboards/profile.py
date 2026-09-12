from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import MenuCB
from app.i18n import Translator


def profile_keyboard(locale: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("menu_my_quizzes"), callback_data=MenuCB(action="my_quizzes").pack())],
            [InlineKeyboardButton(text="🏆 Leaderboard", callback_data=MenuCB(action="leaderboard").pack())],
            [InlineKeyboardButton(text=_("menu_language"), callback_data=MenuCB(action="language").pack())],
            [InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())],
        ]
    )


def create_method_keyboard(locale: str) -> InlineKeyboardMarkup:
    from app.bot.keyboards.callback_data import CreateMethodCB
    from app.core.config import FEATURE_PDF_AI_CREATION_ENABLED

    _ = Translator(locale)
    rows = []
    if FEATURE_PDF_AI_CREATION_ENABLED:
        rows.append([InlineKeyboardButton(text=_("create_pdf"), callback_data=CreateMethodCB(method="pdf").pack())])
    rows.append([InlineKeyboardButton(text=_("create_manual"), callback_data=CreateMethodCB(method="manual").pack())])
    if FEATURE_PDF_AI_CREATION_ENABLED:
        rows.append([InlineKeyboardButton(text=_("create_ai"), callback_data=CreateMethodCB(method="ai").pack())])
    rows.append([InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
