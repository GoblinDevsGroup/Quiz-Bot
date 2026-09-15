import json
import random
import uuid

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Poll, PollAnswer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import PhotoAnswerCB, QuizActionCB
from app.bot.keyboards.quiz_taking import photo_question_keyboard, result_keyboard
from app.database.models import Quiz, QuizAttempt, User
from app.database.repositories.quiz_repository import QuizRepository
from app.database.repositories.user_repository import UserRepository
from app.i18n import Translator
from app.services.quiz.attempt_service import AttemptService
from app.services.quiz.countdown import play_countdown
from app.services.quiz.quiz_service import QuizService

router = Router(name="quiz_taking")

POLL_MAP_TTL_SECONDS = 6 * 3600
POLL_MAP_KEY = "quiz_poll:{poll_id}"
PHOTO_Q_KEY = "quiz_photo_q:{attempt_id}"
ORDER_KEY = "quiz_order:{attempt_id}"


@router.callback_query(QuizActionCB.filter(F.action == "start"))
async def start_quiz(
    callback: CallbackQuery,
    callback_data: QuizActionCB,
    session: AsyncSession,
    user: User,
    translator: Translator,
    redis: Redis,
) -> None:
    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(callback_data.quiz_id))
    if quiz is None:
        await callback.answer(translator("quiz_not_found"), show_alert=True)
        return

    quiz_service = QuizService(session)
    if not quiz_service.can_view(quiz, user.id):
        await callback.answer(translator("quiz_not_found"), show_alert=True)
        return

    attempt_service = AttemptService(session)
    attempt = await attempt_service.start_attempt(quiz, user.id)

    chat_id = callback.message.chat.id
    await callback.answer()
    await play_countdown(callback.bot, chat_id)
    await _send_question(callback.bot, chat_id, quiz, attempt, 0, redis, user.locale)


async def _get_question_order(redis: Redis, attempt: QuizAttempt, quiz: Quiz) -> list[int]:
    key = ORDER_KEY.format(attempt_id=attempt.id)
    raw = await redis.get(key)
    if raw is not None:
        return json.loads(raw)

    order = list(range(quiz.question_count))
    if quiz.shuffle_questions:
        random.shuffle(order)
    await redis.set(key, json.dumps(order), ex=POLL_MAP_TTL_SECONDS)
    return order


def _shuffle_options(quiz: Quiz, question) -> tuple[list[str], int]:
    """Returns (option_texts_in_display_order, new_correct_index)."""
    option_pairs = list(enumerate(opt.text for opt in question.options))  # [(orig_idx, text), ...]
    if quiz.shuffle_options:
        random.shuffle(option_pairs)
    option_texts = [text for _, text in option_pairs]
    correct_index = next(i for i, (orig_idx, _) in enumerate(option_pairs) if orig_idx == question.correct_option_index)
    return option_texts, correct_index


async def _send_source_link(bot: Bot, chat_id: int, source_link: str | None, locale: str) -> None:
    # Sent as its own message BEFORE the question/poll, so whoever is taking
    # the quiz (privately or in a group) sees the reference material first
    # and then the question it belongs to — rather than a button attached
    # under the question, which is easy to miss once the poll is answered.
    # Just the bare link, with its preview enabled (the bot disables link
    # previews by default everywhere else), so it renders as a real preview.
    if not source_link:
        return
    from aiogram.types import LinkPreviewOptions

    await bot.send_message(chat_id, source_link, link_preview_options=LinkPreviewOptions(is_disabled=False))


async def _send_question(bot: Bot, chat_id: int, quiz: Quiz, attempt: QuizAttempt, index: int, redis: Redis, locale: str = "uz") -> None:
    order = await _get_question_order(redis, attempt, quiz)
    question = quiz.questions[order[index]]
    await _send_source_link(bot, chat_id, question.source_link, locale)
    if question.image_file_id:
        await _send_photo_question(bot, chat_id, quiz, attempt, index, question, redis, locale)
    else:
        await _send_poll_question(bot, chat_id, quiz, attempt, index, question, redis, locale)


async def _send_poll_question(
    bot: Bot, chat_id: int, quiz: Quiz, attempt: QuizAttempt, index: int, question, redis: Redis, locale: str = "uz"
) -> None:
    option_texts, correct_option_id = _shuffle_options(quiz, question)
    option_texts = [t[:100] for t in option_texts]

    # Telegram Bot API hard limits for sendPoll.
    poll_question = f"[{index + 1}/{quiz.question_count}] {question.text}"[:300]
    explanation = (question.explanation or "")[:200] or None

    kwargs = {}
    if quiz.time_limit_seconds:
        kwargs["open_period"] = max(5, min(600, quiz.time_limit_seconds))

    message = await bot.send_poll(
        chat_id=chat_id,
        question=poll_question,
        options=option_texts,
        type="quiz",
        correct_option_id=correct_option_id,
        is_anonymous=False,  # required for poll_answer updates to be delivered at all
        explanation=explanation,
        **kwargs,
    )

    # Map the poll back to this attempt/question so the poll_answer/poll
    # handlers (which only receive poll_id + chosen option) know what to
    # grade. Non-anonymous polls in a private chat only ever have one
    # possible voter, so no extra ownership check is needed here.
    key = POLL_MAP_KEY.format(poll_id=message.poll.id)
    payload = json.dumps(
        {
            "attempt_id": str(attempt.id),
            "quiz_id": str(quiz.id),
            "question_index": index,
            "correct_option_index": correct_option_id,
        }
    )
    await redis.set(key, payload, ex=POLL_MAP_TTL_SECONDS)


