import uuid

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import MenuCB, QuizActionCB, QuizBankCB
from app.database.models import Quiz
from app.i18n import Translator


def quiz_bank_card_keyboard(locale: str, quiz: Quiz, page: int) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_("start_quiz_button"),
                    callback_data=QuizActionCB(action="start", quiz_id=str(quiz.id)).pack(),
                ),
                InlineKeyboardButton(
                    text=_("details_button"),
                    callback_data=QuizActionCB(action="details", quiz_id=str(quiz.id)).pack(),
                ),
            ]
        ]
    )


def pagination_keyboard(
    locale: str, page: int, total_pages: int, base_action: str = "list", sort: str = "newest"
) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    buttons = []
    if page > 1:
        buttons.append(
            InlineKeyboardButton(text="⬅️", callback_data=QuizBankCB(action=base_action, page=page - 1, sort=sort).pack())
        )
    buttons.append(
        InlineKeyboardButton(
            text=_("page_indicator", page=page, total=max(total_pages, 1)),
            callback_data=QuizBankCB(action="goto_page", page=total_pages, sort=sort).pack(),
        )
    )
    if page < total_pages:
        buttons.append(
            InlineKeyboardButton(text="➡️", callback_data=QuizBankCB(action=base_action, page=page + 1, sort=sort).pack())
        )

    rows = [buttons]
    rows.append(
        [
            InlineKeyboardButton(text=_("search_button"), callback_data=QuizBankCB(action="search").pack()),
            InlineKeyboardButton(text=_("filters_button"), callback_data=QuizBankCB(action="filters", sort=sort).pack()),
        ]
    )
    rows.append([InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


SORT_OPTIONS = ["newest", "popular", "rating"]


def filters_keyboard(locale: str, current_sort: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    rows = []
    for sort in SORT_OPTIONS:
        label = _(f"sort_{sort}_label")
        if sort == current_sort:
            label = f"✅ {label}"
        rows.append([InlineKeyboardButton(text=label, callback_data=QuizBankCB(action="list", page=1, sort=sort).pack())])
    rows.append([InlineKeyboardButton(text=_("back"), callback_data=QuizBankCB(action="list", page=1, sort=current_sort).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quiz_detail_keyboard(locale: str, quiz_id: str, bot_username: str) -> InlineKeyboardMarkup:
    from app.bot.keyboards.callback_data import ReportCB

    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("start_quiz_button"), callback_data=QuizActionCB(action="start", quiz_id=quiz_id).pack())],
            [InlineKeyboardButton(text=_("start_in_group_button"), url=f"https://t.me/{bot_username}?startgroup=quiz_{quiz_id}")],
            [InlineKeyboardButton(text=_("schedule_in_group_button"), url=f"https://t.me/{bot_username}?startgroup=schedq_{quiz_id}")],
            [InlineKeyboardButton(text="🚩 Report", callback_data=ReportCB(action="start", quiz_id=quiz_id).pack())],
            [InlineKeyboardButton(text=_("back"), callback_data=QuizBankCB(action="list", page=1).pack())],
        ]
    )
