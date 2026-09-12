from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import EditQuizCB
from app.database.models import Quiz
from app.i18n import Translator


def edit_menu_keyboard(locale: str, quiz_id: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("edit_title_button"), callback_data=EditQuizCB(action="title", quiz_id=quiz_id).pack())],
            [InlineKeyboardButton(text=_("edit_description_button"), callback_data=EditQuizCB(action="description", quiz_id=quiz_id).pack())],
            [InlineKeyboardButton(text=_("edit_time_limit_button"), callback_data=EditQuizCB(action="time_limit", quiz_id=quiz_id).pack())],
            [InlineKeyboardButton(text=_("edit_shuffle_button"), callback_data=EditQuizCB(action="shuffle", quiz_id=quiz_id).pack())],
            [InlineKeyboardButton(text=_("edit_add_question_button"), callback_data=EditQuizCB(action="add_question", quiz_id=quiz_id).pack())],
            [
                InlineKeyboardButton(
                    text=_("edit_delete_question_button"),
                    callback_data=EditQuizCB(action="delete_question_list", quiz_id=quiz_id).pack(),
                )
            ],
            [InlineKeyboardButton(text=_("back"), callback_data=EditQuizCB(action="back", quiz_id=quiz_id).pack())],
        ]
    )


def delete_question_list_keyboard(locale: str, quiz: Quiz) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    rows = []
    for idx, question in enumerate(quiz.questions, start=1):
        label = question.text[:40] + ("…" if len(question.text) > 40 else "")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{idx}. {label}",
                    callback_data=EditQuizCB(action="delete_question", quiz_id=str(quiz.id), question_id=str(question.id)).pack(),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=_("back"), callback_data=EditQuizCB(action="menu", quiz_id=str(quiz.id)).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
