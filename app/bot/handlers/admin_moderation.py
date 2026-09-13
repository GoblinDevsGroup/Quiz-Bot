import html
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.admin import back_to_admin_panel_keyboard, pending_quiz_keyboard
from app.bot.keyboards.callback_data import AdminPanelCB, ModerationCB
from app.bot.states.admin_states import ModerationStates
from app.core.config import settings
from app.database.models import Quiz
from app.database.repositories.quiz_repository import QuizRepository
from app.services.quiz.quiz_service import QuizService

router = Router(name="admin_moderation")

PAGE_SIZE = 10


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_id_list


def _pending_quiz_text(quiz: Quiz) -> str:
    subject = quiz.category.localized_name("uz") if quiz.category else "—"
    grade = f"{quiz.grade}-sinf" if quiz.grade else "—"
    return (
        "🆕 Yangi test tasdiqlash uchun yuborildi!\n\n"
        f"📚 Fan: {html.escape(subject)}\n"
        f"🏫 Sinf: {grade}\n"
        f"📝 Sarlavha: {html.escape(quiz.title)}\n"
        f"👤 Muallif: {html.escape(quiz.creator.display_name)}\n"
        f"❓ Savollar soni: {quiz.question_count}"
    )


async def notify_admins_new_submission(bot: Bot, quiz: Quiz) -> None:
    text = _pending_quiz_text(quiz)
    for admin_id in settings.admin_id_list:
        try:
            await bot.send_message(admin_id, text, reply_markup=pending_quiz_keyboard(quiz), parse_mode=None)
        except Exception:
            pass


@router.callback_query(AdminPanelCB.filter(F.action == "pending"))
async def show_pending_quizzes(callback: CallbackQuery, callback_data: AdminPanelCB, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
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
        await callback.message.answer(_pending_quiz_text(quiz), reply_markup=pending_quiz_keyboard(quiz), parse_mode=None)
    if shown_so_far < total:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        more_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="➡️ Yana ko'rsatish", callback_data=AdminPanelCB(action="pending", page=page + 1).pack())]]
        )
        await callback.message.answer(f"Yana {total - shown_so_far} ta kutayotgan test bor.", reply_markup=more_kb)
    await callback.answer()


@router.callback_query(ModerationCB.filter(F.action == "approve"))
async def approve_quiz(callback: CallbackQuery, callback_data: ModerationCB, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(callback_data.quiz_id))
    if quiz is None:
        await callback.answer("Test topilmadi.", show_alert=True)
        return

    quiz_service = QuizService(session)
    quiz = await quiz_service.approve_quiz(quiz)

    await callback.message.edit_text(f"✅ Tasdiqlandi. Test raqami: #{quiz.moderation_number}\n\n{quiz.title}", reply_markup=None)
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
async def prompt_reject_reason(callback: CallbackQuery, callback_data: ModerationCB, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
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
    quiz = await quiz_repo.get_by_id(uuid.UUID(data["quiz_id"]))
    if quiz is None:
        await message.answer("Test topilmadi.")
        return

    quiz_service = QuizService(session)
    quiz = await quiz_service.reject_quiz(quiz)

    await message.answer(f"❌ \"{quiz.title}\" testi rad etildi.")

    creator_text = f"❌ Sizning \"{quiz.title}\" testingiz rad etildi."
    if reason:
        creator_text += f"\n\nSabab: {reason}"
    try:
        await message.bot.send_message(quiz.creator.telegram_user_id, creator_text, parse_mode=None)
    except Exception:
        pass
