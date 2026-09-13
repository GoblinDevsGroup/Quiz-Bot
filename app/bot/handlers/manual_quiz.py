import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import CreateMethodCB
from app.bot.keyboards.manual_creation import (
    created_quiz_keyboard,
    grade_keyboard,
    parse_grade_choice,
    parse_shuffle_choice,
    parse_subject_choice,
    parse_time_limit_choice,
    question_collection_keyboard,
    shuffle_keyboard,
    subject_keyboard,
    time_limit_keyboard,
)
from app.bot.states.manual_states import ManualQuizStates
from app.core.enums import QuizStatus, QuizVisibility
from app.database.models import User
from app.database.repositories.category_repository import SUBJECT_KEY_BY_NAME_UZ, CategoryRepository
from app.i18n import Translator
from app.schemas.quiz import QuestionCreate, QuizCreate
from app.services.quiz.quiz_presentation import build_quiz_card_text
from app.services.quiz.quiz_service import QuizService

router = Router(name="manual_quiz")


@router.callback_query(CreateMethodCB.filter(F.method == "manual"))
async def start_manual_flow(callback: CallbackQuery, state: FSMContext, translator: Translator) -> None:
    await state.set_state(ManualQuizStates.choosing_subject)
    await state.update_data(questions=[])
    await callback.message.edit_text(translator("manual_choose_subject_intro"))
    await callback.message.answer(translator("manual_choose_subject"), reply_markup=subject_keyboard())
    await callback.answer()


@router.message(ManualQuizStates.choosing_subject)
async def set_subject(message: Message, state: FSMContext, session: AsyncSession, translator: Translator) -> None:
    name_uz = parse_subject_choice((message.text or "").strip())
    if name_uz is None:
        await message.answer(translator("manual_choose_subject"), reply_markup=subject_keyboard())
        return

    category_repo = CategoryRepository(session)
    subjects = await category_repo.get_canonical_subjects()
    category = next((c for c in subjects if c.name_uz == name_uz), None)
    if category is None:
        await message.answer(translator("manual_choose_subject"), reply_markup=subject_keyboard())
        return

    await state.update_data(category_id=str(category.id), subject_name=category.name_uz)
    await state.set_state(ManualQuizStates.choosing_grade)
    await message.answer(translator("manual_choose_grade"), reply_markup=grade_keyboard())


@router.message(ManualQuizStates.choosing_grade)
async def set_grade(message: Message, state: FSMContext, translator: Translator) -> None:
    grade = parse_grade_choice((message.text or "").strip())
    if grade is None:
        await message.answer(translator("manual_choose_grade"), reply_markup=grade_keyboard())
        return

    await state.update_data(grade=grade)
    await state.set_state(ManualQuizStates.entering_title)

    data = await state.get_data()
    subject_name = data.get("subject_name", "")
    subject_key = SUBJECT_KEY_BY_NAME_UZ.get(subject_name, "general")
    example = translator(f"manual_title_example_{subject_key}")
    await message.answer(
        translator("manual_enter_title_for_subject", subject=subject_name, grade=grade, example=example),
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ManualQuizStates.entering_title)
async def set_title(message: Message, state: FSMContext, translator: Translator) -> None:
    title = (message.text or "").strip()[:255]
    if len(title) < 3:
        await message.answer(translator("manual_title_too_short"))
        return
    await state.update_data(title=title)
    await state.set_state(ManualQuizStates.entering_description)
    await message.answer(translator("manual_enter_description"))