async def _send_photo_question(
    bot: Bot, chat_id: int, quiz: Quiz, attempt: QuizAttempt, index: int, question, redis: Redis, locale: str = "uz"
) -> None:
    # Telegram's native Poll object has no media field, so a question with an
    # attached image can't use send_poll — the image and question text would
    # end up as two separate messages. Instead we send ONE message: the photo
    # with the question as its caption, and custom inline A/B/C/D buttons.
    option_texts, correct_option_id = _shuffle_options(quiz, question)
    caption = f"[{index + 1}/{quiz.question_count}] {question.text}"[:1024]
    kb = photo_question_keyboard(str(attempt.id), option_texts)

    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=question.image_file_id,
            caption=caption,
            reply_markup=kb,
        )
    except TelegramBadRequest:
        # The stored value was a link that isn't actually a fetchable image
        # (e.g. a t.me/group link a user pasted instead of a photo URL).
        # Fall back to a plain text question so the link is still visible
        # and the quiz doesn't just stall here.
        await bot.send_message(
            chat_id=chat_id,
            text=f"{caption}\n\n{question.image_file_id}",
            reply_markup=kb,
        )

    # Only one photo-question can be active per attempt at a time, so keying
    # by attempt_id (rather than a poll_id, which doesn't exist here) is
    # sufficient and simpler than the poll-based mapping above.
    key = PHOTO_Q_KEY.format(attempt_id=attempt.id)
    payload = json.dumps(
        {
            "quiz_id": str(quiz.id),
            "question_index": index,
            "correct_option_index": correct_option_id,
        }
    )
    await redis.set(key, payload, ex=POLL_MAP_TTL_SECONDS)


async def _advance_or_finish(
    bot: Bot, session: AsyncSession, redis: Redis, attempt: QuizAttempt, quiz: Quiz, user: User, translator: Translator
) -> None:
    attempt_service = AttemptService(session)
    next_index = attempt.current_question_index
    chat_id = user.telegram_user_id
    if next_index >= quiz.question_count:
        await attempt_service.finish_attempt(attempt)
        await _send_result(bot, chat_id, attempt, quiz, user.locale, translator)
    else:
        await _send_question(bot, chat_id, quiz, attempt, next_index, redis, user.locale)


@router.poll_answer()
async def handle_poll_answer(
    poll_answer: PollAnswer, bot: Bot, session: AsyncSession, redis: Redis, user: User, translator: Translator
) -> None:
    key = POLL_MAP_KEY.format(poll_id=poll_answer.poll_id)
    raw = await redis.get(key)
    if raw is None:
        # Only one poll_answer handler can ever run per update (aiogram stops
        # at the first match), so group-quiz polls are also handled here
        # rather than in their own handler.
        await _try_handle_group_poll_answer(poll_answer, bot, session, redis)
        return

    info = json.loads(raw)
    await redis.delete(key)

    attempt_service = AttemptService(session)
    attempt = await attempt_service.get_attempt(uuid.UUID(info["attempt_id"]))
    if attempt is None or attempt.is_completed or attempt.user_id != user.id:
        return
    if attempt.current_question_index != info["question_index"]:
        return  # stale/duplicate update for a question the attempt already moved past

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(info["quiz_id"]))
    order = await _get_question_order(redis, attempt, quiz)
    question = quiz.questions[order[info["question_index"]]]

    selected_index = poll_answer.option_ids[0] if poll_answer.option_ids else -1
    await attempt_service.submit_answer(attempt, question.id, selected_index, info["correct_option_index"])

    await _advance_or_finish(bot, session, redis, attempt, quiz, user, translator)


@router.callback_query(PhotoAnswerCB.filter())
async def handle_photo_answer(
    callback: CallbackQuery,
    callback_data: PhotoAnswerCB,
    session: AsyncSession,
    redis: Redis,
    user: User,
    translator: Translator,
) -> None:
    key = PHOTO_Q_KEY.format(attempt_id=callback_data.attempt_id)
    raw = await redis.get(key)
    if raw is None:
        await callback.answer(translator("quiz_not_found"), show_alert=True)
        return
    info = json.loads(raw)

    attempt_service = AttemptService(session)
    attempt = await attempt_service.get_attempt(uuid.UUID(callback_data.attempt_id))
    if attempt is None or attempt.is_completed or attempt.user_id != user.id:
        await callback.answer(translator("quiz_not_found"), show_alert=True)
        return
    if attempt.current_question_index != info["question_index"]:
        await callback.answer()  # stale button on a question already answered
        return

    await redis.delete(key)

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(info["quiz_id"]))
    order = await _get_question_order(redis, attempt, quiz)
    question = quiz.questions[order[info["question_index"]]]

    is_correct = callback_data.option_index == info["correct_option_index"]
    await attempt_service.submit_answer(attempt, question.id, callback_data.option_index, info["correct_option_index"])

    result_text = translator("answer_correct") if is_correct else translator("answer_incorrect")
    if question.explanation:
        result_text += f"\n\n{translator('explanation_label')} {question.explanation}"
    # Edit the caption in place (rather than removing buttons + sending a
    # separate follow-up) so the image, question, and result stay as one
    # message — Telegram's native quiz-poll animation isn't available here
    # since Poll objects can't carry media, but this keeps it as cohesive as
    # a photo message can get.
    new_caption = f"{callback.message.caption or ''}\n\n{result_text}"[:1024]  # Telegram's photo caption limit
    await callback.message.edit_caption(caption=new_caption, reply_markup=None)

    await _advance_or_finish(callback.bot, session, redis, attempt, quiz, user, translator)
    await callback.answer()


