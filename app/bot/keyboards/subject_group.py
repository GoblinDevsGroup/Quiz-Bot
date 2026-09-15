from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import MenuCB, SubjectGroupCB
from app.database.models import Category, SubjectGroup
from app.i18n import Translator


def subject_group_subject_keyboard(locale: str, subjects: list[Category]) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    rows = []
    row: list[InlineKeyboardButton] = []
    for subject in subjects:
        icon = subject.icon or ""
        row.append(
            InlineKeyboardButton(
                text=f"{icon} {subject.localized_name(locale)}".strip(),
                callback_data=SubjectGroupCB(action="subject", category_id=subject.id.hex).pack(),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subject_group_list_keyboard(
    locale: str, category_id: str, groups: list[SubjectGroup], is_admin: bool
) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    rows = []
    for group in groups:
        label = group.title or _("test_group_join_button")
        row = [InlineKeyboardButton(text=f"👥 {label}", url=group.invite_link)]
        if is_admin:
            row.append(
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=SubjectGroupCB(action="delete", group_id=group.id.hex).pack(),
                )
            )
        rows.append(row)
    if is_admin:
        rows.append(
            [InlineKeyboardButton(text=_("test_group_add_button"), callback_data=SubjectGroupCB(action="add_prompt", category_id=category_id).pack())]
        )
    rows.append([InlineKeyboardButton(text=_("back"), callback_data=SubjectGroupCB(action="subjects").pack())])
    rows.append([InlineKeyboardButton(text=_("main_menu"), callback_data=MenuCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
