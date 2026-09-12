import asyncio
import uuid
from pathlib import Path

from aiogram import Bot
from arq.connections import RedisSettings

from app.bot.keyboards.pdf_generation import preview_keyboard
from app.core.config import settings
from app.core.enums import GenerationStatus
from app.core.logging import configure_logging, get_logger
from app.database.repositories.generation_repository import GenerationRepository
from app.database.repositories.quiz_repository import QuizRepository
from app.database.session import async_session_factory
from app.i18n import Translator
from app.services.ai.factory import get_ai_provider
from app.services.quiz.pdf_pipeline_service import PdfPipelineError, PdfQuizPipelineService

logger = get_logger(__name__)

STATUS_KEY_MAP = {
    GenerationStatus.extracting: "status_extracting",
    GenerationStatus.analyzing: "status_analyzing",
    GenerationStatus.generating: "status_generating",
    GenerationStatus.validating: "status_validating",
    GenerationStatus.completed: "status_completed",
}


async def generate_quiz_from_pdf_task(
    ctx: dict,
    generation_id: str,
    pdf_path: str,
    requester_telegram_id: int,
    chat_id: int,
    status_message_id: int,
    question_count: int,
    difficulty: str,
    question_type: str,
    language: str,
    locale: str,
) -> None:
    bot: Bot = ctx["bot"]
    translator = Translator(locale)

    async def on_progress(status: GenerationStatus) -> None:
        key = STATUS_KEY_MAP.get(status)
        if not key:
            return
        try:
            await bot.edit_message_text(translator(key), chat_id=chat_id, message_id=status_message_id)
        except Exception:
            pass

    async with async_session_factory() as session:
        try:
            from app.database.repositories.user_repository import UserRepository

            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(requester_telegram_id)
            if user is None:
                return

            pipeline = PdfQuizPipelineService(session, get_ai_provider())
            # Bounded ourselves (shorter than arq's own job_timeout) so a hung
            # AI/network call always resolves into a user-facing error message
            # instead of the user staring at a status line forever.
            quiz = await asyncio.wait_for(
                pipeline.run(
                    generation_id=uuid.UUID(generation_id),
                    pdf_path=Path(pdf_path),
                    requester_id=user.id,
                    question_count=question_count,
                    difficulty=difficulty,
                    question_type=question_type,
                    language=language,
                    on_progress=on_progress,
                ),
                timeout=420,
            )
            await session.commit()

            preview_lines = [
                translator("quiz_preview_title", title=quiz.title),
                translator("quiz_preview_stats", count=quiz.question_count, difficulty=quiz.difficulty),
                "",
            ]
            first_q = quiz.questions[0] if quiz.questions else None
            if first_q:
                preview_lines.append(f"1. {first_q.text}")
                for idx, opt in enumerate(first_q.options):
                    letter = chr(ord("A") + idx)
                    preview_lines.append(f"{letter}) {opt.text}")

            await bot.send_message(
                chat_id,
                "\n".join(preview_lines),
                reply_markup=preview_keyboard(locale, str(quiz.id)),
            )

        except PdfPipelineError as exc:
            await session.rollback()
            logger.error("pdf_pipeline_failed", error=str(exc), generation_id=generation_id)
            await bot.send_message(chat_id, translator("status_failed"))
        except asyncio.TimeoutError:
            await session.rollback()
            logger.error("pdf_pipeline_timeout", generation_id=generation_id)
            await bot.send_message(chat_id, translator("status_failed"))
        except Exception as exc:  # never leak internals to the user
            await session.rollback()
            logger.exception("pdf_pipeline_unexpected_error", error=str(exc), generation_id=generation_id)
            await bot.send_message(chat_id, translator("ai_error_generic"))
        except asyncio.CancelledError:
            # The worker itself is being cancelled (e.g. arq's own job_timeout
            # fired, or a shutdown). Best-effort notify, then let it propagate.
            await session.rollback()
            logger.error("pdf_pipeline_cancelled", generation_id=generation_id)
            try:
                await bot.send_message(chat_id, translator("status_failed"))
            except Exception:
                pass
            raise


BROADCAST_RATE_LIMIT_PER_SECOND = 20  # stays comfortably under Telegram's ~30/s cap


