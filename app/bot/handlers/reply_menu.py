from aiogram import Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import language_keyboard
from app.bot.keyboards.my_quizzes import my_quizzes_tabs_keyboard
from app.bot.keyboards.profile import create_method_keyboard, profile_keyboard
from app.database.models import User
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator, t
from app.services.quiz.quiz_presentation import build_quiz_list_row

router = Router(name="reply_menu")


class MenuTextFilter(BaseFilter):
    """Matches a plain-text message against the localized label of a persistent
    reply-keyboard button. The label is always rendered in the user's current
    locale, so comparing against t(user.locale, key) is exact."""

    def __init__(self, key: str):
        self.key = key

    async def __call__(self, message: Message, user: User) -> bool:
        return message.text == t(user.locale, self.key)


async def open_quiz_bank(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    from app.bot.handlers.quiz_bank import _render_page

    await state.clear()
    await _render_page(message, session, user, translator, page=1)


async def open_create_quiz(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    await state.clear()
    await message.answer(translator("create_method_prompt"), reply_markup=create_method_keyboard(user.locale))


async def open_my_quizzes(message: Message, state: FSMContext, session: AsyncSession, translator: Translator, user: User) -> None:
    await state.clear()

    quiz_repo = QuizRepository(session)
    quizzes, _total = await quiz_repo.list_by_creator(user.id, status=None, page=1, page_size=100)

    if not quizzes:
        await message.answer(translator("my_quizzes_empty"), reply_markup=my_quizzes_tabs_keyboard(user.locale))
        return

    rows = [build_quiz_list_row(translator, user.locale, idx, quiz) for idx, quiz in enumerate(quizzes, start=1)]
    text = translator("my_quizzes_title") + "\n\n" + "\n\n".join(rows)
    await message.answer(text, reply_markup=my_quizzes_tabs_keyboard(user.locale), parse_mode="HTML")


async def open_profile(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    from app.bot.handlers.menu import build_profile_text

    await state.clear()
    text = await build_profile_text(session, user, translator)
    await message.answer(text, reply_markup=profile_keyboard(user.locale))


async def open_help(message: Message, state: FSMContext, translator: Translator) -> None:
    await state.clear()
    await message.answer(translator("help_text"))


async def open_language(message: Message, state: FSMContext, translator: Translator) -> None:
    await state.clear()
    await message.answer(translator("choose_language"), reply_markup=language_keyboard())


@router.message(MenuTextFilter("menu_quiz_bank"))
async def reply_quiz_bank(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    await open_quiz_bank(message, state, session, user, translator)


@router.message(MenuTextFilter("menu_create_quiz"))
async def reply_create_quiz(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    await open_create_quiz(message, state, translator, user)


@router.message(MenuTextFilter("menu_my_quizzes"))
async def reply_my_quizzes(message: Message, state: FSMContext, session: AsyncSession, translator: Translator, user: User) -> None:
    await open_my_quizzes(message, state, session, translator, user)


@router.message(MenuTextFilter("menu_profile"))
async def reply_profile(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    await open_profile(message, state, session, user, translator)


@router.message(MenuTextFilter("menu_help"))
async def reply_help(message: Message, state: FSMContext, translator: Translator) -> None:
    await open_help(message, state, translator)


@router.message(MenuTextFilter("menu_language"))
async def reply_language(message: Message, state: FSMContext, translator: Translator) -> None:
    await open_language(message, state, translator)
