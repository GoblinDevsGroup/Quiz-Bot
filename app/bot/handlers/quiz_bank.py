import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import MenuCB, QuizActionCB, QuizBankCB
from app.bot.keyboards.quiz_bank import (
    filters_keyboard,
    grade_picker_keyboard,
    pagination_keyboard,
    quiz_bank_card_keyboard,
    quiz_detail_keyboard,
    subject_picker_keyboard,
)
from app.bot.states.browse_states import BrowseStates
from app.database.models import User
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator

router = Router(name="quiz_bank")

PAGE_SIZE = 1  # one quiz card per "page" for a clean swipe-through browsing experience


async def _send_or_edit(target, text: str, kb) -> None:
    """Works whether triggered by an inline-button callback (edits in place)
    or by a persistent reply-keyboard button tap, a plain Message (sends fresh)."""
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


async def _render_subjects(target, session: AsyncSession, user: User, translator: Translator) -> None:
    category_repo = CategoryRepository(session)
    subjects = await category_repo.get_canonical_subjects()
    await _send_or_edit(target, translator("quiz_bank_choose_subject"), subject_picker_keyboard(user.locale, subjects))


@router.callback_query(MenuCB.filter(F.action == "quiz_bank"))
async def open_quiz_bank(callback: CallbackQuery, session: AsyncSession, user: User, translator: Translator) -> None:
    await _render_subjects(callback, session, user, translator)
    await callback.answer()


@router.callback_query(QuizBankCB.filter(F.action == "subjects"))
async def back_to_subjects(callback: CallbackQuery, session: AsyncSession, user: User, translator: Translator) -> None:
    await _render_subjects(callback, session, user, translator)
    await callback.answer()


@router.callback_query(QuizBankCB.filter(F.action == "subject"))
async def choose_subject(
    callback: CallbackQuery, callback_data: QuizBankCB, user: User, translator: Translator
) -> None:
    await callback.message.edit_text(
        translator("quiz_bank_choose_grade"), reply_markup=grade_picker_keyboard(user.locale, callback_data.category_id)
    )
    await callback.answer()


