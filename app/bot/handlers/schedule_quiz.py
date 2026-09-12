import uuid
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.schedule_states import ScheduleStates
from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import Translator

router = Router(name="schedule_quiz")

# The bot's whole audience is Uzbekistan-based, and there's no per-user
# timezone setting anywhere in the data model, so the datetime the admin
# types is always interpreted as Asia/Tashkent (UTC+5, no DST) and converted
# to UTC here for arq's scheduler.
TASHKENT_UTC_OFFSET = timedelta(hours=5)
MIN_LEAD_MINUTES = 2
MAX_LEAD_DAYS = 30
DATETIME_FORMAT = "%Y-%m-%d %H:%M"


@router.message(ScheduleStates.awaiting_datetime, Command("cancel"))
async def cancel_schedule(message: Message, state: FSMContext, translator: Translator) -> None:
    await state.clear()
    await message.answer(translator("schedule_cancelled"))


@router.message(ScheduleStates.awaiting_datetime)
async def receive_schedule_datetime(
    message: Message, state: FSMContext, session: AsyncSession, redis: Redis, translator: Translator
) -> None:
    text = (message.text or "").strip()
    try:
        local_dt = datetime.strptime(text, DATETIME_FORMAT)
    except ValueError:
        await message.answer(translator("schedule_invalid_format"))
        return

    run_at_utc = local_dt.replace(tzinfo=timezone.utc) - TASHKENT_UTC_OFFSET
    now_utc = datetime.now(timezone.utc)
    if run_at_utc < now_utc + timedelta(minutes=MIN_LEAD_MINUTES):
        await message.answer(translator("schedule_must_be_future"))
        return
    if run_at_utc > now_utc + timedelta(days=MAX_LEAD_DAYS):
        await message.answer(translator("schedule_too_far", days=MAX_LEAD_DAYS))
        return

    data = await state.get_data()
    quiz_id_raw = data.get("quiz_id")
    chat_id = data.get("chat_id")
    locale = data.get("locale", "uz")
    if quiz_id_raw is None or chat_id is None:
        await state.clear()
        await message.answer(translator("quiz_not_found"))
        return

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(quiz_id_raw))
    if quiz is None:
        await state.clear()
        await message.answer(translator("quiz_not_found"))
        return

    await redis.enqueue_job(
        "scheduled_group_quiz_task",
        quiz_id=str(quiz.id),
        chat_id=chat_id,
        locale=locale,
        _defer_until=run_at_utc,
        _job_id=f"schedq:{chat_id}:{quiz.id}:{int(run_at_utc.timestamp())}",
    )
    await state.clear()

    await message.answer(translator("schedule_confirmed_group", title=quiz.title, datetime=text))
