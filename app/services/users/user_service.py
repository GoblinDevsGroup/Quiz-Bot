from typing import Optional

from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = UserRepository(session)

    async def get_or_create_from_telegram(self, tg_user: TgUser) -> User:
        return await self.repo.get_or_create(
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )

    async def set_locale(self, user: User, locale: str) -> None:
        await self.repo.set_locale(user, locale)

    async def ban(self, user: User) -> None:
        await self.repo.set_banned(user, True)

    async def unban(self, user: User) -> None:
        await self.repo.set_banned(user, False)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        return await self.repo.get_by_telegram_id(telegram_id)
