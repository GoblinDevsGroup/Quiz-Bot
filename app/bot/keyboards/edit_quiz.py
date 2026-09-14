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
                    callback_data=EditQuizCB(action="del_q_list", quiz_id=quiz_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_("edit_reorder_button"),
                    callback_data=EditQuizCB(action="reorder", quiz_id=quiz_id).pack(),
                )
            ],
            [InlineKeyboardButton(text=_("back"), callback_data=EditQuizCB(action="back", quiz_id=quiz_id).pack())],
        ]
    )


def delete_question_list_keyboard(locale: str, quiz: Quiz) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    questions = sorted(quiz.questions, key=lambda q: q.order_index)
    rows = []
    for idx, question in enumerate(questions):
        label = question.text[:40] + ("…" if len(question.text) > 40 else "")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{idx + 1}. {label}",
                    callback_data=EditQuizCB(action="del_q", quiz_id=str(quiz.id), idx=idx).pack(),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=_("back"), callback_data=EditQuizCB(action="menu", quiz_id=str(quiz.id)).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reorder_question_list_keyboard(locale: str, quiz: Quiz) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    questions = sorted(quiz.questions, key=lambda q: q.order_index)
    rows = []
    for idx, question in enumerate(questions):
        label = question.text[:35] + ("…" if len(question.text) > 35 else "")
        row = [InlineKeyboardButton(text=f"{idx + 1}. {label}", callback_data=EditQuizCB(action="noop", quiz_id=str(quiz.id)).pack())]
        buttons = []
        if idx > 0:
            buttons.append(
                InlineKeyboardButton(
                    text="⬆️",
                    callback_data=EditQuizCB(action="move_up", quiz_id=str(quiz.id), idx=idx).pack(),
                )
            )
        if idx < len(questions) - 1:
            buttons.append(
                InlineKeyboardButton(
                    text="⬇️",
                    callback_data=EditQuizCB(action="move_down", quiz_id=str(quiz.id), idx=idx).pack(),
                )
            )
        buttons.append(
            InlineKeyboardButton(
                text="🗑",
                callback_data=EditQuizCB(action="del_q_reorder", quiz_id=str(quiz.id), idx=idx).pack(),
            )
        )
        rows.append(row)
        if buttons:
            rows.append(buttons)
    rows.append([InlineKeyboardButton(text=_("back"), callback_data=EditQuizCB(action="menu", quiz_id=str(quiz.id)).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
