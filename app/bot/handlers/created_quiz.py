import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import CreatedQuizActionCB, QuizActionCB
from app.bot.keyboards.my_quizzes import my_quiz_card_keyboard
from app.database.models import User
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator
from app.services.statistics.statistics_service import StatisticsService

router = Router(name="created_quiz")


@router.callback_query(CreatedQuizActionCB.filter(F.action == "start"))
async def start_created_quiz(
    callback: CallbackQuery, callback_data: CreatedQuizActionCB, session: AsyncSession, user: User, translator: Translator, redis
) -> None:
    from app.bot.handlers.quiz_taking import start_quiz

    await start_quiz(callback, QuizActionCB(action="start", quiz_id=callback_data.quiz_id), session, user, translator, redis)


@router.callback_query(CreatedQuizActionCB.filter(F.action == "stats"))
async def created_quiz_stats(callback: CallbackQuery, callback_data: CreatedQuizActionCB, session: AsyncSession) -> None:
    stats_service = StatisticsService(session)
    analytics = await stats_service.quiz_analytics(uuid.UUID(callback_data.quiz_id))
    text = (
        f"📊 Total attempts: {analytics['total_attempts']}\n"
        f"📈 Average score: {analytics['average_score']}%\n"
        f"⏱ Average time: {analytics['average_duration_seconds']}s"
    )
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(CreatedQuizActionCB.filter(F.action == "manage"))
async def manage_created_quiz(
    callback: CallbackQuery, callback_data: CreatedQuizActionCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    # Full field-level editing (rewriting title/questions) isn't implemented;
    # this opens the same manage panel available from "Mening quizlarim"
    # (start/results/share/publish/delete), which covers real quiz upkeep.
    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(callback_data.quiz_id))
    if quiz is None or quiz.creator_id != user.id:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await callback.message.answer(f"⚙️ {quiz.title}", reply_markup=my_quiz_card_keyboard(user.locale, quiz))
    await callback.answer()