async def broadcast_message_task(ctx: dict, text: str, admin_telegram_id: int) -> None:
    bot: Bot = ctx["bot"]

    async with async_session_factory() as session:
        from app.database.repositories.user_repository import UserRepository

        user_repo = UserRepository(session)
        total = await user_repo.count_all()

        sent = 0
        failed = 0
        page = 1
        page_size = 200
        while True:
            users, _total = await user_repo.list_all(page=page, page_size=page_size)
            if not users:
                break
            for user in users:
                if user.is_banned:
                    continue
                try:
                    await bot.send_message(user.telegram_user_id, text)
                    sent += 1
                except Exception as exc:
                    failed += 1
                    logger.warning("broadcast_send_failed", telegram_user_id=user.telegram_user_id, error=str(exc))
                await asyncio.sleep(1 / BROADCAST_RATE_LIMIT_PER_SECOND)
            page += 1

    logger.info("broadcast_complete", total=total, sent=sent, failed=failed)
    try:
        await bot.send_message(
            admin_telegram_id, f"📣 Broadcast complete.\nTotal users: {total}\nSent: {sent}\nFailed: {failed}"
        )
    except Exception:
        pass


# If the group is mid-quiz exactly when a scheduled one is due, we retry
# every minute rather than dropping it — a scheduled quiz an admin planned
# ahead of time shouldn't just silently vanish because of unlucky timing.
# Capped so a chat that's stuck forever doesn't retry forever.
GROUP_BUSY_RETRY_SECONDS = 60
GROUP_BUSY_MAX_RETRIES = 120  # ~2 hours of retrying


async def scheduled_group_quiz_task(
    ctx: dict, quiz_id: str, chat_id: int, locale: str, retry_count: int = 0
) -> None:
    """Fires at the exact time a group admin scheduled via the "Guruhda
    rejalashtirish" flow (see schedule_quiz.py) — `_defer_until` on the
    first enqueue call is what makes arq hold the job until then. `ctx["redis"]`
    is arq's own pool, which is the same Redis instance group sessions are
    stored in, so this reuses begin_group_session unchanged."""
    bot: Bot = ctx["bot"]
    redis = ctx["redis"]
    translator = Translator(locale)

    from app.bot.handlers.group_quiz import begin_group_session

    async with async_session_factory() as session:
        quiz_repo = QuizRepository(session)
        quiz = await quiz_repo.get_by_id(uuid.UUID(quiz_id))
        if quiz is None:
            logger.warning("scheduled_group_quiz_missing", quiz_id=quiz_id, chat_id=chat_id)
            return
        quiz_title = quiz.title

        try:
            # Only the very first attempt announces the "another quiz is
            # running" conflict — silent on retries so the chat isn't spammed
            # once a minute while the earlier quiz plays out.
            started = await begin_group_session(
                bot, redis, quiz, chat_id, locale, translator, notify_conflict=(retry_count == 0)
            )
        except Exception as exc:
            logger.warning("scheduled_group_quiz_failed", chat_id=chat_id, quiz_id=quiz_id, error=str(exc))
            return

    if started:
        return

    if retry_count >= GROUP_BUSY_MAX_RETRIES:
        logger.warning("scheduled_group_quiz_gave_up", chat_id=chat_id, quiz_id=quiz_id)
        try:
            await bot.send_message(chat_id, translator("schedule_gave_up", title=quiz_title))
        except Exception:
            pass
        return

    await redis.enqueue_job(
        "scheduled_group_quiz_task",
        quiz_id=quiz_id,
        chat_id=chat_id,
        locale=locale,
        retry_count=retry_count + 1,
        _defer_by=GROUP_BUSY_RETRY_SECONDS,
        _job_id=f"schedq_retry:{chat_id}:{quiz_id}:{retry_count + 1}:{uuid.uuid4().hex[:8]}",
    )


async def startup(ctx: dict) -> None:
    configure_logging()
    ctx["bot"] = Bot(token=settings.bot_token)
    logger.info("worker_started")


async def shutdown(ctx: dict) -> None:
    bot: Bot = ctx.get("bot")
    if bot:
        await bot.session.close()
    logger.info("worker_stopped")


class WorkerSettings:
    functions = [generate_quiz_from_pdf_task, broadcast_message_task, scheduled_group_quiz_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 480  # kept slightly above the task's own 420s wait_for so our
    # handler's TimeoutError fires first and always leaves the user a message
