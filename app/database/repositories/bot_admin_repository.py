import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BotAdmin


class BotAdminRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> list[BotAdmin]:
        result = await self.session.execute(select(BotAdmin).order_by(BotAdmin.created_at))
        return list(result.scalars().all())

    async def list_telegram_ids(self) -> list[int]:
        result = await self.session.execute(select(BotAdmin.telegram_user_id))
        return list(result.scalars().all())

    async def get_by_id(self, admin_id: uuid.UUID) -> Optional[BotAdmin]:
        return await self.session.get(BotAdmin, admin_id)

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[BotAdmin]:
        result = await self.session.execute(
            select(BotAdmin).where(BotAdmin.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        telegram_user_id: int,
        username: Optional[str],
        full_name: Optional[str],
        added_by_telegram_id: Optional[int],
    ) -> BotAdmin:
        admin = BotAdmin(
            telegram_user_id=telegram_user_id,
            username=username,
            full_name=full_name,
            added_by_telegram_id=added_by_telegram_id,
        )
        self.session.add(admin)
        await self.session.flush()
        return admin

    async def delete(self, admin: BotAdmin) -> None:
        await self.session.delete(admin)
        await self.session.flush()
