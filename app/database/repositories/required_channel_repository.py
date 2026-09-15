import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RequiredChannel


class RequiredChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(self) -> list[RequiredChannel]:
        result = await self.session.execute(
            select(RequiredChannel).where(RequiredChannel.is_active.is_(True)).order_by(RequiredChannel.created_at)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[RequiredChannel]:
        result = await self.session.execute(select(RequiredChannel).order_by(RequiredChannel.created_at))
        return list(result.scalars().all())

    async def get_by_id(self, channel_id: uuid.UUID) -> Optional[RequiredChannel]:
        return await self.session.get(RequiredChannel, channel_id)

    async def get_by_chat_id(self, chat_id: int) -> Optional[RequiredChannel]:
        result = await self.session.execute(select(RequiredChannel).where(RequiredChannel.chat_id == chat_id))
        return result.scalar_one_or_none()

    async def add(
        self,
        chat_id: int,
        title: Optional[str],
        username: Optional[str],
        invite_link: Optional[str],
        added_by_telegram_id: Optional[int],
    ) -> RequiredChannel:
        channel = RequiredChannel(
            chat_id=chat_id,
            title=title,
            username=username,
            invite_link=invite_link,
            added_by_telegram_id=added_by_telegram_id,
        )
        self.session.add(channel)
        await self.session.flush()
        return channel

    async def delete(self, channel: RequiredChannel) -> None:
        await self.session.delete(channel)
        await self.session.flush()
