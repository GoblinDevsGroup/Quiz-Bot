from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import AdminGradeCB, AdminPanelCB, ModerationCB
from app.database.models import Quiz

GRADES = [5, 6, 7, 8, 9, 10, 11]


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    def btn(text: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=AdminPanelCB(action=action).pack())

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [btn("📋 Kutayotgan testlar", "pending")],
            [btn("👥 Foydalanuvchilar", "users"), btn("📚 Barcha testlar", "allquizzes")],
            [btn("🚩 Shikoyatlar", "reports"), btn("👥 Guruhlar", "groups")],
            [btn("🚫 Ban qilish", "ban_prompt"), btn("✅ Blokdan chiqarish", "unban_prompt")],
            [btn("🔎 Foydalanuvchi qidirish", "finduser_prompt")],
            [btn("🗑 Testni o'chirish", "delete_prompt")],
            [btn("🏫 Test sinfini o'zgartirish", "setgrade_prompt")],
            [btn("📣 Xabar yuborish", "broadcast_prompt")],
        ]
    )


def back_to_admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Admin panel", callback_data=AdminPanelCB(action="panel").pack())]]
    )


def admin_grade_quiz_picker_keyboard(quizzes: list[Quiz], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Lets an admin pick a quiz to move between grades by tapping it —
    no need to hunt down and type/paste a UUID by hand."""
    rows = []
    for quiz in quizzes:
        label = f"{quiz.title[:35]} ({quiz.grade or '—'}-sinf)"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=AdminGradeCB(action="select", quiz_id=quiz.id.hex).pack())]
        )
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=AdminGradeCB(action="pick", page=page - 1).pack()))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data=AdminGradeCB(action="pick", page=page).pack()))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=AdminGradeCB(action="pick", page=page + 1).pack()))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Admin panel", callback_data=AdminPanelCB(action="panel").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_grade_value_keyboard(quiz_id_hex: str) -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for g in GRADES:
        row.append(InlineKeyboardButton(text=f"{g}-sinf", callback_data=AdminGradeCB(action="set", quiz_id=quiz_id_hex, grade=g).pack()))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Testlar ro'yxati", callback_data=AdminGradeCB(action="pick", page=1).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pending_quiz_keyboard(quiz: Quiz) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=ModerationCB(action="approve", quiz_id=str(quiz.id)).pack()),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=ModerationCB(action="reject", quiz_id=str(quiz.id)).pack()),
            ]
        ]
    )