@router.message(ManualQuizStates.entering_description, Command("skip"))
async def skip_description(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    await state.update_data(description=None)
    await _enter_question_collection(message, state, translator, user)


@router.message(ManualQuizStates.entering_description)
async def set_description(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    await state.update_data(description=(message.text or "").strip()[:1000])
    await _enter_question_collection(message, state, translator, user)


async def _enter_question_collection(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    await state.set_state(ManualQuizStates.collecting_questions)
    await message.answer(
        translator("manual_poll_instructions"),
        reply_markup=question_collection_keyboard(user.locale, has_questions=False),
    )


@router.message(ManualQuizStates.collecting_questions, F.poll)
async def receive_question_poll(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    poll = message.poll
    if poll.type != "quiz" or poll.correct_option_id is None:
        await message.answer(translator("manual_invalid_poll"))
        return

    data = await state.get_data()
    questions = data.get("questions", [])
    questions.append(
        {
            "text": poll.question,
            "options": [opt.text for opt in poll.options],
            "correct_option_index": poll.correct_option_id,
            "explanation": poll.explanation or None,
            "image_file_id": None,
        }
    )
    await state.update_data(questions=questions)
    await state.set_state(ManualQuizStates.awaiting_question_image)
    await message.answer(translator("manual_ask_image"))


@router.message(ManualQuizStates.awaiting_question_image, Command("skip"))
async def skip_question_image(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    await _confirm_question_added(message, state, translator, user)


@router.message(ManualQuizStates.awaiting_question_image, F.photo)
async def set_question_image(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    from app.services.moderation.image_moderation import is_image_flagged

    photo = message.photo[-1]  # largest available resolution
    file = await message.bot.download(photo.file_id)
    if await is_image_flagged(file.read()):
        await message.answer(translator("manual_image_rejected"))
        return

    data = await state.get_data()
    questions = data.get("questions", [])
    if questions:
        questions[-1]["image_file_id"] = photo.file_id
        await state.update_data(questions=questions)
    await message.answer(translator("manual_image_added"))
    await _confirm_question_added(message, state, translator, user)


@router.message(ManualQuizStates.awaiting_question_image, F.poll)
async def poll_during_image_wait(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    # User skipped the image implicitly by sending the next question's poll
    # instead of a photo or /skip — auto-skip the pending image and treat
    # this poll as the next question.
    await state.set_state(ManualQuizStates.collecting_questions)
    await receive_question_poll(message, state, translator, user)


@router.message(ManualQuizStates.awaiting_question_image)
async def invalid_question_image(message: Message, translator: Translator) -> None:
    await message.answer(translator("manual_ask_image"))


async def _confirm_question_added(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    data = await state.get_data()
    questions = data.get("questions", [])
    await state.set_state(ManualQuizStates.collecting_questions)
    await message.answer(
        translator("manual_question_added", title=data["title"], count=len(questions)),
        reply_markup=question_collection_keyboard(user.locale, has_questions=True),
    )


@router.message(ManualQuizStates.collecting_questions, Command("undo"))
async def undo_last_question(message: Message, state: FSMContext, translator: Translator) -> None:
    data = await state.get_data()
    questions = data.get("questions", [])
    if not questions:
        await message.answer(translator("manual_undo_nothing"))
        return
    questions.pop()
    await state.update_data(questions=questions)
    await message.answer(translator("manual_undo_removed", count=len(questions)))


@router.message(ManualQuizStates.collecting_questions, Command("done"))
async def finish_questions(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    data = await state.get_data()
    if not data.get("questions"):
        await message.answer(translator("manual_need_at_least_one_question"))
        return
    await state.set_state(ManualQuizStates.choosing_time_limit)
    # Sending a fresh ReplyKeyboardMarkup here replaces "Savol tuzish" in
    # place — no separate removal message needed for this transition.
    await message.answer(translator("manual_choose_time_limit"), reply_markup=time_limit_keyboard(user.locale))


@router.message(ManualQuizStates.collecting_questions)
async def collecting_questions_fallback(message: Message, translator: Translator) -> None:
    # The real flow allows sending intro content before a poll, but we don't
    # have anywhere to persist that against a not-yet-sent question, so just
    # remind the user a poll is what actually gets graded.
    await message.answer(translator("manual_waiting_for_poll"))


@router.message(ManualQuizStates.choosing_time_limit)
async def set_time_limit(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    seconds = parse_time_limit_choice(user.locale, (message.text or "").strip())
    if seconds is None:
        await message.answer(translator("manual_choose_time_limit"), reply_markup=time_limit_keyboard(user.locale))
        return

    await state.update_data(time_limit_seconds=seconds)
    await state.set_state(ManualQuizStates.choosing_shuffle)
    # Sending a fresh ReplyKeyboardMarkup here replaces the time-limit grid
    # in place — no separate removal message needed for this transition.
    await message.answer(translator("manual_choose_shuffle"), reply_markup=shuffle_keyboard(user.locale))


@router.message(ManualQuizStates.choosing_shuffle)
async def set_shuffle_and_finish(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    choice = parse_shuffle_choice(user.locale, (message.text or "").strip())
    if choice is None:
        await message.answer(translator("manual_choose_shuffle"), reply_markup=shuffle_keyboard(user.locale))
        return
    shuffle_questions, shuffle_options = choice

    data = await state.get_data()
    category_id = data.get("category_id")
    quiz_create = QuizCreate(
        title=data["title"],
        description=data.get("description"),
        category_id=uuid.UUID(category_id) if category_id else None,
        grade=data.get("grade"),
        difficulty="mixed",
        visibility=QuizVisibility.private.value,
        language=user.locale,
        time_limit_seconds=data.get("time_limit_seconds"),
        shuffle_questions=shuffle_questions,
        shuffle_options=shuffle_options,
        questions=[QuestionCreate(**q) for q in data.get("questions", [])],
    )

    quiz_service = QuizService(session)
    # Newly created tests wait for admin moderation before they appear in the
    # public quiz bank — created as pending rather than immediately published.
    quiz = await quiz_service.create_manual_quiz(user.id, quiz_create, status=QuizStatus.pending.value)

    await state.clear()

    # This message both gives progress feedback AND clears the persistent
    # reply keyboard (a single message can't carry an inline keyboard AND a
    # ReplyKeyboardRemove at once, so the final card below stays inline-only).
    await message.answer(translator("quiz_finalizing"), reply_markup=ReplyKeyboardRemove())

    from app.bot.handlers.admin_moderation import notify_admins_new_submission

    await notify_admins_new_submission(message.bot, quiz)

    text = build_quiz_card_text(translator, user.locale, quiz, heading=translator("quiz_submitted_title"))
    await message.answer(text, parse_mode="HTML")
