from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import CreateMethodCB
from app.bot.keyboards.manual_creation import (
    created_quiz_keyboard,
    parse_shuffle_choice,
    parse_time_limit_choice,
    question_collection_keyboard,
    shuffle_keyboard,
    time_limit_keyboard,
)
from app.bot.states.manual_states import ManualQuizStates
from app.core.enums import QuizStatus, QuizVisibility
from app.database.models import User
from app.i18n import Translator
from app.schemas.quiz import QuestionCreate, QuizCreate
from app.services.quiz.quiz_presentation import build_quiz_card_text
from app.services.quiz.quiz_service import QuizService

router = Router(name="manual_quiz")


@router.callback_query(CreateMethodCB.filter(F.method == "manual"))
async def start_manual_flow(callback: CallbackQuery, state: FSMContext, translator: Translator) -> None:
    await state.set_state(ManualQuizStates.entering_title)
    await state.update_data(questions=[])
    await callback.message.edit_text(translator("manual_enter_title"))
    await callback.answer()


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
    quiz_create = QuizCreate(
        title=data["title"],
        description=data.get("description"),
        category_id=None,
        difficulty="mixed",
        visibility=QuizVisibility.public.value,
        language=user.locale,
        time_limit_seconds=data.get("time_limit_seconds"),
        shuffle_questions=shuffle_questions,
        shuffle_options=shuffle_options,
        questions=[QuestionCreate(**q) for q in data.get("questions", [])],
    )

    quiz_service = QuizService(session)
    # The real @QuizBot's tests are immediately live/shareable, no separate
    # publish step — matched here by creating already published+public.
    quiz = await quiz_service.create_manual_quiz(user.id, quiz_create, status=QuizStatus.published.value)

    await state.clear()

    # This message both gives progress feedback AND clears the persistent
    # reply keyboard (a single message can't carry an inline keyboard AND a
    # ReplyKeyboardRemove at once, so the final card below stays inline-only).
    await message.answer(translator("quiz_finalizing"), reply_markup=ReplyKeyboardRemove())

    bot_info = await message.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=quiz_{quiz.id}"
    text = build_quiz_card_text(translator, user.locale, quiz, link=link, heading=translator("quiz_created_title"))
    await message.answer(
        text, reply_markup=created_quiz_keyboard(user.locale, str(quiz.id), bot_info.username), parse_mode="HTML"
    )
