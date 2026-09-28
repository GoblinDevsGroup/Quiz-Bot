from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import MenuCB, PdfSettingCB
from app.i18n import Translator


def question_count_keyboard(locale: str, max_count: int) -> InlineKeyboardMarkup:
    """Presets that fit the document, plus an 'all' button for the full amount."""
    _ = Translator(locale)
    presets = [c for c in (10, 20, 30, 50, 100) if c < max_count]
    rows = []
    for i in range(0, len(presets), 3):
        rows.append(
            [
                InlineKeyboardButton(text=str(c), callback_data=PdfSettingCB(field="count", value=str(c)).pack())
                for c in presets[i : i + 3]
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_("count_all_button", n=max_count),
                callback_data=PdfSettingCB(field="count", value="all").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
