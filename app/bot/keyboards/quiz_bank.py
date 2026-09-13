from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import MenuCB, QuizActionCB, QuizBankCB
from app.database.models import Category, Quiz
from app.i18n import Translator

GRADES = [5, 6, 7, 8, 9, 10, 11]


def subject_picker_keyboard(locale: str, subjects: list[Category]) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    rows = []
    row: list[InlineKeyboardButton] = []
    for subject in subjects:
        icon = subject.icon or ""
        row.append(
            InlineKeyboardButton(
                text=f"{icon} {subject.localized_name(locale)}".strip(),
                callback_data=QuizBankCB(action="subject", category_id=subject.id.hex).pack(),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=_("quiz_bank_all_subjects"), callback_data=QuizBankCB(action="list", page=1).pack())])
    rows.append([InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def grade_picker_keyboard(locale: str, category_id: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    rows = []
    row: list[InlineKeyboardButton] = []
    for grade in GRADES:
        row.append(
            InlineKeyboardButton(
                text=f"{grade}-sinf",
                callback_data=QuizBankCB(action="grade", category_id=category_id, grade=grade, page=1).pack(),
            )
        )
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton(text=_("quiz_bank_all_grades"), callback_data=QuizBankCB(action="grade", category_id=category_id, grade=0, page=1).pack())]
    )
    rows.append([InlineKeyboardButton(text=_("back"), callback_data=QuizBankCB(action="subjects").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    locale: str,
    page: int,
    total_pages: int,
    base_action: str = "list",
    sort: str = "newest",
    category_id: str | None = None,
    grade: int = 0,
) -> InlineKeyboardMarkup:
    _ = Translator(locale)

    def cb(action: str, **kwargs) -> str:
        return QuizBankCB(action=action, sort=sort, category_id=category_id, grade=grade, **kwargs).pack()

    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=cb(base_action, page=page - 1)))
    buttons.append(
        InlineKeyboardButton(
            text=_("page_indicator", page=page, total=max(total_pages, 1)),
            callback_data=cb("goto", page=total_pages),
        )
    )
    if page < total_pages:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=cb(base_action, page=page + 1)))

    rows = [buttons]
    rows.append(
        [
            InlineKeyboardButton(text=_("search_button"), callback_data=cb("search")),
            InlineKeyboardButton(text=_("filters_button"), callback_data=cb("filters")),
        ]
    )
    rows.append([InlineKeyboardButton(text=_("quiz_bank_change_subject"), callback_data=QuizBankCB(action="subjects").pack())])
    rows.append([InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


SORT_OPTIONS = ["newest", "popular", "rating"]


def filters_keyboard(locale: str, current_sort: str, category_id: str | None = None, grade: int = 0) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    rows = []
    for sort in SORT_OPTIONS:
        label = _(f"sort_{sort}_label")
        if sort == current_sort:
            label = f"✅ {label}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=QuizBankCB(action="list", page=1, sort=sort, category_id=category_id, grade=grade).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_("back"),
                callback_data=QuizBankCB(action="list", page=1, sort=current_sort, category_id=category_id, grade=grade).pack(),
            )
        ]
    )
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
