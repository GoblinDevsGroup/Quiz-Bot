from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BotChatMembership


class ChatMembershipRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self, chat_id: int, chat_title: Optional[str], chat_type: str, member_count: Optional[int], is_active: bool
    ) -> BotChatMembership:
        existing = await self.session.get(BotChatMembership, chat_id)
        if existing is None:
            existing = BotChatMembership(
                chat_id=chat_id,
                chat_title=chat_title,
                chat_type=chat_type,
                member_count=member_count,
                is_active=is_active,
            )
            self.session.add(existing)
        else:
            existing.chat_title = chat_title
            existing.chat_type = chat_type
            existing.member_count = member_count
            existing.is_active = is_active
        await self.session.flush()
        return existing

    async def list_active(self, limit: int = 100) -> list[BotChatMembership]:
        stmt = (
            select(BotChatMembership)
            .where(BotChatMembership.is_active.is_(True))
            .order_by(BotChatMembership.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(BotChatMembership).where(BotChatMembership.is_active.is_(True))
        return (await self.session.execute(stmt)).scalar_one()
