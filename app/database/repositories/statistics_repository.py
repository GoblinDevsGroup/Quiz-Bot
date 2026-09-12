import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserStatistics


class StatisticsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, user_id: uuid.UUID) -> UserStatistics:
        result = await self.session.execute(
            select(UserStatistics).where(UserStatistics.user_id == user_id)
        )
        stats = result.scalar_one_or_none()
        if stats:
            return stats
        stats = UserStatistics(user_id=user_id)
        self.session.add(stats)
        await self.session.flush()
        return stats

    async def on_quiz_created(self, user_id: uuid.UUID) -> None:
        stats = await self.get_or_create(user_id)
        stats.quizzes_created += 1
        await self.session.flush()

    async def on_quiz_completed(
        self, user_id: uuid.UUID, correct: int, incorrect: int, points: int, score_percent: float
    ) -> None:
        stats = await self.get_or_create(user_id)
        stats.quizzes_completed += 1
        stats.total_questions_answered += correct + incorrect
        stats.total_correct_answers += correct
        stats.total_incorrect_answers += incorrect
        stats.total_points += points
        stats.best_score_percent = max(stats.best_score_percent, int(score_percent))
        await self.session.flush()

    async def top_by_points(self, limit: int = 10) -> list[UserStatistics]:
        stmt = (
            select(UserStatistics)
            .order_by(UserStatistics.total_points.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
