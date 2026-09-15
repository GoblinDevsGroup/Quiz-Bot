import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin_filter import IsAdmin
from app.bot.keyboards.admin import (
    admin_grade_quiz_picker_keyboard,
    admin_grade_value_keyboard,
    admin_panel_keyboard,
    back_to_admin_panel_keyboard,
)
from app.bot.keyboards.callback_data import AdminGradeCB, AdminPanelCB
from app.bot.states.admin_states import AdminStates
from app.database.repositories.chat_membership_repository import ChatMembershipRepository
from app.database.repositories.quiz_repository import QuizRepository
from app.database.repositories.user_repository import UserRepository
from app.services.quiz.quiz_service import QuizService
from app.services.reports.report_service import ReportService
from app.services.users.user_service import UserService

router = Router(name="admin")
router.message.filter(IsAdmin())

PAGE_SIZE = 15


def _is_admin_callback(callback: CallbackQuery) -> bool:
    from app.core.config import settings

    return callback.from_user is not None and callback.from_user.id in settings.admin_id_list


async def plain(message: Message, text: str) -> None:
    # These are diagnostic/moderation dumps containing raw usernames, quiz
    # titles, and "<placeholder>"-style usage hints — any of which can
    # contain '<'/'>'/'&' that the bot's default HTML parse mode would try
    # (and fail) to interpret as markup. None disables entity parsing for
    # this call only, regardless of the bot-wide default.
    await message.answer(text, parse_mode=None)


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    await message.answer("🛠 Admin panel", reply_markup=admin_panel_keyboard())


@router.message(Command("cancel"))
async def admin_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current is None:
        await message.answer("Bekor qilinadigan hech narsa yo'q.", reply_markup=admin_panel_keyboard())
        return
    await message.answer("❌ Bekor qilindi.", reply_markup=admin_panel_keyboard())


# ---------------------------------------------------------------------------
# Text-command bodies factored into helpers so both the /command form and the
# inline admin-panel buttons below share exactly one implementation each.
# ---------------------------------------------------------------------------


async def _do_ban(session: AsyncSession, telegram_id: int) -> str:
    user_service = UserService(session)
    target = await user_service.get_by_telegram_id(telegram_id)
    if not target:
        return "User not found."
    await user_service.ban(target)
    return f"🚫 Banned {target.display_name}"


async def _do_unban(session: AsyncSession, telegram_id: int) -> str:
    user_service = UserService(session)
    target = await user_service.get_by_telegram_id(telegram_id)
    if not target:
        return "User not found."
    await user_service.unban(target)
    return f"✅ Unbanned {target.display_name}"


async def _reports_text(session: AsyncSession) -> str:
    report_service = ReportService(session)
    reports = await report_service.list_open_reports()
    if not reports:
        return "No open reports."
    lines = [f"#{r.id} quiz={r.quiz_id} reason={r.reason} comment={r.comment or '-'}" for r in reports[:20]]
    return "\n".join(lines)


async def _delete_quiz_text(session: AsyncSession, quiz_id_raw: str) -> str:
    try:
        quiz_id = uuid.UUID(quiz_id_raw)
    except ValueError:
        return "Invalid quiz id."

    repo = QuizRepository(session)
    quiz = await repo.get_by_id(quiz_id)
    if not quiz:
        return "Quiz not found."
    await repo.soft_delete(quiz)
    return "🗑 Quiz deleted by admin."


async def _find_user_text(session: AsyncSession, query: str) -> str:
    user_repo = UserRepository(session)
    users = await user_repo.search_by_username(query)
    if not users:
        return "No users found."
    lines = [f"{u.display_name} | tg_id={u.telegram_user_id} | banned={u.is_banned}" for u in users]
    return "\n".join(lines)


