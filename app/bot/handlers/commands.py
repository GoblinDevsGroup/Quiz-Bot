import uuid

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.reply_menu import open_create_quiz, open_language, open_my_quizzes
from app.database.models import User
from app.database.repositories.attempt_repository import AttemptRepository
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator
from app.services.quiz.attempt_service import AttemptService

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
async def cmd_stop(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator, redis: Redis
) -> None:
    # Any in-progress creation/browsing flow is tracked in FSM; any in-progress
    # quiz attempt is tracked in the database (native-poll answers don't touch
    # FSM at all), so both need to be cleared for /stop to actually stop
    # whatever the user considers "active".
    await state.clear()

    if message.chat.type in ("group", "supergroup"):
        if await _try_stop_group_quiz(message, session, redis):
            return

    attempt_repo = AttemptRepository(session)
    attempt = await attempt_repo.get_active_for_user(user.id)
    if attempt is None:
        await message.answer(translator("stop_no_active_quiz"))
        return

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(attempt.quiz_id)

    attempt_service = AttemptService(session)
    await attempt_service.finish_attempt(attempt)
    await message.answer(translator("stop_confirmed"))

    if quiz is not None:
        from app.bot.handlers.quiz_taking import _send_result

        await _send_result(message.bot, message.chat.id, attempt, quiz, user.locale, translator)


async def _try_stop_group_quiz(message: Message, session: AsyncSession, redis: Redis) -> bool:
    """Stops the active group quiz session in this chat if the caller is an
    admin, announcing final results the same way the inline "Stop" button
    does. Returns True if it handled the /stop (whether it actually stopped
    anything or just told the caller they can't), False to fall through to
    the solo-attempt /stop logic below."""
    from app.bot.handlers.group_quiz import finish_group_quiz
    from app.services.quiz import group_session_service as gs

    session_id = await gs.get_active_session_id_for_chat(redis, message.chat.id)
    if session_id is None:
        return False

    group = await gs.get_session(redis, session_id)
    if group is None or group.status != "in_progress":
        return False

    translator = Translator(group.locale)
    if message.from_user is None:
        return False
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    except Exception:
        return False
    if member.status not in ("administrator", "creator"):
        await message.answer(translator("group_stop_admins_only"))
        return True

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(group.quiz_id))
    if quiz is None:
        return False

    await finish_group_quiz(message.bot, redis, group, quiz, stopped_by=message.from_user.full_name)
    return True
