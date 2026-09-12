import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import QuizActionCB
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.core.enums import QuizVisibility
from app.database.models import User
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator
from app.services.quiz.quiz_service import QuizPermissionError, QuizService

router = Router(name="quiz_preview")


@router.callback_query(QuizActionCB.filter(F.action == "save"))
async def save_ai_quiz(
    callback: CallbackQuery, callback_data: QuizActionCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(callback_data.quiz_id))
    if quiz is None or quiz.creator_id != user.id:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return

    # Quiz already persisted as draft by the generation pipeline; saving here
    # just confirms the draft. Publishing (making it public) is a separate step
    # available from "Mening quizlarim".
    await callback.message.edit_text(
        translator("my_quiz_card", title=quiz.title, count=quiz.question_count, status=translator("status_draft")),
    )
    await callback.message.answer(translator("main_menu"), reply_markup=main_menu_keyboard(user.locale))
    await callback.answer()


@router.callback_query(QuizActionCB.filter(F.action == "discard"))
async def discard_ai_quiz(
    callback: CallbackQuery, callback_data: QuizActionCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(callback_data.quiz_id))
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
    await callback.message.answer(translator("main_menu"), reply_markup=main_menu_keyboard(user.locale))
    await callback.answer()


@router.callback_query(QuizActionCB.filter(F.action == "preview_test"))
async def preview_as_test(
    callback: CallbackQuery,
    callback_data: QuizActionCB,
    session: AsyncSession,
    user: User,
    translator: Translator,
    redis,
) -> None:
    # Reuse the normal quiz-taking flow so authors experience it exactly as
    # other users will when they take the published quiz.
    from app.bot.handlers.quiz_taking import start_quiz

    await start_quiz(callback, callback_data, session, user, translator, redis)


@router.callback_query(QuizActionCB.filter(F.action == "regenerate"))
async def regenerate_notice(callback: CallbackQuery, translator: Translator) -> None:
    await callback.answer("Please start a new PDF upload to regenerate.", show_alert=True)
