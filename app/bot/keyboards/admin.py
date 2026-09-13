from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import AdminPanelCB, ModerationCB
from app.database.models import Quiz


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


def pending_quiz_keyboard(quiz: Quiz) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=ModerationCB(action="approve", quiz_id=str(quiz.id)).pack()),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=ModerationCB(action="reject", quiz_id=str(quiz.id)).pack()),
            ]
        ]
    )
