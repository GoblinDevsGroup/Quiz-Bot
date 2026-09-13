import uuid

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.keyboards.quiz_bank import quiz_detail_keyboard
from app.database.models import User
from app.i18n import Translator
from app.services.quiz.quiz_service import QuizService

router = Router(name="start")


@router.message(CommandStart(deep_link=True))
async def start_with_deeplink(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: User,
    translator: Translator,
    redis: Redis,
    state: FSMContext,
) -> None:
    payload = command.args or ""
    if payload.startswith("schedq_"):
        await _handle_schedule_deeplink(message, payload, session, user, translator, state)
        return

    if payload.startswith("quiz_"):
        quiz_id_raw = payload.removeprefix("quiz_")
        try:
            quiz_id = uuid.UUID(quiz_id_raw)
        except ValueError:
            await message.answer(translator("quiz_not_found"))
            return

        quiz_service = QuizService(session)
        quiz = await quiz_service.get_public_quiz_or_none(quiz_id)
        if quiz is None or not quiz_service.can_view(quiz, user.id):
            await message.answer(translator("quiz_not_found"))
            return

        if message.chat.type in ("group", "supergroup"):
            # Reached via the "Guruhda testni boshlash" button's native
            # `?startgroup=quiz_<id>` deep link: Telegram already handled group
            # selection and, if needed, added the bot here before sending this
            # /start — no bot-side "pick a group" step required.
            from app.bot.handlers.group_quiz import begin_group_session

            await begin_group_session(message.bot, redis, quiz, message.chat.id, user.locale, translator)
            return

        # Make sure the persistent main-menu keyboard is set even for a user's
        # very first interaction (arriving straight via a shared deep link).
        await message.answer(translator("start_welcome", name=user.display_name), reply_markup=main_menu_keyboard(user.locale))

        text = translator(
            "quiz_card",
            title=quiz.title,
            creator=quiz.creator.display_name,
            count=quiz.question_count,
            difficulty=quiz.difficulty,
            attempts=quiz.attempts_count,
        )
        bot_info = await message.bot.get_me()
        await message.answer(text, reply_markup=quiz_detail_keyboard(user.locale, str(quiz.id), bot_info.username))
        return

    await start_plain(message, session, user, translator)


async def _handle_schedule_deeplink(
    message: Message, payload: str, session: AsyncSession, user: User, translator: Translator, state: FSMContext
) -> None:
    """Reached via the "Guruhda rejalashtirish" button's `?startgroup=schedq_<id>`
    deep link. Only a group admin/creator can schedule; the actual date/time
    is collected as a follow-up plain-text reply (see schedule_quiz.py),
    scoped to this admin+chat by aiogram's own FSM key."""
    quiz_id_raw = payload.removeprefix("schedq_")
    try:
        quiz_id = uuid.UUID(quiz_id_raw)
    except ValueError:
        await message.answer(translator("quiz_not_found"))
        return

    quiz_service = QuizService(session)
    quiz = await quiz_service.get_public_quiz_or_none(quiz_id)
    if quiz is None or not quiz_service.can_view(quiz, user.id):
        await message.answer(translator("quiz_not_found"))
        return

    if message.chat.type not in ("group", "supergroup"):
        await message.answer(translator("schedule_group_only"))
        return

    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    except Exception:
        member = None
    if member is None or member.status not in ("administrator", "creator"):
        await message.answer(translator("group_stop_admins_only"))
        return

    from app.bot.states.schedule_states import ScheduleStates

    await state.set_state(ScheduleStates.awaiting_datetime)
    await state.update_data(quiz_id=str(quiz.id), chat_id=message.chat.id, locale=user.locale)
    await message.answer(translator("schedule_prompt_datetime"))


@router.message(CommandStart())
async def start_plain(message: Message, session: AsyncSession, user: User, translator: Translator) -> None:
    if message.chat.type in ("group", "supergroup"):
        # The personal welcome + persistent main-menu keyboard must never be
        # posted into a group: it dumps every private menu button (quiz bank,
        # my quizzes, profile, ...) into a chat everyone can see and tap.
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        bot_info = await message.bot.get_me()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=translator("open_private_chat_button"), url=f"https://t.me/{bot_info.username}")]]
        )
        await message.answer(translator("group_private_only"), reply_markup=kb)
        return

    name = user.display_name
    await message.answer(
        translator("start_welcome", name=name),
        reply_markup=main_menu_keyboard(user.locale),
    )
