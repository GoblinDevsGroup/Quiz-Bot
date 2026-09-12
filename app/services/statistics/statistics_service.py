import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserStatistics
from app.database.repositories.attempt_repository import AttemptRepository
from app.database.repositories.statistics_repository import StatisticsRepository


class StatisticsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.stats_repo = StatisticsRepository(session)
        self.attempt_repo = AttemptRepository(session)

    async def get_user_statistics(self, user_id: uuid.UUID) -> UserStatistics:
        return await self.stats_repo.get_or_create(user_id)

    async def leaderboard(self, limit: int = 10) -> list[UserStatistics]:
        return await self.stats_repo.top_by_points(limit)

    async def quiz_analytics(self, quiz_id: uuid.UUID) -> dict:
        attempts = await self.attempt_repo.list_by_quiz(quiz_id)
        if not attempts:
            return {
                "total_attempts": 0,
                "average_score": 0.0,
                "average_duration_seconds": 0,
            }
        avg_score = sum(a.score_percent for a in attempts) / len(attempts)
        durations = [a.duration_seconds for a in attempts if a.duration_seconds]
        avg_duration = sum(durations) / len(durations) if durations else 0
        return {
            "total_attempts": len(attempts),
            "average_score": round(avg_score, 1),
            "average_duration_seconds": int(avg_duration),
        }
