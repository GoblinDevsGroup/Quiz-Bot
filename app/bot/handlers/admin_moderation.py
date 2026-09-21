import html
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.admin import back_to_admin_panel_keyboard, pending_quiz_keyboard
from app.bot.keyboards.callback_data import AdminPanelCB, ModerationCB
from app.bot.states.admin_states import ModerationStates
from app.core.enums import QuizStatus
from app.database.models import Quiz
from app.database.repositories.quiz_repository import QuizRepository
from app.services.admin.admin_service import all_admin_ids, is_admin
from app.services.quiz.quiz_service import QuizService

router = Router(name="admin_moderation")

PAGE_SIZE = 10


async def _is_admin(session: AsyncSession, telegram_id: int) -> bool:
    return await is_admin(session, telegram_id)


def _pending_quiz_text(quiz: Quiz) -> str:
    subject = quiz.category.localized_name("uz") if quiz.category else "—"
    grade = f"{quiz.grade}-sinf" if quiz.grade else "—"
    return (
        "🆕 Yangi test tasdiqlash uchun yuborildi!\n\n"
        f"📚 Fan: {html.escape(subject)}\n"
        f"🏫 Sinf: {grade}\n"
        f"📝 Sarlavha: {html.escape(quiz.title)}\n"
        f"👤 Muallif: {html.escape(quiz.creator.display_name)}\n"
        f"❓ Savollar soni: {quiz.question_count}\n"
        f"🆔 ID: {quiz.id}"
    )


def _moderator_name(user: TgUser) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name or str(user.id)


def _decided_text(quiz: Quiz) -> str:
    """The message every admin sees once a quiz has been moderated, whoever
    did it — same wording for the admin who clicked and for all the others."""
    by = quiz.moderated_by_name or "boshqa admin"
    head = (
        f"✅ {by} tasdiqladi. Test raqami: #{quiz.moderation_number}"
        if quiz.status == QuizStatus.published.value
        else f"❌ {by} rad etdi."
    )
    subject = quiz.category.localized_name("uz") if quiz.category else "—"
    grade = f"{quiz.grade}-sinf" if quiz.grade else "—"
    return (
        f"{head}\n\n"
        f"📝 {quiz.title}\n"
        f"📚 Fan: {subject}  ·  🏫 Sinf: {grade}\n"
        f"👤 Muallif: {quiz.creator.display_name}"
    )


async def _send_pending_card(bot: Bot, session: AsyncSession, chat_id: int, quiz: Quiz) -> None:
    sent = await bot.send_message(chat_id, _pending_quiz_text(quiz), reply_markup=pending_quiz_keyboard(quiz), parse_mode=None)
    await QuizRepository(session).add_moderation_notification(quiz.id, chat_id, sent.message_id)


async def _refresh_all_cards(bot: Bot, session: AsyncSession, quiz: Quiz) -> None:
    """Rewrite every admin's copy of the pending card to the final outcome and
    drop its buttons, so nobody can approve/reject the same quiz again."""
    text = _decided_text(quiz)
    quiz_repo = QuizRepository(session)
    for note in await quiz_repo.list_moderation_notifications(quiz.id):
        try:
            await bot.edit_message_text(text, chat_id=note.admin_telegram_id, message_id=note.message_id, reply_markup=None, parse_mode=None)
        except Exception:
            pass
    # Done with these cards; a rejected quiz that is resubmitted gets fresh ones.
    await quiz_repo.clear_moderation_notifications(quiz.id)


async def _show_already_decided(callback: CallbackQuery, quiz: Quiz) -> None:
    """Another admin got there first (or this card was stale): show them the
    outcome in place of the buttons instead of moderating a second time."""
    try:
        await callback.message.edit_text(_decided_text(quiz), reply_markup=None, parse_mode=None)
    except Exception:
        pass
    await callback.answer("Bu test allaqachon ko'rib chiqilgan.", show_alert=True)


async def notify_admins_new_submission(bot: Bot, session: AsyncSession, quiz: Quiz) -> None:
    for admin_id in await all_admin_ids(session):
        try:
            await _send_pending_card(bot, session, admin_id, quiz)
        except Exception:
            pass