@router.callback_query(QuizBankCB.filter(F.action == "grade"))
async def choose_grade(
    callback: CallbackQuery, callback_data: QuizBankCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    await _render_page(
        callback,
        session,
        user,
        translator,
        page=1,
        category_id=callback_data.category_id,
        grade=callback_data.grade or None,
    )
    await callback.answer()


@router.callback_query(QuizBankCB.filter(F.action == "list"))
async def paginate_quiz_bank(
    callback: CallbackQuery, callback_data: QuizBankCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    await _render_page(
        callback,
        session,
        user,
        translator,
        page=callback_data.page,
        sort=callback_data.sort,
        category_id=callback_data.category_id,
        grade=callback_data.grade or None,
    )
    await callback.answer()


async def _render_page(
    target,
    session: AsyncSession,
    user: User,
    translator: Translator,
    page: int,
    sort: str = "newest",
    category_id: str | None = None,
    grade: int | None = None,
) -> None:
    repo = QuizRepository(session)
    quizzes, total = await repo.list_public(
        page=page,
        page_size=PAGE_SIZE,
        sort=sort,
        category_id=uuid.UUID(category_id) if category_id else None,
        grade=grade,
    )

    if not quizzes:
        from app.bot.keyboards.main_menu import back_to_main_keyboard

        await _send_or_edit(target, translator("quiz_bank_empty"), back_to_main_keyboard(user.locale))
        return

    quiz = quizzes[0]
    text = translator(
        "quiz_card",
        title=quiz.title,
        creator=quiz.creator.display_name,
        count=quiz.question_count,
        difficulty=quiz.difficulty,
        attempts=quiz.attempts_count,
    )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    kb = pagination_keyboard(user.locale, page, total_pages, sort=sort, category_id=category_id, grade=grade or 0)
    # Merge in start/details buttons above pagination
    card_kb = quiz_bank_card_keyboard(user.locale, quiz, page)
    kb.inline_keyboard = card_kb.inline_keyboard + kb.inline_keyboard

    await _send_or_edit(target, text, kb)


@router.callback_query(QuizActionCB.filter(F.action == "details"))
async def show_quiz_details(
    callback: CallbackQuery, callback_data: QuizActionCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    repo = QuizRepository(session)
    quiz = await repo.get_by_id(uuid.UUID(callback_data.quiz_id))
    if quiz is None:
        await callback.answer(translator("quiz_not_found"), show_alert=True)
        return

    lines = [f"🧠 {quiz.title}", "", quiz.description or "", "", f"👤 {quiz.creator.display_name}"]
    lines.append(f"📚 {quiz.question_count} | 🎯 {quiz.difficulty} | 👥 {quiz.attempts_count}")
    lines.append(f"⭐ {quiz.average_rating}")
    bot_info = await callback.bot.get_me()
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=quiz_detail_keyboard(user.locale, str(quiz.id), bot_info.username)
    )
    await callback.answer()


@router.callback_query(QuizBankCB.filter(F.action == "search"))
async def prompt_search(callback: CallbackQuery, callback_data: QuizBankCB, state: FSMContext, translator: Translator) -> None:
    await state.set_state(BrowseStates.searching)
    await state.update_data(category_id=callback_data.category_id, grade=callback_data.grade)
    await callback.message.edit_text(translator("search_prompt"))
    await callback.answer()


@router.callback_query(QuizBankCB.filter(F.action == "goto"))
async def prompt_page_number(
    callback: CallbackQuery, callback_data: QuizBankCB, state: FSMContext, translator: Translator
) -> None:
    total_pages = max(1, callback_data.page)
    if total_pages <= 1:
        await callback.answer()
        return
    await state.set_state(BrowseStates.awaiting_page_number)
    await state.update_data(total_pages=total_pages, sort=callback_data.sort, category_id=callback_data.category_id, grade=callback_data.grade)
    await callback.message.answer(translator("goto_page_prompt", total=total_pages))
    await callback.answer()


@router.message(BrowseStates.awaiting_page_number)
async def handle_page_number(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    data = await state.get_data()
    total_pages = data.get("total_pages", 1)
    sort = data.get("sort", "newest")

    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= total_pages):
        await message.answer(translator("goto_page_invalid", total=total_pages))
        return

    await state.clear()
    await _render_page(
        message, session, user, translator, page=int(text), sort=sort, category_id=data.get("category_id"), grade=data.get("grade") or None
    )


@router.message(BrowseStates.searching)
async def handle_search(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    data = await state.get_data()
    await state.clear()
    category_id = data.get("category_id")
    grade = data.get("grade") or None
    repo = QuizRepository(session)
    quizzes, total = await repo.list_public(
        page=1,
        page_size=5,
        search=message.text.strip(),
        category_id=uuid.UUID(category_id) if category_id else None,
        grade=grade,
    )

    if not quizzes:
        await message.answer(translator("quiz_bank_empty"))
        return

    for quiz in quizzes:
        text = translator(
            "quiz_card",
            title=quiz.title,
            creator=quiz.creator.display_name,
            count=quiz.question_count,
            difficulty=quiz.difficulty,
            attempts=quiz.attempts_count,
        )
        await message.answer(text, reply_markup=quiz_bank_card_keyboard(user.locale, quiz, 1))


@router.callback_query(QuizBankCB.filter(F.action == "filters"))
async def show_filters_menu(
    callback: CallbackQuery, callback_data: QuizBankCB, user: User, translator: Translator
) -> None:
    await callback.message.edit_text(
        translator("filters_menu_title"),
        reply_markup=filters_keyboard(user.locale, callback_data.sort, callback_data.category_id, callback_data.grade),
    )
    await callback.answer()
