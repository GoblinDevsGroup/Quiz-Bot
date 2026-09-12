from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import MenuCB, PhotoAnswerCB
from app.bot.keyboards.common import OPTION_LETTERS
from app.i18n import Translator


def photo_question_keyboard(attempt_id: str, option_texts: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for idx, text in enumerate(option_texts):
        letter = OPTION_LETTERS[idx] if idx < len(OPTION_LETTERS) else str(idx + 1)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{letter}) {text[:60]}",
                    callback_data=PhotoAnswerCB(attempt_id=attempt_id, option_index=idx).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def result_keyboard(locale: str, quiz_id: str) -> InlineKeyboardMarkup:
    from app.bot.keyboards.callback_data import QuizActionCB

    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("retry_button"), callback_data=QuizActionCB(action="start", quiz_id=quiz_id).pack()),
                InlineKeyboardButton(text=_("share_button"), switch_inline_query=quiz_id),
            ],
            [InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())],
        ]
    )
