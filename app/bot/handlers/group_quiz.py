import asyncio
import html as html_lib
import uuid

from aiogram import Bot, Router
from aiogram.types import CallbackQuery, Poll
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import GroupReadyCB
from app.bot.keyboards.group_quiz import group_ready_keyboard
from app.core.logging import get_logger
from app.database.repositories.quiz_repository import QuizRepository
from app.database.session import async_session_factory
from app.i18n import Translator
from app.services.quiz import group_session_service as gs
from app.services.quiz.countdown import play_countdown
from app.services.quiz.quiz_presentation import summary_line

logger = get_logger(__name__)

router = Router(name="group_quiz")


async def begin_group_session(
    bot: Bot, redis: Redis, quiz, chat_id: int, locale: str, translator: Translator, notify_conflict: bool = True
) -> bool:
    """Entry point for starting a quiz in a group — reached via Telegram's
    native `?startgroup=` deep link (handled in start.py's CommandStart
    handler) for an immediate start, or via arq's scheduled_group_quiz_task
    for a pre-planned one. No custom "pick a group" step here: Telegram's
    own group picker already did that job before this ever runs.

    Returns False without starting anything if the chat already has a
    waiting/in-progress session — the scheduler (not this function) is
    responsible for retrying later in that case."""
    existing_id = await gs.get_active_session_id_for_chat(redis, chat_id)
    if existing_id is not None:
        existing = await gs.get_session(redis, existing_id)
        if existing is not None and existing.status in ("waiting", "in_progress"):
            if notify_conflict:
                await bot.send_message(chat_id, translator("group_session_already_active"))
            return False

    session_id = await gs.reserve_session_id(redis, str(quiz.id), locale)
    group = await gs.get_or_create_session(redis, session_id, chat_id)
    await gs.set_active_session_for_chat(redis, chat_id, session_id)

    await bot.send_message(
        chat_id,
        translator(
            "group_waiting_message",
            title=html_lib.escape(quiz.title),
            creator=html_lib.escape(quiz.creator.display_name),
            summary=summary_line(translator, locale, quiz),
            min=gs.MIN_PARTICIPANTS,
            count=0,
        ),
        reply_markup=group_ready_keyboard(locale, group.session_id, 0),
        parse_mode="HTML",
    )
    return True


@router.callback_query(GroupReadyCB.filter())
async def handle_group_ready(
    callback: CallbackQuery, callback_data: GroupReadyCB, session: AsyncSession, redis: Redis
) -> None:
    group = await gs.get_session(redis, callback_data.session_id)
    if group is None or callback.message is None:
        await callback.answer(show_alert=True)
        return

    translator = Translator(group.locale)
    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(group.quiz_id))
    if quiz is None:
        await callback.answer(translator("group_quiz_not_found"), show_alert=True)
        return

    user = callback.from_user
    username = f"@{user.username}" if user.username else user.full_name
    already_ready = str(user.id) in group.participants

    if group.status != "waiting":
        # Quiz already started/finished — joining now wouldn't do anything
        # useful, so just acknowledge without changing state.
        await callback.answer()
        return

    group.add_participant(user.id, username)
    await gs.save_session(redis, group)
    await callback.answer(translator("group_already_ready_toast") if already_ready else translator("group_ready_toast"))

    ready_count = group.ready_count()
    try:
        await callback.message.edit_text(
            translator(
                "group_waiting_message",
                title=html_lib.escape(quiz.title),
                creator=html_lib.escape(quiz.creator.display_name),
                summary=summary_line(translator, group.locale, quiz),
                min=gs.MIN_PARTICIPANTS,
                count=ready_count,
            ),
            reply_markup=group_ready_keyboard(group.locale, group.session_id, ready_count),
            parse_mode="HTML",
        )
    except Exception:
        pass

    if ready_count >= gs.MIN_PARTICIPANTS:
        group.start()
        await gs.save_session(redis, group)
        await play_countdown(callback.bot, group.chat_id)
        await send_group_question(callback.bot, redis, group, quiz, 0)


