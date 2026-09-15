import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SubjectGroup


class SubjectGroupRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_category(self, category_id: uuid.UUID) -> list[SubjectGroup]:
        result = await self.session.execute(
            select(SubjectGroup).where(SubjectGroup.category_id == category_id).order_by(SubjectGroup.created_at)
        )
        return list(result.scalars().all())

    async def get_by_id(self, group_id: uuid.UUID) -> Optional[SubjectGroup]:
        return await self.session.get(SubjectGroup, group_id)

    async def add(self, category_id: uuid.UUID, invite_link: str, title: Optional[str], added_by_telegram_id: Optional[int]) -> SubjectGroup:
        group = SubjectGroup(
            category_id=category_id,
            invite_link=invite_link,
            title=title,
            added_by_telegram_id=added_by_telegram_id,
        )
        self.session.add(group)
        await self.session.flush()
        return group

    async def delete(self, group: SubjectGroup) -> None:
        await self.session.delete(group)
        await self.session.flush()
