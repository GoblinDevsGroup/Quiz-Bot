import json
import time
import uuid
from typing import Optional

from redis.asyncio import Redis

SESSION_TTL_SECONDS = 6 * 3600
MIN_PARTICIPANTS = 2
DEFAULT_GROUP_TIME_LIMIT_SECONDS = 30

SESSION_KEY = "group_session:{session_id}"
SESSION_QUIZ_KEY = "group_session_quiz:{session_id}"
GROUP_POLL_KEY = "group_poll:{poll_id}"
ACTIVE_CHAT_SESSION_KEY = "group_active_session:{chat_id}"
SESSION_LOCK_KEY = "group_session_lock:{session_id}"
QUESTION_CLAIM_KEY = "group_session_q:{session_id}:{index}"
FINISH_CLAIM_KEY = "group_session_finished:{session_id}"

# Deletes the chat's active-session pointer only if it still points at the
# session we decided was stale, so a concurrent /start's fresh claim is never
# wiped out by another /start that read the old value a moment earlier.
_COMPARE_AND_DELETE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class GroupSession:
    """Thin wrapper around a JSON blob stored in Redis. Group quiz play has no
    single fixed user, so it can't reuse the QuizAttempt (per-user) DB model —
    this keeps a lightweight ad-hoc session instead of a larger schema change."""

    def __init__(self, session_id: str, data: dict):
        self.session_id = session_id
        self.data = data

    @property
    def quiz_id(self) -> str:
        return self.data["quiz_id"]

    @property
    def chat_id(self) -> int:
        return self.data["chat_id"]

    @property
    def locale(self) -> str:
        return self.data.get("locale", "uz")

    @property
    def status(self) -> str:
        return self.data["status"]

    @property
    def current_question_index(self) -> int:
        return self.data["current_question_index"]

    @property
    def participants(self) -> dict:
        return self.data["participants"]

    def add_participant(self, user_id: int, username: str) -> None:
        uid = str(user_id)
        if uid not in self.data["participants"]:
            self.data["participants"][uid] = {
                "username": username,
                "correct": 0,
                "total_time_ms": 0,
                "answered_this_question": False,
            }

    def ready_count(self) -> int:
        return len(self.data["participants"])

    def start(self) -> None:
        self.data["status"] = "in_progress"
        self.data["current_question_index"] = 0

    def begin_question(self, index: int) -> None:
        self.data["current_question_index"] = index
        self.data["question_started_at"] = time.time()
        for p in self.data["participants"].values():
            p["answered_this_question"] = False

    def record_answer(self, user_id: int, is_correct: bool, username: Optional[str] = None) -> None:
        uid = str(user_id)
        p = self.data["participants"].get(uid)
        if p is None:
            # The poll is visible to the whole group and anyone can answer it
            # even without tapping "✅ Tayyor/Ready" first — count them on the
            # leaderboard too instead of silently dropping their answer.
            self.add_participant(user_id, username or uid)
            p = self.data["participants"][uid]
        if p["answered_this_question"]:
            return
        p["answered_this_question"] = True
        if is_correct:
            p["correct"] += 1
        elapsed_ms = int((time.time() - self.data["question_started_at"]) * 1000)
        p["total_time_ms"] += elapsed_ms

    def all_answered(self) -> bool:
        participants = self.data["participants"]
        if not participants:
            return False
        return all(p["answered_this_question"] for p in participants.values())

    def finish(self) -> None:
        self.data["status"] = "finished"

    def leaderboard(self) -> list[dict]:
        rows = [{"user_id": uid, **p} for uid, p in self.data["participants"].items()]
        rows.sort(key=lambda r: (-r["correct"], r["total_time_ms"]))
        return rows


async def reserve_session_id(redis: Redis, quiz_id: str, locale: str) -> str:
    """Called at inline-query-answer time, before any group chat/message
    exists yet — we only know the quiz and can't know the chat_id until
    someone actually taps 'ready' inside the posted message. Stashing the
    quiz id (and locale) under the session id now lets the first ready-tap
    create the real session without needing the quiz id in callback_data."""
    session_id = str(uuid.uuid4())
    await redis.set(SESSION_QUIZ_KEY.format(session_id=session_id), json.dumps({"quiz_id": quiz_id, "locale": locale}), ex=SESSION_TTL_SECONDS)
    return session_id


