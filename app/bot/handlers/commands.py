from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.reply_menu import open_create_quiz, open_language, open_my_quizzes
from app.database.models import User
from app.database.repositories.attempt_repository import AttemptRepository
from app.i18n import Translator

router = Router(name="commands")


@router.message(Command("newquiz"))
async def cmd_newquiz(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    await open_create_quiz(message, state, translator, user)


@router.message(Command("quizzes"))
async def cmd_quizzes(message: Message, state: FSMContext, session: AsyncSession, translator: Translator, user: User) -> None:
    await open_my_quizzes(message, state, session, translator, user)


@router.message(Command("lang"))
async def cmd_lang(message: Message, state: FSMContext, translator: Translator) -> None:
    await open_language(message, state, translator)


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    # Any in-progress creation/browsing flow is tracked in FSM; any in-progress
    # quiz attempt is tracked in the database (native-poll answers don't touch
    # FSM at all), so both need to be cleared for /stop to actually stop
    # whatever the user considers "active".
    await state.clear()

    attempt_repo = AttemptRepository(session)
    attempt = await attempt_repo.get_active_for_user(user.id)
    if attempt is None:
        await message.answer(translator("stop_no_active_quiz"))
        return

    await attempt_repo.finish(attempt)
    await message.answer(translator("stop_confirmed"))