async def _list_users_text(session: AsyncSession, page: int) -> str:
    user_repo = UserRepository(session)
    quiz_repo = QuizRepository(session)
    users, total = await user_repo.list_all(page=page, page_size=PAGE_SIZE)
    if not users:
        return "No users on this page."

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"👥 Users: {total} total (page {page}/{total_pages})", ""]
    for u in users:
        _quizzes, quiz_count = await quiz_repo.list_by_creator(u.id, page=1, page_size=1)
        ban_flag = " 🚫BANNED" if u.is_banned else ""
        lines.append(f"{u.display_name} | tg_id={u.telegram_user_id} | quizzes={quiz_count}{ban_flag}")
    lines.append("")
    lines.append(f"Next page: /users {page + 1}" if page < total_pages else "(last page)")
    return "\n".join(lines)


async def _list_all_quizzes_text(session: AsyncSession, page: int) -> str:
    quiz_repo = QuizRepository(session)
    quizzes, total = await quiz_repo.list_all_for_admin(page=page, page_size=PAGE_SIZE)
    if not quizzes:
        return "No quizzes on this page."

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"📚 All quizzes: {total} total (page {page}/{total_pages})", ""]
    for q in quizzes:
        lines.append(
            f"• {q.title} | by {q.creator.display_name} | {q.status}/{q.visibility} | "
            f"{q.question_count}q | id={q.id}"
        )
    lines.append("")
    lines.append("Delete with: /deletequiz [id]")
    lines.append(f"Next page: /allquizzes {page + 1}" if page < total_pages else "(last page)")
    return "\n".join(lines)


VALID_GRADES = {5, 6, 7, 8, 9, 10, 11}


async def _set_quiz_grade(session: AsyncSession, quiz_id_raw: str, grade_raw: str):
    """Returns (message_text, quiz_or_None). quiz is only returned on success,
    so the caller can notify its creator that an admin moved it to a
    different grade."""
    try:
        quiz_id = uuid.UUID(quiz_id_raw)
    except ValueError:
        return "❌ Noto'g'ri test ID.", None

    grade_raw = grade_raw.strip().removesuffix("-sinf").strip()
    if not grade_raw.isdigit() or int(grade_raw) not in VALID_GRADES:
        return "❌ Sinf 5 dan 11 gacha bo'lishi kerak.", None
    grade = int(grade_raw)

    repo = QuizRepository(session)
    quiz = await repo.get_by_id(quiz_id)
    if quiz is None:
        return "❌ Test topilmadi.", None

    old_grade = quiz.grade
    await repo.update_fields(quiz, grade=grade)
    return f"✅ \"{quiz.title}\" testi {old_grade or '—'}-sinfdan {grade}-sinfga o'tkazildi.", quiz


