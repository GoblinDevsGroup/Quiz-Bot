from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import MenuCB, MyQuizzesCB, QuizActionCB
from app.database.models import Quiz
from app.i18n import Translator


def my_quiz_card_keyboard(locale: str, quiz: Quiz) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    qid = str(quiz.id)
    rows = [
        [
            InlineKeyboardButton(text=_("start_quiz_button"), callback_data=QuizActionCB(action="start", quiz_id=qid).pack()),
            InlineKeyboardButton(text=_("edit_button"), callback_data=QuizActionCB(action="edit", quiz_id=qid).pack()),
        ],
        [
            InlineKeyboardButton(text=_("results_button"), callback_data=QuizActionCB(action="results", quiz_id=qid).pack()),
            InlineKeyboardButton(text=_("share_button"), switch_inline_query=qid),
        ],
    ]
    if quiz.status == "draft":
        rows.append([InlineKeyboardButton(text=_("publish_button"), callback_data=QuizActionCB(action="publish", quiz_id=qid).pack())])
    rows.append([InlineKeyboardButton(text=_("delete_button"), callback_data=QuizActionCB(action="delete_confirm", quiz_id=qid).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_quizzes_tabs_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Draft", callback_data=MyQuizzesCB(action="list", status="draft", page=1).pack()),
                InlineKeyboardButton(text="⏳ Kutilmoqda", callback_data=MyQuizzesCB(action="list", status="pending", page=1).pack()),
                InlineKeyboardButton(text="🌍 Published", callback_data=MyQuizzesCB(action="list", status="published", page=1).pack()),
                InlineKeyboardButton(text="📦 Archived", callback_data=MyQuizzesCB(action="list", status="archived", page=1).pack()),
            ],
            [InlineKeyboardButton(text=Translator(locale)("main_menu"), callback_data=MenuCB(action="main").pack())],
        ]
    )


def my_quizzes_pagination_keyboard(locale: str, status: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=MyQuizzesCB(action="list", status=status, page=page - 1).pack()))
    buttons.append(InlineKeyboardButton(text=_("page_indicator", page=page, total=max(total_pages, 1)), callback_data="noop"))
    if page < total_pages:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=MyQuizzesCB(action="list", status=status, page=page + 1).pack()))
    return InlineKeyboardMarkup(inline_keyboard=[buttons, [InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())]])
