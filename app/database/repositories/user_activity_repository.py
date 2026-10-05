import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, UserActivityDay

# Uzbekistan has no DST, so a fixed offset is exact and avoids depending on
# tzdata being installed in the container.
TASHKENT_TZ = timezone(timedelta(hours=5))

# "Regular" user: active on at least this many different days in the last
# REGULAR_WINDOW_DAYS days — roughly twice a week, every week.
REGULAR_WINDOW_DAYS = 30
REGULAR_MIN_DAYS = 8


def today_tashkent() -> date:
    return datetime.now(TASHKENT_TZ).date()


class UserActivityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(self, user_id: uuid.UUID, day: date) -> None:
        await self.session.execute(
            insert(UserActivityDay).values(user_id=user_id, day=day).on_conflict_do_nothing()
        )

    async def _active_since(self, first_day: date) -> int:
        stmt = select(func.count(func.distinct(UserActivityDay.user_id))).where(UserActivityDay.day >= first_day)
        return (await self.session.execute(stmt)).scalar_one()

    async def regular_users_count(self, today: date) -> int:
        first_day = today - timedelta(days=REGULAR_WINDOW_DAYS - 1)
        per_user = (
            select(UserActivityDay.user_id)
            .where(UserActivityDay.day >= first_day)
            .group_by(UserActivityDay.user_id)
            .having(func.count() >= REGULAR_MIN_DAYS)
            .subquery()
        )
        return (await self.session.execute(select(func.count()).select_from(per_user))).scalar_one()

    async def summary(self, today: date) -> dict[str, int]:
        month_start = today - timedelta(days=REGULAR_WINDOW_DAYS - 1)
        new_users = (
            await self.session.execute(
                select(func.count()).select_from(User).where(
                    User.created_at >= datetime.combine(month_start, datetime.min.time(), TASHKENT_TZ)
                )
            )
        ).scalar_one()
        return {
            "today": await self._active_since(today),
            "week": await self._active_since(today - timedelta(days=6)),
            "month": await self._active_since(month_start),
            "regular": await self.regular_users_count(today),
            "new_month": new_users,
        }

    async def last_active_days(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, date]:
        if not user_ids:
            return {}
        stmt = (
            select(UserActivityDay.user_id, func.max(UserActivityDay.day))
            .where(UserActivityDay.user_id.in_(user_ids))
            .group_by(UserActivityDay.user_id)
        )
        return {uid: day for uid, day in (await self.session.execute(stmt)).all()}
