import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ReportStatus
from app.database.models import Report
from app.database.repositories.report_repository import ReportRepository


class ReportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ReportRepository(session)

    async def submit_report(
        self, quiz_id: uuid.UUID, reporter_id: uuid.UUID, reason: str, comment: Optional[str] = None
    ) -> Report:
        return await self.repo.create(quiz_id, reporter_id, reason, comment)

    async def list_open_reports(self) -> list[Report]:
        return await self.repo.list_open()

    async def resolve(self, report: Report, dismiss: bool = False) -> None:
        status = ReportStatus.dismissed if dismiss else ReportStatus.reviewed
        await self.repo.set_status(report, status)
