import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import QuizStatus
from app.bot.keyboards.callback_data import MenuCB, MyQuizzesCB, QuizActionCB
from app.bot.keyboards.common import confirm_keyboard
from app.bot.keyboards.my_quizzes import (
    my_quiz_card_keyboard,
    my_quizzes_pagination_keyboard,
    my_quizzes_tabs_keyboard,
)
from app.database.models import User
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator
from app.services.quiz.quiz_presentation import build_quiz_card_text, build_quiz_list_row, short_code
from app.services.quiz.quiz_service import QuizPermissionError, QuizService

router = Router(name="my_quizzes")

PAGE_SIZE = 5


@router.callback_query(MenuCB.filter(F.action == "my_quizzes"))
async def open_my_quizzes(callback: CallbackQuery, session: AsyncSession, translator: Translator, user: User) -> None:
    quiz_repo = QuizRepository(session)
    quizzes, _total = await quiz_repo.list_by_creator(user.id, status=None, page=1, page_size=100)

    if not quizzes:
        await callback.message.edit_text(translator("my_quizzes_empty"), reply_markup=my_quizzes_tabs_keyboard(user.locale))
        await callback.answer()
        return

    rows = [build_quiz_list_row(translator, user.locale, idx, quiz) for idx, quiz in enumerate(quizzes, start=1)]
    text = translator("my_quizzes_title") + "\n\n" + "\n\n".join(rows)
    await callback.message.edit_text(text, reply_markup=my_quizzes_tabs_keyboard(user.locale), parse_mode="HTML")
    await callback.answer()


@router.message(F.text.startswith("/view_"))
async def view_quiz_by_short_code(message: Message, session: AsyncSession, user: User, translator: Translator) -> None:
    from app.bot.keyboards.manual_creation import created_quiz_keyboard

    code = message.text.removeprefix("/view_").strip()
    quiz_repo = QuizRepository(session)
    quizzes, _total = await quiz_repo.list_by_creator(user.id, status=None, page=1, page_size=100)
    quiz = next((q for q in quizzes if short_code(q) == code), None)
    if quiz is None:
        await message.answer(translator("quiz_not_found"))
        return

    bot_info = await message.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=quiz_{quiz.id}"
    text = build_quiz_card_text(translator, user.locale, quiz, link=link)
    await message.answer(
        text, reply_markup=created_quiz_keyboard(user.locale, str(quiz.id), bot_info.username), parse_mode="HTML"
    )


@router.callback_query(MyQuizzesCB.filter(F.action == "list"))
async def list_my_quizzes(
    callback: CallbackQuery, callback_data: MyQuizzesCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    # IMPORTANT: only ever filter by the current local user's id. Never trust
    # any client-supplied user identifier for this query.
    repo = QuizRepository(session)
    status = callback_data.status or QuizStatus.draft.value
    quizzes, total = await repo.list_by_creator(user.id, status=status, page=callback_data.page, page_size=PAGE_SIZE)

    if not quizzes:
        await callback.message.edit_text(translator("my_quizzes_empty"), reply_markup=my_quizzes_tabs_keyboard(user.locale))
        await callback.answer()
        return

    lines = []
    for quiz in quizzes:
        lines.append(
            translator(
                "my_quiz_card",
                title=quiz.title,
                count=quiz.question_count,
                status=translator(f"status_{quiz.status}"),
            )
        )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    await callback.message.edit_text("\n\n".join(lines), reply_markup=my_quizzes_pagination_keyboard(user.locale, status, callback_data.page, total_pages))

    # Send action keyboards for each quiz as separate compact messages for clarity
    for quiz in quizzes:
        await callback.message.answer(f"⚙️ {quiz.title}", reply_markup=my_quiz_card_keyboard(user.locale, quiz))

    await callback.answer()


@router.callback_query(QuizActionCB.filter(F.action == "publish"))
async def publish_quiz(
    callback: CallbackQuery, callback_data: QuizActionCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(callback_data.quiz_id))
    if quiz is None:
        await callback.answer(translator("quiz_not_found"), show_alert=True)
        return

    quiz_service = QuizService(session)
    try:
        quiz = await quiz_service.submit_for_moderation(quiz, user.id)
    except QuizPermissionError:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    from app.bot.handlers.admin_moderation import notify_admins_new_submission

    await notify_admins_new_submission(callback.bot, session, quiz)

    await callback.message.answer(translator("quiz_submitted_for_review"))
    await callback.answer()


@router.callback_query(QuizActionCB.filter(F.action == "delete_confirm"))
async def confirm_delete(callback: CallbackQuery, callback_data: QuizActionCB, translator: Translator, user: User) -> None:
    from app.bot.keyboards.callback_data import ConfirmCB

    await callback.message.edit_text(
        translator("delete_confirm"),
        reply_markup=confirm_keyboard(user.locale, action="delete_quiz", value=callback_data.quiz_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:"))
async def confirm_delete_execute(callback: CallbackQuery, session: AsyncSession, user: User, translator: Translator) -> None:
    from app.bot.keyboards.callback_data import ConfirmCB

    try:
        data = ConfirmCB.unpack(callback.data)
    except (ValueError, TypeError):
        return
    if data.action != "delete_quiz":
        return

    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(data.value))
    if quiz is None:
        await callback.answer(translator("quiz_not_found"), show_alert=True)
        return

    quiz_service = QuizService(session)
    try:
        await quiz_service.delete(quiz, user.id)
    except QuizPermissionError:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return

    await callback.message.edit_text(translator("quiz_deleted"))
    await callback.answer()


@router.callback_query(QuizActionCB.filter(F.action == "results"))
async def quiz_results(
    callback: CallbackQuery, callback_data: QuizActionCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    from app.services.statistics.statistics_service import StatisticsService

    stats_service = StatisticsService(session)
    analytics = await stats_service.quiz_analytics(uuid.UUID(callback_data.quiz_id))
    text = (
        f"📊 Total attempts: {analytics['total_attempts']}\n"
        f"📈 Average score: {analytics['average_score']}%\n"
        f"⏱ Average time: {analytics['average_duration_seconds']}s"
    )
    await callback.message.answer(text)
    await callback.answer()