async def _list_groups_text(session: AsyncSession) -> str:
    repo = ChatMembershipRepository(session)
    groups = await repo.list_active()
    if not groups:
        return "Bot is not currently a member of any tracked group."
    lines = [f"👥 Bot is active in {len(groups)} group(s):", ""]
    for g in groups:
        lines.append(f"• {g.chat_title or '(untitled)'} | {g.chat_type} | chat_id={g.chat_id}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text commands (kept for admins who prefer typing commands directly)
# ---------------------------------------------------------------------------


@router.message(Command("ban"))
async def ban_user(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await plain(message, "Usage: /ban [telegram_id]")
        return
    await plain(message, await _do_ban(session, int(parts[1])))


@router.message(Command("unban"))
async def unban_user(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await plain(message, "Usage: /unban [telegram_id]")
        return
    await plain(message, await _do_unban(session, int(parts[1])))


@router.message(Command("reports"))
async def list_reports(message: Message, session: AsyncSession) -> None:
    await plain(message, await _reports_text(session))


@router.message(Command("deletequiz"))
async def admin_delete_quiz(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    if len(parts) != 2:
        await plain(message, "Usage: /deletequiz [quiz_id]")
        return
    await plain(message, await _delete_quiz_text(session, parts[1]))


@router.message(Command("finduser"))
async def find_user(message: Message, session: AsyncSession) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await plain(message, "Usage: /finduser [username]")
        return
    await plain(message, await _find_user_text(session, parts[1]))


@router.message(Command("users"))
async def list_all_users(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
    await plain(message, await _list_users_text(session, page))


@router.message(Command("allquizzes"))
async def list_all_quizzes(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
    await plain(message, await _list_all_quizzes_text(session, page))


@router.message(Command("setgrade"))
async def admin_set_grade(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    if len(parts) != 3:
        await plain(message, "Usage: /setgrade [quiz_id] [5-11]")
        return
    text, quiz = await _set_quiz_grade(session, parts[1], parts[2])
    await plain(message, text)
    if quiz is not None:
        await _notify_grade_changed(message.bot, quiz)


async def _notify_grade_changed(bot, quiz) -> None:
    try:
        await bot.send_message(
            quiz.creator.telegram_user_id,
            f"ℹ️ \"{quiz.title}\" testingiz admin tomonidan {quiz.grade}-sinfga o'tkazildi.",
            parse_mode=None,
        )
    except Exception:
        pass


@router.message(Command("groups"))
async def list_groups(message: Message, session: AsyncSession) -> None:
    await plain(message, await _list_groups_text(session))


@router.message(Command("broadcast"))
async def broadcast_message(message: Message, redis) -> None:
    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await plain(message, "Usage: /broadcast [message text]")
        return

    await redis.enqueue_job(
        "broadcast_message_task",
        text=text,
        admin_telegram_id=message.from_user.id,
    )
    await plain(message, "📣 Broadcast queued — sending in the background, you'll get a summary when it's done.")


# ---------------------------------------------------------------------------
# Inline admin panel
# ---------------------------------------------------------------------------


@router.callback_query(AdminPanelCB.filter(F.action == "panel"))
async def open_panel(callback: CallbackQuery) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    await callback.message.edit_text("🛠 Admin panel", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(AdminPanelCB.filter(F.action == "users"))
async def panel_users(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    text = await _list_users_text(session, 1)
    await callback.message.edit_text(text, reply_markup=back_to_admin_panel_keyboard())
    await callback.answer()


@router.callback_query(AdminPanelCB.filter(F.action == "allquizzes"))
async def panel_all_quizzes(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    text = await _list_all_quizzes_text(session, 1)
    await callback.message.edit_text(text, reply_markup=back_to_admin_panel_keyboard())
    await callback.answer()


@router.callback_query(AdminPanelCB.filter(F.action == "reports"))
async def panel_reports(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    text = await _reports_text(session)
    await callback.message.edit_text(text, reply_markup=back_to_admin_panel_keyboard())
    await callback.answer()


@router.callback_query(AdminPanelCB.filter(F.action == "groups"))
async def panel_groups(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    text = await _list_groups_text(session)
    await callback.message.edit_text(text, reply_markup=back_to_admin_panel_keyboard())
    await callback.answer()


@router.callback_query(AdminPanelCB.filter(F.action == "test_groups"))
async def panel_test_groups(callback: CallbackQuery, session: AsyncSession, user, translator) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    from app.bot.handlers.subject_group import render_test_group_subjects

    await render_test_group_subjects(callback, session, user, translator)
    await callback.answer()


async def _prompt(callback: CallbackQuery, state: FSMContext, target_state, text: str) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    await state.set_state(target_state)
    await callback.message.answer(f"{text}\n\n(Bekor qilish uchun /cancel yuboring)")
    await callback.answer()


@router.callback_query(AdminPanelCB.filter(F.action == "ban_prompt"))
async def panel_ban_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await _prompt(callback, state, AdminStates.awaiting_ban_id, "Bloklamoqchi bo'lgan foydalanuvchining Telegram ID sini yuboring:")


@router.callback_query(AdminPanelCB.filter(F.action == "unban_prompt"))
async def panel_unban_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await _prompt(callback, state, AdminStates.awaiting_unban_id, "Blokdan chiqarmoqchi bo'lgan foydalanuvchining Telegram ID sini yuboring:")


@router.callback_query(AdminPanelCB.filter(F.action == "finduser_prompt"))
async def panel_finduser_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await _prompt(callback, state, AdminStates.awaiting_finduser_query, "Qidirmoqchi bo'lgan foydalanuvchi nomini (username) yuboring:")


@router.callback_query(AdminPanelCB.filter(F.action == "delete_prompt"))
async def panel_delete_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await _prompt(callback, state, AdminStates.awaiting_delete_quiz_id, "O'chirmoqchi bo'lgan testning ID sini yuboring:")


GRADE_PICKER_PAGE_SIZE = 10


@router.callback_query(AdminPanelCB.filter(F.action == "setgrade_prompt"))
async def panel_setgrade_prompt(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    await _show_grade_quiz_picker(callback, session, page=1)


@router.callback_query(AdminGradeCB.filter(F.action == "pick"))
async def grade_pick_page(callback: CallbackQuery, callback_data: AdminGradeCB, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    await _show_grade_quiz_picker(callback, session, page=callback_data.page)


async def _show_grade_quiz_picker(callback: CallbackQuery, session: AsyncSession, page: int) -> None:
    quiz_repo = QuizRepository(session)
    quizzes, total = await quiz_repo.list_all_for_admin(page=page, page_size=GRADE_PICKER_PAGE_SIZE)
    if not quizzes:
        await callback.message.edit_text("Hozircha test yo'q.", reply_markup=back_to_admin_panel_keyboard())
        await callback.answer()
        return
    total_pages = max(1, (total + GRADE_PICKER_PAGE_SIZE - 1) // GRADE_PICKER_PAGE_SIZE)
    await callback.message.edit_text(
        "🏫 Sinfini o'zgartirmoqchi bo'lgan testni tanlang:",
        reply_markup=admin_grade_quiz_picker_keyboard(quizzes, page, total_pages),
    )
    await callback.answer()


@router.callback_query(AdminGradeCB.filter(F.action == "select"))
async def grade_select_quiz(callback: CallbackQuery, callback_data: AdminGradeCB, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(callback_data.quiz_id))
    if quiz is None:
        await callback.answer("Test topilmadi.", show_alert=True)
        return
    await callback.message.edit_text(
        f"\"{quiz.title}\" — hozirgi sinf: {quiz.grade or '—'}. Yangi sinfni tanlang:",
        reply_markup=admin_grade_value_keyboard(callback_data.quiz_id),
    )
    await callback.answer()


@router.callback_query(AdminGradeCB.filter(F.action == "set"))
async def grade_set_value(callback: CallbackQuery, callback_data: AdminGradeCB, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    text, quiz = await _set_quiz_grade(session, callback_data.quiz_id, str(callback_data.grade))
    await callback.message.edit_text(text, reply_markup=back_to_admin_panel_keyboard())
    await callback.answer()
    if quiz is not None:
        await _notify_grade_changed(callback.bot, quiz)


@router.callback_query(AdminPanelCB.filter(F.action == "broadcast_prompt"))
async def panel_broadcast_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await _prompt(callback, state, AdminStates.awaiting_broadcast_text, "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabar matnini yuboring:")


@router.message(AdminStates.awaiting_ban_id)
async def apply_ban(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("❌ Noto'g'ri Telegram ID.")
        return
    await plain(message, await _do_ban(session, int(text)))


@router.message(AdminStates.awaiting_unban_id)
async def apply_unban(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("❌ Noto'g'ri Telegram ID.")
        return
    await plain(message, await _do_unban(session, int(text)))


@router.message(AdminStates.awaiting_finduser_query)
async def apply_finduser(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await plain(message, await _find_user_text(session, (message.text or "").strip()))


@router.message(AdminStates.awaiting_delete_quiz_id)
async def apply_delete_quiz(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await plain(message, await _delete_quiz_text(session, (message.text or "").strip()))


@router.message(AdminStates.awaiting_broadcast_text)
async def apply_broadcast(message: Message, state: FSMContext, redis) -> None:
    await state.clear()
    text = (message.text or "").strip()
    if not text:
        await plain(message, "Bo'sh xabar yuborib bo'lmaydi.")
        return
    await redis.enqueue_job("broadcast_message_task", text=text, admin_telegram_id=message.from_user.id)
    await plain(message, "📣 Xabar navbatga qo'yildi — fonda yuborilmoqda, tugagach xabar beriladi.")
