import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import EditQuizCB, QuizActionCB
from app.bot.keyboards.edit_quiz import (
    REORDER_PAGE_SIZE,
    delete_question_list_keyboard,
    edit_menu_keyboard,
    reorder_page_count,
    reorder_question_list_keyboard,
)
from app.bot.keyboards.manual_creation import (
    parse_shuffle_choice,
    parse_time_limit_choice,
    question_collection_keyboard,
    shuffle_keyboard,
    time_limit_keyboard,
)
from app.bot.states.edit_quiz_states import EditQuizStates
from app.core.validation import is_http_url
from app.database.models import User
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator
from app.services.quiz.quiz_service import QuizPermissionError, QuizService

router = Router(name="edit_quiz")


async def _load_owned_quiz(session: AsyncSession, quiz_id: str, user: User):
    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(quiz_id))
    if quiz is None or quiz.creator_id != user.id:
        return None
    return quiz


@router.callback_query(QuizActionCB.filter(F.action == "edit"))
async def open_edit_menu_from_quiz_action(
    callback: CallbackQuery, callback_data: QuizActionCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    await _show_edit_menu(callback, callback_data.quiz_id, session, user, translator)


@router.callback_query(EditQuizCB.filter(F.action == "menu"))
async def open_edit_menu(
    callback: CallbackQuery, callback_data: EditQuizCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    await _show_edit_menu(callback, callback_data.quiz_id, session, user, translator)


async def _show_edit_menu(callback, quiz_id: str, session: AsyncSession, user: User, translator: Translator) -> None:
    quiz = await _load_owned_quiz(session, quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await callback.message.answer(
        translator("edit_menu_title", title=quiz.title), reply_markup=edit_menu_keyboard(user.locale, quiz_id)
    )
    await callback.answer()


@router.callback_query(EditQuizCB.filter(F.action == "back"))
async def back_to_quiz_card(
    callback: CallbackQuery, callback_data: EditQuizCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    from app.bot.keyboards.my_quizzes import my_quiz_card_keyboard

    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await callback.message.edit_text(f"⚙️ {quiz.title}", reply_markup=my_quiz_card_keyboard(user.locale, quiz))
    await callback.answer()


@router.callback_query(EditQuizCB.filter(F.action == "title"))
async def prompt_title(
    callback: CallbackQuery, callback_data: EditQuizCB, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await state.set_state(EditQuizStates.awaiting_title)
    await state.update_data(quiz_id=callback_data.quiz_id)
    await callback.message.answer(translator("edit_prompt_title"))
    await callback.answer()


@router.message(EditQuizStates.awaiting_title)
async def set_new_title(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    title = (message.text or "").strip()[:255]
    if len(title) < 3:
        await message.answer(translator("manual_title_too_short"))
        return

    data = await state.get_data()
    quiz = await _load_owned_quiz(session, data["quiz_id"], user)
    if quiz is None:
        await state.clear()
        await message.answer(translator("not_owner_error"))
        return

    quiz_service = QuizService(session)
    await quiz_service.update_fields(quiz, user.id, title=title)
    await state.clear()
    await message.answer(translator("edit_title_updated"), reply_markup=edit_menu_keyboard(user.locale, str(quiz.id)))


@router.callback_query(EditQuizCB.filter(F.action == "description"))
async def prompt_description(
    callback: CallbackQuery, callback_data: EditQuizCB, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await state.set_state(EditQuizStates.awaiting_description)
    await state.update_data(quiz_id=callback_data.quiz_id)
    await callback.message.answer(translator("edit_prompt_description"))
    await callback.answer()


@router.message(EditQuizStates.awaiting_description, Command("skip"))
async def clear_description(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    await _apply_description(message, state, session, user, translator, None)


@router.message(EditQuizStates.awaiting_description)
async def set_new_description(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    await _apply_description(message, state, session, user, translator, (message.text or "").strip()[:1000])


async def _apply_description(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator, description
) -> None:
    data = await state.get_data()
    quiz = await _load_owned_quiz(session, data["quiz_id"], user)
    if quiz is None:
        await state.clear()
        await message.answer(translator("not_owner_error"))
        return

    quiz_service = QuizService(session)
    await quiz_service.update_fields(quiz, user.id, description=description)
    await state.clear()
    await message.answer(translator("edit_description_updated"), reply_markup=edit_menu_keyboard(user.locale, str(quiz.id)))


@router.callback_query(EditQuizCB.filter(F.action == "time_limit"))
async def prompt_time_limit(
    callback: CallbackQuery, callback_data: EditQuizCB, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await state.set_state(EditQuizStates.awaiting_time_limit)
    await state.update_data(quiz_id=callback_data.quiz_id)
    await callback.message.answer(translator("edit_prompt_time_limit"), reply_markup=time_limit_keyboard(user.locale))
    await callback.answer()


@router.message(EditQuizStates.awaiting_time_limit)
async def set_new_time_limit(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    seconds = parse_time_limit_choice(user.locale, (message.text or "").strip())
    if seconds is None:
        await message.answer(translator("edit_prompt_time_limit"), reply_markup=time_limit_keyboard(user.locale))
        return

    data = await state.get_data()
    quiz = await _load_owned_quiz(session, data["quiz_id"], user)
    if quiz is None:
        await state.clear()
        await message.answer(translator("not_owner_error"), reply_markup=ReplyKeyboardRemove())
        return

    quiz_service = QuizService(session)
    await quiz_service.update_fields(quiz, user.id, time_limit_seconds=seconds)
    await state.clear()
    await message.answer(translator("edit_time_limit_updated"), reply_markup=ReplyKeyboardRemove())
    await message.answer(translator("edit_menu_title", title=quiz.title), reply_markup=edit_menu_keyboard(user.locale, str(quiz.id)))


@router.callback_query(EditQuizCB.filter(F.action == "shuffle"))
async def prompt_shuffle(
    callback: CallbackQuery, callback_data: EditQuizCB, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await state.set_state(EditQuizStates.awaiting_shuffle)
    await state.update_data(quiz_id=callback_data.quiz_id)
    await callback.message.answer(translator("manual_choose_shuffle"), reply_markup=shuffle_keyboard(user.locale))
    await callback.answer()


@router.message(EditQuizStates.awaiting_shuffle)
async def set_new_shuffle(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    choice = parse_shuffle_choice(user.locale, (message.text or "").strip())
    if choice is None:
        await message.answer(translator("manual_choose_shuffle"), reply_markup=shuffle_keyboard(user.locale))
        return
    shuffle_questions, shuffle_options = choice

    data = await state.get_data()
    quiz = await _load_owned_quiz(session, data["quiz_id"], user)
    if quiz is None:
        await state.clear()
        await message.answer(translator("not_owner_error"), reply_markup=ReplyKeyboardRemove())
        return

    quiz_service = QuizService(session)
    await quiz_service.update_fields(quiz, user.id, shuffle_questions=shuffle_questions, shuffle_options=shuffle_options)
    await state.clear()
    await message.answer(translator("edit_shuffle_updated"), reply_markup=ReplyKeyboardRemove())
    await message.answer(translator("edit_menu_title", title=quiz.title), reply_markup=edit_menu_keyboard(user.locale, str(quiz.id)))


@router.callback_query(EditQuizCB.filter(F.action == "add_question"))
async def prompt_add_question(
    callback: CallbackQuery, callback_data: EditQuizCB, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await state.set_state(EditQuizStates.awaiting_new_question_poll)
    await state.update_data(quiz_id=callback_data.quiz_id)
    await callback.message.answer(
        translator("manual_poll_instructions"), reply_markup=question_collection_keyboard(user.locale, has_questions=True)
    )
    await callback.answer()


@router.message(EditQuizStates.awaiting_new_question_poll, F.poll)
async def receive_new_question_poll(message: Message, state: FSMContext, translator: Translator) -> None:
    poll = message.poll
    if poll.type != "quiz" or poll.correct_option_id is None:
        await message.answer(translator("manual_invalid_poll"))
        return

    await state.update_data(
        pending_question={
            "text": poll.question,
            "options": [opt.text for opt in poll.options],
            "correct_option_index": poll.correct_option_id,
            "explanation": poll.explanation or None,
        }
    )
    await state.set_state(EditQuizStates.awaiting_new_question_image)
    await message.answer(translator("manual_ask_image"))


@router.message(EditQuizStates.awaiting_new_question_poll)
async def waiting_for_new_question_poll(message: Message, translator: Translator) -> None:
    await message.answer(translator("manual_waiting_for_poll"))


@router.message(EditQuizStates.awaiting_new_question_image, Command("skip"))
async def skip_new_question_image(message: Message, state: FSMContext, translator: Translator) -> None:
    await _ask_new_question_link(message, state, translator, image_file_id=None)


@router.message(EditQuizStates.awaiting_new_question_image, F.photo)
async def set_new_question_image(message: Message, state: FSMContext, translator: Translator) -> None:
    from app.services.moderation.image_moderation import is_image_flagged

    photo = message.photo[-1]
    file = await message.bot.download(photo.file_id)
    if await is_image_flagged(file.read()):
        await message.answer(translator("manual_image_rejected"))
        return

    await message.answer(translator("manual_image_added"))
    await _ask_new_question_link(message, state, translator, image_file_id=photo.file_id)


@router.message(EditQuizStates.awaiting_new_question_image, F.text)
async def set_new_question_image_link(message: Message, state: FSMContext, translator: Translator) -> None:
    url = (message.text or "").strip()
    if not is_http_url(url):
        await message.answer(translator("manual_ask_image"))
        return
    await message.answer(translator("manual_image_added"))
    await _ask_new_question_link(message, state, translator, image_file_id=url)


@router.message(EditQuizStates.awaiting_new_question_image)
async def invalid_new_question_image(message: Message, translator: Translator) -> None:
    await message.answer(translator("manual_ask_image"))


async def _ask_new_question_link(message: Message, state: FSMContext, translator: Translator, image_file_id) -> None:
    await state.update_data(pending_image_file_id=image_file_id)
    await state.set_state(EditQuizStates.awaiting_new_question_link)
    await message.answer(translator("manual_ask_link"))


@router.message(EditQuizStates.awaiting_new_question_link, Command("skip"))
async def skip_new_question_link(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    await _finalize_new_question(message, state, session, user, translator, source_link=None)


@router.message(EditQuizStates.awaiting_new_question_link, F.text)
async def set_new_question_link(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    url = (message.text or "").strip()
    if not is_http_url(url):
        await message.answer(translator("manual_ask_link"))
        return
    await message.answer(translator("manual_link_added"))
    await _finalize_new_question(message, state, session, user, translator, source_link=url)


@router.message(EditQuizStates.awaiting_new_question_link)
async def invalid_new_question_link(message: Message, translator: Translator) -> None:
    await message.answer(translator("manual_ask_link"))


async def _finalize_new_question(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator, source_link
) -> None:
    data = await state.get_data()
    quiz = await _load_owned_quiz(session, data["quiz_id"], user)
    pending = data.get("pending_question")
    if quiz is None or pending is None:
        await state.clear()
        await message.answer(translator("not_owner_error"), reply_markup=ReplyKeyboardRemove())
        return

    quiz_service = QuizService(session)
    quiz = await quiz_service.add_question(
        quiz,
        user.id,
        text=pending["text"],
        options=pending["options"],
        correct_option_index=pending["correct_option_index"],
        explanation=pending["explanation"],
        image_file_id=data.get("pending_image_file_id"),
        source_link=source_link,
    )
    await state.clear()
    await message.answer(
        translator("edit_question_added", count=quiz.question_count), reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(translator("edit_menu_title", title=quiz.title), reply_markup=edit_menu_keyboard(user.locale, str(quiz.id)))


@router.callback_query(EditQuizCB.filter(F.action == "del_q_list"))
async def show_delete_question_list(
    callback: CallbackQuery, callback_data: EditQuizCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    await callback.message.edit_text(
        translator("edit_delete_question_prompt"), reply_markup=delete_question_list_keyboard(user.locale, quiz)
    )
    await callback.answer()


@router.callback_query(EditQuizCB.filter(F.action == "del_q"))
async def delete_question(
    callback: CallbackQuery, callback_data: EditQuizCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return

    quiz_service = QuizService(session)
    try:
        quiz = await quiz_service.delete_question_by_index(quiz, user.id, callback_data.idx)
    except QuizPermissionError:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    except ValueError:
        await callback.answer(translator("edit_delete_question_last_one"), show_alert=True)
        return

    await callback.answer(translator("edit_question_deleted"))
    await callback.message.edit_text(
        translator("edit_delete_question_prompt"), reply_markup=delete_question_list_keyboard(user.locale, quiz)
    )


@router.callback_query(EditQuizCB.filter(F.action == "noop"))
async def noop_reorder_label(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(EditQuizCB.filter(F.action == "reorder"))
async def show_reorder_list(
    callback: CallbackQuery, callback_data: EditQuizCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    # For this action `idx` carries the page number (0 when opened from the menu).
    await callback.message.edit_text(
        translator("edit_reorder_prompt"),
        reply_markup=reorder_question_list_keyboard(user.locale, quiz, page=callback_data.idx),
    )
    await callback.answer()


@router.callback_query(EditQuizCB.filter(F.action == "del_q_reorder"))
async def delete_question_from_reorder(
    callback: CallbackQuery, callback_data: EditQuizCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return

    quiz_service = QuizService(session)
    try:
        quiz = await quiz_service.delete_question_by_index(quiz, user.id, callback_data.idx)
    except QuizPermissionError:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    except ValueError:
        await callback.answer(translator("edit_delete_question_last_one"), show_alert=True)
        return

    await callback.answer(translator("edit_question_deleted"))
    page = min(callback_data.idx // REORDER_PAGE_SIZE, reorder_page_count(quiz.question_count) - 1)
    await callback.message.edit_text(
        translator("edit_reorder_prompt"), reply_markup=reorder_question_list_keyboard(user.locale, quiz, page=page)
    )


@router.callback_query(EditQuizCB.filter(F.action.in_({"move_up", "move_down"})))
async def move_question(
    callback: CallbackQuery, callback_data: EditQuizCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    quiz = await _load_owned_quiz(session, callback_data.quiz_id, user)
    if quiz is None:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return

    direction = "up" if callback_data.action == "move_up" else "down"
    # Follow the moved question, which may have crossed onto the neighbouring page.
    page = (callback_data.idx + (-1 if direction == "up" else 1)) // REORDER_PAGE_SIZE
    quiz_service = QuizService(session)
    try:
        quiz = await quiz_service.move_question_by_index(quiz, user.id, callback_data.idx, direction)
    except QuizPermissionError:
        await callback.answer(translator("not_owner_error"), show_alert=True)
        return
    except ValueError:
        await callback.answer()
        return

    await callback.answer()
    await callback.message.edit_text(
        translator("edit_reorder_prompt"), reply_markup=reorder_question_list_keyboard(user.locale, quiz, page=page)
    )