async def get_or_create_session(redis: Redis, session_id: str, chat_id: int) -> Optional[GroupSession]:
    existing = await get_session(redis, session_id)
    if existing is not None:
        return existing

    raw = await redis.get(SESSION_QUIZ_KEY.format(session_id=session_id))
    if raw is None:
        return None
    reserved = json.loads(raw)

    data = {
        "quiz_id": reserved["quiz_id"],
        "locale": reserved["locale"],
        "chat_id": chat_id,
        "status": "waiting",
        "current_question_index": -1,
        "question_started_at": 0.0,
        "participants": {},
    }
    session = GroupSession(session_id, data)
    await save_session(redis, session)
    return session


async def get_session(redis: Redis, session_id: str) -> Optional[GroupSession]:
    raw = await redis.get(SESSION_KEY.format(session_id=session_id))
    if raw is None:
        return None
    return GroupSession(session_id, json.loads(raw))


async def save_session(redis: Redis, session: GroupSession) -> None:
    await redis.set(SESSION_KEY.format(session_id=session.session_id), json.dumps(session.data), ex=SESSION_TTL_SECONDS)


async def map_poll_to_session(redis: Redis, poll_id: str, session_id: str, question_index: int, correct_option_index: int) -> None:
    payload = json.dumps(
        {"session_id": session_id, "question_index": question_index, "correct_option_index": correct_option_index}
    )
    await redis.set(GROUP_POLL_KEY.format(poll_id=poll_id), payload, ex=SESSION_TTL_SECONDS)


async def get_poll_mapping(redis: Redis, poll_id: str) -> Optional[dict]:
    raw = await redis.get(GROUP_POLL_KEY.format(poll_id=poll_id))
    if raw is None:
        return None
    return json.loads(raw)


async def delete_poll_mapping(redis: Redis, poll_id: str) -> None:
    await redis.delete(GROUP_POLL_KEY.format(poll_id=poll_id))


async def get_active_session_id_for_chat(redis: Redis, chat_id: int) -> Optional[str]:
    """Guards against a group ending up with two overlapping quiz sessions —
    e.g. the startgroup link or /start command being triggered twice."""
    raw = await redis.get(ACTIVE_CHAT_SESSION_KEY.format(chat_id=chat_id))
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw


async def set_active_session_for_chat(redis: Redis, chat_id: int, session_id: str) -> None:
    await redis.set(ACTIVE_CHAT_SESSION_KEY.format(chat_id=chat_id), session_id, ex=SESSION_TTL_SECONDS)


async def try_claim_active_session_for_chat(redis: Redis, chat_id: int, session_id: str) -> bool:
    """Atomically claims the chat's "there's a session running" slot.

    get_active_session_id_for_chat + set_active_session_for_chat used to be
    two separate round-trips, so two /start updates for the same group
    arriving close together (Telegram redelivers on webhook retries, and
    people double-tap the deep-link button) could both see no active session,
    and both go on to create one — the group ends up with two waiting
    messages and, once each fills up, two quizzes running at once. SET NX
    makes the claim a single atomic operation: only the first caller gets
    True."""
    return bool(
        await redis.set(ACTIVE_CHAT_SESSION_KEY.format(chat_id=chat_id), session_id, ex=SESSION_TTL_SECONDS, nx=True)
    )


async def clear_active_session_if_matches(redis: Redis, chat_id: int, session_id: str) -> None:
    await redis.eval(_COMPARE_AND_DELETE_LUA, 1, ACTIVE_CHAT_SESSION_KEY.format(chat_id=chat_id), session_id)


def session_lock(redis: Redis, session_id: str):
    """Serializes read-modify-write cycles on one session's JSON blob.

    aiogram processes updates concurrently, so without this two "Ready" taps
    (or two poll answers) landing together both load the same snapshot, and
    whichever saves last silently drops the other's change. Worse, both
    "Ready" handlers could see the threshold reached and each start the
    quiz — the group got two "🚀 Ketdik!" countdowns and every question
    twice."""
    return redis.lock(SESSION_LOCK_KEY.format(session_id=session_id), timeout=15, blocking_timeout=15, sleep=0.02)


async def try_claim_question(redis: Redis, session_id: str, index: int) -> bool:
    """Exactly-once guard for sending question `index` (index == question
    count means "finish"). The poll-closed update and the force-advance
    fallback timer both try to advance; only the first one gets True."""
    return bool(
        await redis.set(QUESTION_CLAIM_KEY.format(session_id=session_id, index=index), 1, ex=SESSION_TTL_SECONDS, nx=True)
    )


async def try_claim_finish(redis: Redis, session_id: str) -> bool:
    return bool(await redis.set(FINISH_CLAIM_KEY.format(session_id=session_id), 1, ex=SESSION_TTL_SECONDS, nx=True))
