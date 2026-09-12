import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, UserStatistics


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_or_create(
        self,
        telegram_user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> User:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user:
            changed = False
            if user.username != username:
                user.username = username
                changed = True
            if user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if user.last_name != last_name:
                user.last_name = last_name
                changed = True
            if changed:
                await self.session.flush()
            return user

        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        self.session.add(user)
        await self.session.flush()

        stats = UserStatistics(user_id=user.id)
        self.session.add(stats)
        await self.session.flush()
        return user

    async def set_locale(self, user: User, locale: str) -> None:
        user.locale = locale
        await self.session.flush()

    async def set_banned(self, user: User, banned: bool) -> None:
        user.is_banned = banned
        await self.session.flush()

    async def search_by_username(self, query: str, limit: int = 20) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.username.ilike(f"%{query}%")).limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
        total = (await self.session.execute(select(func.count()).select_from(User))).scalar_one()
        stmt = select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def count_all(self) -> int:
        return (await self.session.execute(select(func.count()).select_from(User))).scalar_one()
