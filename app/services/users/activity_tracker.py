import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.user_activity_repository import UserActivityRepository, today_tashkent

# Users already recorded for `_cached_day` in this process. Every update runs
# through the user middleware, so without this each message, button tap and
# poll answer would cost an extra INSERT; this keeps it to one per user per day.
_cached_day: date | None = None
_recorded: set[uuid.UUID] = set()


async def mark_active(session: AsyncSession, user_id: uuid.UUID) -> None:
    global _cached_day
    today = today_tashkent()
    if today != _cached_day:
        _cached_day = today
        _recorded.clear()
    if user_id in _recorded:
        return
    # Savepoint: if this insert fails, only it is rolled back, not the
    # update's whole transaction.
    async with session.begin_nested():
        await UserActivityRepository(session).record(user_id, today)
    _recorded.add(user_id)