async def send_group_question(bot: Bot, redis: Redis, group: gs.GroupSession, quiz, index: int) -> None:
    if index >= quiz.question_count:
        await finish_group_quiz(bot, redis, group, quiz)
        return

    group.begin_question(index)
    await gs.save_session(redis, group)

    question = quiz.questions[index]
    poll_question = f"[{index + 1}/{quiz.question_count}] {question.text}"[:300]
    options = [opt.text[:100] for opt in question.options]
    open_period = max(5, min(600, quiz.time_limit_seconds or gs.DEFAULT_GROUP_TIME_LIMIT_SECONDS))

    message = await bot.send_poll(
        chat_id=group.chat_id,
        question=poll_question,
        options=options,
        type="quiz",
        correct_option_id=question.correct_option_index,
        is_anonymous=False,
        explanation=(question.explanation or "")[:200] or None,
        open_period=open_period,
    )
    await gs.map_poll_to_session(redis, message.poll.id, group.session_id, index, question.correct_option_index)
    logger.info("group_question_sent", session_id=group.session_id, index=index, open_period=open_period)

    # Telegram's own "poll auto-closed" update (handled in quiz_taking.py) is
    # not reliable enough to depend on alone for advancing a live group game,
    # so this is scheduled as the guaranteed fallback. Whichever fires first
    # wins; current_question_index acts as the idempotency guard against the
    # other one double-advancing.
    asyncio.create_task(
        _force_advance_after_timeout(bot, message.poll.id, group.session_id, index, message.chat.id, message.message_id, open_period)
    )


async def _force_advance_after_timeout(
    bot: Bot, poll_id: str, session_id: str, index: int, chat_id: int, message_id: int, open_period: int
) -> None:
    await asyncio.sleep(open_period + 2)

    # Needs its own DB session + Redis client: this runs as a detached
    # asyncio task, outside the normal per-update middleware chain that
    # would otherwise inject them.
    from app.core.config import settings
    from redis.asyncio import Redis as RedisClient

    redis = RedisClient.from_url(settings.redis_url)
    try:
        group = await gs.get_session(redis, session_id)
        if group is None or group.current_question_index != index or group.status != "in_progress":
            return  # already advanced via the natural poll-closed path

        logger.warning("group_question_force_advanced", session_id=session_id, index=index)
        try:
            await bot.stop_poll(chat_id, message_id)
        except Exception:
            pass
        await gs.delete_poll_mapping(redis, poll_id)

        async with async_session_factory() as session:
            quiz_repo = QuizRepository(session)
            quiz = await quiz_repo.get_by_id(uuid.UUID(group.quiz_id))
            if quiz is None:
                return
            await advance_or_finish_group(bot, redis, group, quiz)
    finally:
        await redis.aclose()


async def advance_or_finish_group(bot: Bot, redis: Redis, group: gs.GroupSession, quiz) -> None:
    await send_group_question(bot, redis, group, quiz, group.current_question_index + 1)


async def finish_group_quiz(bot: Bot, redis: Redis, group: gs.GroupSession, quiz, stopped_by: str | None = None) -> None:
    group.finish()
    await gs.save_session(redis, group)
    await gs.clear_active_session_for_chat(redis, group.chat_id)

    translator = Translator(group.locale)
    rows = group.leaderboard()
    top_rows = rows[:10]
    medals = ["🥇", "🥈", "🥉"]
    heading = (
        translator("group_stopped_title", admin=html_lib.escape(stopped_by))
        if stopped_by
        else translator("group_finished_title")
    )
    lines = [heading, "", f"<b>{html_lib.escape(quiz.title)}</b>", ""]
    if not rows:
        lines.append(translator("group_no_participants"))
    else:
        for rank, row in enumerate(top_rows, start=1):
            seconds = row["total_time_ms"] / 1000
            rank_label = medals[rank - 1] if rank <= 3 else f"{rank}."
            lines.append(
                translator(
                    "group_leaderboard_row",
                    rank=rank_label,
                    username=html_lib.escape(row["username"]),
                    correct=row["correct"],
                    total=quiz.question_count,
                    time=f"{seconds:.1f}s",
                )
            )
        if len(rows) > len(top_rows):
            lines.append("")
            lines.append(translator("group_leaderboard_more", count=len(rows) - len(top_rows)))
    await bot.send_message(group.chat_id, "\n".join(lines), parse_mode="HTML")
