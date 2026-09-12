import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ReportStatus
from app.database.models import Report


class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, quiz_id: uuid.UUID, reporter_id: uuid.UUID, reason: str, comment: Optional[str] = None
    ) -> Report:
        report = Report(quiz_id=quiz_id, reporter_id=reporter_id, reason=reason, comment=comment)
        self.session.add(report)
        await self.session.flush()
        return report

    async def list_open(self, limit: int = 50) -> list[Report]:
        stmt = (
            select(Report)
            .where(Report.status == ReportStatus.open.value)
            .order_by(Report.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_status(self, report: Report, status: ReportStatus) -> None:
        report.status = status.value
        await self.session.flush()