@router.callback_query(AdminPanelCB.filter(F.action == "pending"))
async def show_pending_quizzes(callback: CallbackQuery, callback_data: AdminPanelCB, session: AsyncSession) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer()
        return

    page = max(1, callback_data.page)
    quiz_repo = QuizRepository(session)
    quizzes, total = await quiz_repo.list_pending_for_admin(page=page, page_size=PAGE_SIZE)
    if not quizzes:
        text = "✅ Hozircha tasdiqlanishi kerak bo'lgan test yo'q." if page == 1 else "📋 Boshqa kutayotgan test yo'q."
        await callback.message.edit_text(text, reply_markup=back_to_admin_panel_keyboard())
        await callback.answer()
        return

    shown_so_far = (page - 1) * PAGE_SIZE + len(quizzes)
    await callback.message.edit_text(f"📋 Kutayotgan testlar: {total} ta", reply_markup=back_to_admin_panel_keyboard())
    for quiz in quizzes:
        await _send_pending_card(callback.bot, session, callback.message.chat.id, quiz)
    if shown_so_far < total:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        more_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="➡️ Yana ko'rsatish", callback_data=AdminPanelCB(action="pending", page=page + 1).pack())]]
        )
        await callback.message.answer(f"Yana {total - shown_so_far} ta kutayotgan test bor.", reply_markup=more_kb)
    await callback.answer()


@router.callback_query(ModerationCB.filter(F.action == "approve"))
async def approve_quiz(callback: CallbackQuery, callback_data: ModerationCB, session: AsyncSession) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer()
        return

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_for_moderation(uuid.UUID(callback_data.quiz_id))
    if quiz is None:
        await callback.answer("Test topilmadi.", show_alert=True)
        return

    if quiz.status != QuizStatus.pending.value:
        await _show_already_decided(callback, quiz)
        return

    quiz_service = QuizService(session)
    quiz = await quiz_service.approve_quiz(quiz, _moderator_name(callback.from_user))

    await _refresh_all_cards(callback.bot, session, quiz)
    await callback.answer("Tasdiqlandi")

    try:
        await callback.bot.send_message(
            quiz.creator.telegram_user_id,
            f"✅ Sizning \"{quiz.title}\" testingiz tasdiqlandi va bazaga qo'shildi!\n\n🔢 Test raqami: #{quiz.moderation_number}",
            parse_mode=None,
        )
    except Exception:
        pass


@router.callback_query(ModerationCB.filter(F.action == "reject"))
async def prompt_reject_reason(callback: CallbackQuery, callback_data: ModerationCB, state: FSMContext, session: AsyncSession) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer()
        return

    quiz = await QuizRepository(session).get_by_id(uuid.UUID(callback_data.quiz_id), refresh=True)
    if quiz is not None and quiz.status != QuizStatus.pending.value:
        await _show_already_decided(callback, quiz)
        return

    await state.set_state(ModerationStates.awaiting_reject_reason)
    await state.update_data(quiz_id=callback_data.quiz_id)
    await callback.message.answer("Rad etish sababini yozing (yoki sababsiz o'tkazish uchun '-' yuboring):")
    await callback.answer()


@router.message(ModerationStates.awaiting_reject_reason)
async def apply_reject_reason(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    await state.clear()

    reason = (message.text or "").strip()
    reason = None if reason == "-" else reason

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_for_moderation(uuid.UUID(data["quiz_id"]))
    if quiz is None:
        await message.answer("Test topilmadi.")
        return

    if quiz.status != QuizStatus.pending.value:
        await message.answer(f"ℹ️ Bu test allaqachon ko'rib chiqilgan.\n\n{_decided_text(quiz)}")
        return

    quiz_service = QuizService(session)
    quiz = await quiz_service.reject_quiz(quiz, _moderator_name(message.from_user))

    await _refresh_all_cards(message.bot, session, quiz)
    await message.answer(f"❌ \"{quiz.title}\" testi rad etildi.")

    creator_text = f"❌ Sizning \"{quiz.title}\" testingiz rad etildi."
    if reason:
        creator_text += f"\n\nSabab: {reason}"
    try:
        await message.bot.send_message(quiz.creator.telegram_user_id, creator_text, parse_mode=None)
    except Exception:
        pass
