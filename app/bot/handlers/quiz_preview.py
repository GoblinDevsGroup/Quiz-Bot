import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import QuizActionCB
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.keyboards.manual_creation import (
    parse_shuffle_choice,
    parse_time_limit_choice,
    shuffle_keyboard,
    time_limit_keyboard,
)
from app.bot.states.generation_review_states import GenerationReviewStates
from app.core.enums import QuizVisibility
from app.database.models import User
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator
from app.services.quiz.quiz_service import QuizPermissionError, QuizService

router = Router(name="quiz_preview")


@router.callback_query(QuizActionCB.filter(F.action == "save"))
async def save_ai_quiz(
    callback: CallbackQuery,
    callback_data: QuizActionCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    translator: Translator,
) -> None:
    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(callback_data.quiz_id))
    if quiz is None or quiz.creator_id != user.id:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return

    await state.update_data(review_quiz_id=str(quiz.id))
    await state.set_state(GenerationReviewStates.choosing_time_limit)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(translator("manual_choose_time_limit"), reply_markup=time_limit_keyboard(user.locale))
    await callback.answer()


@router.message(GenerationReviewStates.choosing_time_limit)
async def set_review_time_limit(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    seconds = parse_time_limit_choice(user.locale, (message.text or "").strip())
    if seconds is None:
        await message.answer(translator("manual_choose_time_limit"), reply_markup=time_limit_keyboard(user.locale))
        return

    await state.update_data(time_limit_seconds=seconds)
    await state.set_state(GenerationReviewStates.choosing_shuffle)
    await message.answer(translator("manual_choose_shuffle"), reply_markup=shuffle_keyboard(user.locale))


@router.message(GenerationReviewStates.choosing_shuffle)
async def set_review_shuffle_and_finish(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    choice = parse_shuffle_choice(user.locale, (message.text or "").strip())
    if choice is None:
        await message.answer(translator("manual_choose_shuffle"), reply_markup=shuffle_keyboard(user.locale))
        return
    shuffle_questions, shuffle_options = choice

    data = await state.get_data()
    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(data["review_quiz_id"]))
    if quiz is None or quiz.creator_id != user.id:
        await message.answer(translator("not_owner_error"))
        await state.clear()
        return

    quiz_service = QuizService(session)
    quiz = await quiz_service.update_fields(
        quiz,
        user.id,
        time_limit_seconds=data.get("time_limit_seconds"),
        shuffle_questions=shuffle_questions,
        shuffle_options=shuffle_options,
    )
    await state.clear()

    # Quiz already persisted as draft by the generation pipeline; this just
    # confirms the draft with its final settings applied. Publishing (making
    # it public) is a separate step available from "Mening quizlarim".
    await message.answer(
        translator("my_quiz_card", title=quiz.title, count=quiz.question_count, status=translator("status_draft")),
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(translator("main_menu"), reply_markup=main_menu_keyboard(user.locale))


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