@router.poll()
async def handle_poll_timeout(poll: Poll, bot: Bot, session: AsyncSession, redis: Redis) -> None:
    # Telegram sends this when a timed poll (open_period) auto-closes. If it
    # closed WITHOUT the user answering, no poll_answer update ever arrives —
    # without this handler the attempt would wait forever for an answer that
    # will never come. `poll_answer` deletes the Redis key first, so if it's
    # still here the user genuinely never answered in time.
    if not poll.is_closed:
        return

    key = POLL_MAP_KEY.format(poll_id=poll.id)
    raw = await redis.get(key)
    if raw is None:
        await _try_handle_group_poll_timeout(poll, bot, session, redis)
        return

    info = json.loads(raw)
    await redis.delete(key)

    attempt_service = AttemptService(session)
    attempt = await attempt_service.get_attempt(uuid.UUID(info["attempt_id"]))
    if attempt is None or attempt.is_completed:
        return
    if attempt.current_question_index != info["question_index"]:
        return

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(info["quiz_id"]))
    order = await _get_question_order(redis, attempt, quiz)
    question = quiz.questions[order[info["question_index"]]]

    # No answer submitted before the timer ran out -> counts as incorrect.
    await attempt_service.submit_answer(attempt, question.id, -1, info["correct_option_index"])

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(attempt.user_id)
    if user is None:
        return
    translator = Translator(user.locale)

    await _advance_or_finish(bot, session, redis, attempt, quiz, user, translator)


def _stars(score_percent: float) -> str:
    filled = round(score_percent / 20)
    return "⭐" * max(0, min(5, filled)) or "☆"


async def _send_result(
    bot: Bot, chat_id: int, attempt: QuizAttempt, quiz: Quiz, locale: str, translator: Translator
) -> None:
    minutes, seconds = divmod(attempt.duration_seconds or 0, 60)
    text = "\n".join(
        [
            translator("quiz_finished"),
            "",
            translator("your_result"),
            translator("correct_count_result", count=attempt.correct_count),
            f"{attempt.score_percent}%",
            "",
            f"{translator('time_label')} {minutes:02d}:{seconds:02d}",
            f"{translator('incorrect_label')} {attempt.incorrect_count}",
            "",
            _stars(attempt.score_percent),
        ]
    )
    await bot.send_message(chat_id, text, reply_markup=result_keyboard(locale, str(quiz.id)))


async def _try_handle_group_poll_answer(poll_answer: PollAnswer, bot: Bot, session: AsyncSession, redis: Redis) -> None:
    from app.services.quiz import group_session_service as gs

    info = await gs.get_poll_mapping(redis, poll_answer.poll_id)
    if info is None:
        return  # not a group poll either — genuinely unknown/expired

    group = await gs.get_session(redis, info["session_id"])
    if group is None or group.current_question_index != info["question_index"]:
        return

    is_correct = bool(poll_answer.option_ids) and poll_answer.option_ids[0] == info["correct_option_index"]
    voter = poll_answer.user
    username = f"@{voter.username}" if voter.username else voter.full_name
    group.record_answer(voter.id, is_correct, username=username)
    await gs.save_session(redis, group)
    # Deliberately does not early-advance even if everyone has now answered:
    # doing so would need the poll's message_id to call stop_poll, which
    # isn't tracked. The question simply runs for its full open_period.


async def _try_handle_group_poll_timeout(poll: Poll, bot: Bot, session: AsyncSession, redis: Redis) -> None:
    from app.bot.handlers.group_quiz import advance_or_finish_group
    from app.services.quiz import group_session_service as gs

    if not poll.is_closed:
        return

    info = await gs.get_poll_mapping(redis, poll.id)
    if info is None:
        return
    await gs.delete_poll_mapping(redis, poll.id)

    group = await gs.get_session(redis, info["session_id"])
    if group is None or group.status != "in_progress" or group.current_question_index != info["question_index"]:
        return

    quiz_repo = QuizRepository(session)
    quiz = await quiz_repo.get_by_id(uuid.UUID(group.quiz_id))
    if quiz is None:
        return
    await advance_or_finish_group(bot, redis, group, quiz)
