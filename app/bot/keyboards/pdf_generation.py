from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import MenuCB, PdfSettingCB
from app.i18n import Translator


def question_count_keyboard() -> InlineKeyboardMarkup:
    counts = ["10", "20", "30", "50"]
    row = [
        InlineKeyboardButton(text=c, callback_data=PdfSettingCB(field="count", value=c).pack())
        for c in counts
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def difficulty_keyboard() -> InlineKeyboardMarkup:
    options = [("Easy", "easy"), ("Medium", "medium"), ("Hard", "hard"), ("Mixed", "mixed")]
    row = [
        InlineKeyboardButton(text=label, callback_data=PdfSettingCB(field="difficulty", value=value).pack())
        for label, value in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def question_type_keyboard() -> InlineKeyboardMarkup:
    options = [
        ("Multiple Choice", "multiple_choice"),
        ("True/False", "true_false"),
        ("Mixed", "mixed"),
    ]
    row = [
        InlineKeyboardButton(text=label, callback_data=PdfSettingCB(field="qtype", value=value).pack())
        for label, value in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def pdf_language_keyboard() -> InlineKeyboardMarkup:
    options = [
        ("🇺🇿 Uzbek", "uz"),
        ("🇷🇺 Русский", "ru"),
        ("🇬🇧 English", "en"),
        ("Auto-detect", "auto"),
    ]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=PdfSettingCB(field="language", value=value).pack())]
        for label, value in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def generate_confirm_keyboard(locale: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("generate_button"), callback_data=PdfSettingCB(field="go", value="go").pack())],
            [InlineKeyboardButton(text=_("cancel"), callback_data=MenuCB(action="main").pack())],
        ]
    )


def preview_keyboard(locale: str, quiz_id: str) -> InlineKeyboardMarkup:
    from app.bot.keyboards.callback_data import QuizActionCB

    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("start_test_button"), callback_data=QuizActionCB(action="preview_test", quiz_id=quiz_id).pack())],
            [
                InlineKeyboardButton(text=_("regenerate_button"), callback_data=QuizActionCB(action="regenerate", quiz_id=quiz_id).pack()),
                InlineKeyboardButton(text=_("save_button"), callback_data=QuizActionCB(action="save", quiz_id=quiz_id).pack()),
            ],
            [InlineKeyboardButton(text=_("discard_button"), callback_data=QuizActionCB(action="discard", quiz_id=quiz_id).pack())],
        ]
    )
